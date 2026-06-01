import asyncio
import base64
import json
import time

from miloco_server.proxy import codex_auth
from miloco_server.proxy import codex_proxy
from miloco_server.proxy.codex_proxy import (
    CodexProxy,
    _messages_to_input,
    _tools_to_responses_tools,
)
from openai.types.shared.function_definition import FunctionDefinition
from miloco_server.schema.model_schema import ThirdPartyModelInfo
from miloco_server.service import model_service as model_service_module
from miloco_server.service.model_service import ModelService


def _jwt_with_exp(exp: int) -> str:
    header = base64.urlsafe_b64encode(b'{"alg":"none"}').rstrip(b"=").decode()
    payload = base64.urlsafe_b64encode(
        json.dumps({"exp": exp}).encode()
    ).rstrip(b"=").decode()
    return f"{header}.{payload}.sig"


def test_codex_auth_reads_oauth_state_and_models(tmp_path, monkeypatch):
    monkeypatch.setenv("CODEX_HOME", str(tmp_path))
    (tmp_path / "auth.json").write_text(
        json.dumps({
            "tokens": {
                "access_token": _jwt_with_exp(int(time.time()) + 3600),
                "refresh_token": "refresh-token",
                "id_token": _jwt_with_exp(int(time.time()) + 3600),
                "account_id": "acct-1",
            }
        }),
        encoding="utf-8",
    )
    (tmp_path / "config.toml").write_text('model = "gpt-5.5"\n', encoding="utf-8")
    (tmp_path / "models_cache.json").write_text(
        json.dumps({"models": [{"slug": "gpt-5.4"}, {"slug": "gpt-5.5"}]}),
        encoding="utf-8",
    )

    state = codex_auth.load_auth_state()
    status = codex_auth.safe_status()

    assert state["logged_in"] is True
    assert state["codex_home"] == str(tmp_path)
    assert status["logged_in"] is True
    assert status["models"][:2] == ["gpt-5.5", "gpt-5.4"]
    assert status["codex_home"] == str(tmp_path)
    assert "access_token" not in status
    assert "refresh_token" not in status


def test_codex_auth_discovers_user_home_when_container_default_is_empty(tmp_path, monkeypatch):
    empty_root_home = tmp_path / "root" / ".codex"
    user_codex_home = tmp_path / "home" / "yangxinyi" / ".codex"
    empty_root_home.mkdir(parents=True)
    user_codex_home.mkdir(parents=True)
    monkeypatch.setenv("CODEX_HOME", str(empty_root_home))
    monkeypatch.setenv("CODEX_HOME_CANDIDATE_ROOTS", str(tmp_path / "home"))
    (user_codex_home / "auth.json").write_text(
        json.dumps({
            "tokens": {
                "access_token": _jwt_with_exp(int(time.time()) + 3600),
                "refresh_token": "refresh-token",
                "id_token": _jwt_with_exp(int(time.time()) + 3600),
            }
        }),
        encoding="utf-8",
    )

    status = codex_auth.safe_status()

    assert status["logged_in"] is True
    assert status["codex_home"] == str(user_codex_home)


def test_codex_proxy_converts_messages_tools_and_function_call():
    input_items = _messages_to_input([
        {"role": "system", "content": "system"},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "look"},
                {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,abc"}},
            ],
        },
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [{
                "id": "call-1",
                "type": "function",
                "function": {"name": "turn_on", "arguments": "{\"x\":1}"},
            }],
        },
        {"role": "tool", "tool_call_id": "call-1", "name": "turn_on", "content": "done"},
    ])
    tools = _tools_to_responses_tools([{
        "type": "function",
        "function": {
            "name": "turn_on",
            "description": "Turn on device",
            "parameters": {"type": "object", "properties": {"id": {"type": "string"}}},
        },
    }])
    call = CodexProxy._event_to_function_call({
        "type": "response.output_item.done",
        "item": {
            "type": "function_call",
            "call_id": "call-2",
            "name": "turn_off",
            "arguments": "{\"id\":\"1\"}",
        },
    })

    assert input_items[0]["content"][0] == {"type": "input_text", "text": "look"}
    assert input_items[0]["content"][1]["type"] == "input_image"
    assert input_items[1]["type"] == "function_call"
    assert input_items[2] == {"type": "function_call_output", "call_id": "call-1", "output": "done"}
    assert tools[0]["name"] == "turn_on"
    assert call["function"]["name"] == "turn_off"


def test_codex_proxy_converts_openai_sdk_function_definition_tools():
    tools = _tools_to_responses_tools([{
        "type": "function",
        "function": FunctionDefinition(
            name="local_default___vision_understand",
            description="Tool for understanding images",
            parameters={
                "type": "object",
                "properties": {
                    "request_id": {"type": "string"},
                    "query": {"type": "string"},
                },
                "required": ["request_id", "query"],
            },
        ),
    }])

    assert tools == [{
        "type": "function",
        "name": "local_default___vision_understand",
        "description": "Tool for understanding images",
        "parameters": {
            "type": "object",
            "properties": {
                "request_id": {"type": "string"},
                "query": {"type": "string"},
            },
            "required": ["request_id", "query"],
        },
    }]


def test_codex_proxy_stream_emits_chat_completion_chunks(monkeypatch):
    proxy = CodexProxy("gpt-5.5")

    async def fake_refresh_tokens_if_needed(home=None, session=None, leeway_seconds=120):
        return {"logged_in": True, "access_token": "token"}

    async def fake_stream_response_json(payload, auth_state, session=None, timeout_seconds=60.0):
        yield {"type": "response.output_text.delta", "delta": "hello"}
        yield {
            "type": "response.output_item.done",
            "item": {
                "type": "function_call",
                "call_id": "call-1",
                "name": "tool",
                "arguments": "{}",
            },
        }

    monkeypatch.setattr(codex_proxy, "refresh_tokens_if_needed", fake_refresh_tokens_if_needed)
    monkeypatch.setattr(proxy, "_stream_response_json", fake_stream_response_json)

    async def collect():
        return [
            chunk
            async for chunk in proxy.async_call_llm_stream([{"role": "user", "content": "hi"}], [])
        ]

    chunks = asyncio.run(collect())

    assert chunks[0]["chunk"].choices[0].delta.content == "hello"
    assert chunks[1]["chunk"].choices[0].finish_reason == "tool_calls"
    assert chunks[1]["chunk"].choices[0].delta.tool_calls[0].function.name == "tool"


def test_model_service_builds_codex_virtual_model_and_proxy():
    model = ModelService._build_codex_model_info("gpt-5.5")
    proxy = ModelService._build_llm_proxy(model)

    assert model.id == "codex-login:gpt-5.5"
    assert model.provider_type == "codex_login"
    assert model.editable is False
    assert model.deletable is False
    assert isinstance(proxy, CodexProxy)


def test_model_service_builds_openai_proxy_for_legacy_third_party_model(monkeypatch):
    class FakeOpenAIProxy:
        def __init__(self, base_url, api_key, model_name):
            self.base_url = base_url
            self.api_key = api_key
            self.model_name = model_name

    monkeypatch.setattr(model_service_module, "OpenAIProxy", FakeOpenAIProxy)

    model = ThirdPartyModelInfo(
        id="third-party-id",
        model_name="qwen3-vl-flash",
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        api_key="test-key",
    )

    proxy = ModelService._build_llm_proxy(model)

    assert isinstance(proxy, FakeOpenAIProxy)
    assert proxy.model_name == "qwen3-vl-flash"
