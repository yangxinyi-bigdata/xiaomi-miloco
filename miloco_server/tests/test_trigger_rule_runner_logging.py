import asyncio
import json
import sys
import types

if "aiocache" not in sys.modules:
    aiocache_module = types.ModuleType("aiocache")
    aiocache_base_module = types.ModuleType("aiocache.base")

    class FakeCache:
        MEMORY = "memory"

    class FakeBaseCache:
        async def clear(self):
            return None

    def fake_cached(*args, **kwargs):  # pylint: disable=unused-argument
        def decorator(func):
            return func
        return decorator

    class FakeCaches:
        def get(self, name):  # pylint: disable=unused-argument
            return FakeBaseCache()

    aiocache_module.Cache = FakeCache
    aiocache_module.cached = fake_cached
    aiocache_module.caches = FakeCaches()
    aiocache_base_module.BaseCache = FakeBaseCache
    sys.modules["aiocache"] = aiocache_module
    sys.modules["aiocache.base"] = aiocache_base_module

from miloco_server.config.prompt_config import UserLanguage
from miloco_server.schema.miot_schema import (
    CameraImgInfo,
    CameraImgInfoPath,
    CameraImgPathSeq,
    CameraImgSeq,
    CameraInfo,
)
from miloco_server.schema.trigger_log_schema import (
    TriggerRuleLogReason,
    TriggerRuleLogStatus,
)
from miloco_server.schema.trigger_schema import ExecuteInfo, TriggerRule
from miloco_server.service import trigger_rule_runner as runner_module
from miloco_server.service.trigger_rule_runner import TriggerRuleRunner


class FakeLLMProxy:
    def __init__(self, content):
        self.content = content
        self.calls = 0

    async def async_call_llm(self, messages):  # pylint: disable=unused-argument
        self.calls += 1
        return {"content": self.content}


class FakeMiotProxy:
    def __init__(self, camera_info, image_seq):
        self.camera_info = camera_info
        self.image_seq = image_seq

    async def get_cameras(self):
        return {self.camera_info.did: self.camera_info}

    def get_recent_camera_img(self, camera_id, channel, count):  # pylint: disable=unused-argument
        return self.image_seq


class FakeTriggerRuleLogDAO:
    def __init__(self):
        self.logs = []

    def create(self, log):
        self.logs.append(log)
        return log.id


def _camera_info():
    return CameraInfo(
        did="camera-1",
        name="Living Room Camera",
        online=True,
        channel_count=1,
        camera_status="online",
    )


def _image_seq(camera_info):
    return CameraImgSeq(
        camera_info=camera_info,
        channel=0,
        img_list=[
            CameraImgInfo(data=b"first", timestamp=1710000000000),
            CameraImgInfo(data=b"second", timestamp=1710000000500),
        ],
    )


def _rule():
    return TriggerRule(
        id="rule-1",
        enabled=True,
        name="Room Presence",
        cameras=["camera-1"],
        condition="detect whether someone is in the room",
        execute_info=ExecuteInfo(),
    )


def _runner(rule, llm_proxy, miot_proxy, dao):
    return TriggerRuleRunner(
        [rule],
        miot_proxy,
        lambda purpose: llm_proxy,  # pylint: disable=unused-argument
        lambda: UserLanguage.CHINESE,
        None,
        dao,
    )


def test_parse_llm_output_accepts_structured_json_and_legacy_numbers():
    structured = TriggerRuleRunner._parse_llm_output(json.dumps({
        "is_happened": False,
        "is_same_action": False,
        "reason": "No person is visible in the scene",
    }))
    legacy = TriggerRuleRunner._parse_llm_output("2")

    assert structured == {
        "is_happened": False,
        "is_same_action": False,
        "reason": "No person is visible in the scene",
        "raw_output": '{"is_happened": false, "is_same_action": false, "reason": "No person is visible in the scene"}',
    }
    assert legacy["is_happened"] is True
    assert legacy["is_same_action"] is True
    assert legacy["raw_output"] == "2"


def test_no_match_model_result_is_written_as_explainable_log(monkeypatch):
    camera_info = _camera_info()
    image_seq = _image_seq(camera_info)
    rule = _rule()
    dao = FakeTriggerRuleLogDAO()
    llm_proxy = FakeLLMProxy(json.dumps({
        "is_happened": False,
        "is_same_action": False,
        "reason": "No person is visible in the scene",
    }))
    runner = _runner(rule, llm_proxy, FakeMiotProxy(camera_info, image_seq), dao)
    runner._check_camera_motion = lambda checked_image_seq: True  # pylint: disable=protected-access,unused-argument

    async def fake_store_to_path(self):
        return CameraImgPathSeq(
            camera_info=self.camera_info,
            channel=self.channel,
            img_list=[CameraImgInfoPath(data="/tmp/frame.jpg", timestamp=1710000000000)],
        )

    monkeypatch.setattr(runner_module.trigger_filter, "pre_filter", lambda checked_rule: True)
    monkeypatch.setattr(CameraImgSeq, "store_to_path", fake_store_to_path)

    asyncio.run(runner._execute_scheduled_task())

    assert len(dao.logs) == 1
    log = dao.logs[0]
    assert log.status == TriggerRuleLogStatus.SKIPPED
    assert log.reason_code == TriggerRuleLogReason.NO_CONDITION_MATCH
    assert log.message == "No person is visible in the scene"
    assert log.condition_results[0].result is False
    assert log.condition_results[0].llm_reason == "No person is visible in the scene"
    assert log.condition_results[0].llm_raw_output
    assert log.condition_results[0].images[0].data == "/tmp/frame.jpg"


def test_structured_trigger_and_same_action_results_keep_model_reason():
    camera_info = _camera_info()
    image_seq = _image_seq(camera_info)
    rule = _rule()
    runner = _runner(
        rule,
        FakeLLMProxy(json.dumps({
            "is_happened": True,
            "is_same_action": False,
            "reason": "A person is standing in the room",
        })),
        FakeMiotProxy(camera_info, image_seq),
        FakeTriggerRuleLogDAO(),
    )

    result = asyncio.run(runner._check_trigger_condition(
        rule,
        runner._get_vision_understaning_llm_proxy(),
        {"camera-1": {0: (True, image_seq)}},
        {"camera-1": camera_info},
    ))

    condition_result = result["condition_results"][0]
    assert condition_result.result is True
    assert condition_result.is_same_action is False
    assert condition_result.llm_reason == "A person is standing in the room"

    same_action_runner = _runner(
        rule,
        FakeLLMProxy(json.dumps({
            "is_happened": True,
            "is_same_action": True,
            "reason": "The same person is still standing in the same place",
        })),
        FakeMiotProxy(camera_info, image_seq),
        FakeTriggerRuleLogDAO(),
    )
    same_action_result = asyncio.run(same_action_runner._check_trigger_condition(
        rule,
        same_action_runner._get_vision_understaning_llm_proxy(),
        {"camera-1": {0: (True, image_seq)}},
        {"camera-1": camera_info},
    ))

    diagnostic = same_action_result["diagnostics"][0]
    assert diagnostic["reason_code"] == TriggerRuleLogReason.SAME_ACTION_SKIPPED
    assert diagnostic["message"] == "The same person is still standing in the same place"
    assert diagnostic["condition_results"][0].llm_reason == "The same person is still standing in the same place"


def test_pre_filter_skip_does_not_write_business_log(monkeypatch):
    camera_info = _camera_info()
    image_seq = _image_seq(camera_info)
    rule = _rule()
    dao = FakeTriggerRuleLogDAO()
    llm_proxy = FakeLLMProxy("1")
    runner = _runner(rule, llm_proxy, FakeMiotProxy(camera_info, image_seq), dao)

    monkeypatch.setattr(runner_module.trigger_filter, "pre_filter", lambda checked_rule: False)

    asyncio.run(runner._execute_scheduled_task())

    assert dao.logs == []
    assert llm_proxy.calls == 0
