# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""
Trigger business logic service
Handles trigger-related business logic and data validation
"""

import json
import time
from typing import TYPE_CHECKING, Any, Callable, List, Dict, Optional
import asyncio
import logging
import uuid

from miloco_server.schema.mcp_schema import CallToolResult
from thespian.actors import ActorExitRequest

from miloco_server import actor_system
from miloco_server.config.normal_config import TRIGGER_RULE_RUNNER_CONFIG
from miloco_server.config.prompt_config import UserLanguage
from miloco_server.dao.trigger_rule_log_dao import TriggerRuleLogDAO
from miloco_server.proxy.llm_proxy import LLMProxy
from miloco_server.schema.miot_schema import CameraImgPathSeq, CameraImgSeq, CameraInfo
from miloco_server.schema.trigger_log_schema import (
    AiRecommendDynamicExecuteResult, TriggerConditionResult, ActionExecuteResult,
    TriggerRuleLog, NotifyResult, ExecuteResult, TriggerRuleLogReason,
    TriggerRuleLogStatus
)
from miloco_server.schema.trigger_schema import (
    Action, TriggerRule, ExecuteType, SendingState
)
from miloco_server.utils.local_models import ModelPurpose
from miloco_server.utils.prompt_helper import TriggerRuleConditionPromptBuilder
from miloco_server.utils.trigger_filter import trigger_filter
from miloco_server.service import trigger_rule_dynamic_executor_cache
from miloco_server.service.trigger_rule_dynamic_executor import START, TriggerRuleDynamicExecutor

logger = logging.getLogger(name=__name__)

if TYPE_CHECKING:
    from miloco_server.proxy.miot_proxy import MiotProxy
    from miloco_server.mcp.tool_executor import ToolExecutor


class TriggerRuleRunner:
    """Trigger service class"""

    def __init__(self, trigger_rules: List[TriggerRule], miot_proxy: "MiotProxy",
                 get_llm_proxy_by_purpose: Callable[[ModelPurpose], LLMProxy],
                 get_language: Callable[[], UserLanguage],
                 tool_executor: "ToolExecutor",
                 trigger_rule_log_dao: TriggerRuleLogDAO):

        self.trigger_rules: Dict[str, TriggerRule] = {
            rule.id: rule
            for rule in trigger_rules if rule.id is not None
        }
        self._get_llm_proxy_by_purpose = get_llm_proxy_by_purpose
        self.miot_proxy = miot_proxy
        self._get_language = get_language
        self.trigger_rule_log_dao = trigger_rule_log_dao
        self._tool_executor = tool_executor
        self._task = None
        self._is_running: bool = False
        self._interval_seconds = TRIGGER_RULE_RUNNER_CONFIG["interval_seconds"]
        self._vision_use_img_count = TRIGGER_RULE_RUNNER_CONFIG["vision_use_img_count"]
        # Per-camera last happened cache: key=(rule_id, camera_did, channel), value=CameraImgSeq
        self._last_happened_cache: Dict[tuple, CameraImgSeq] = {}
        self._sending_states: Dict[str, SendingState] = {}
        logger.info(
            "TriggerRuleRunner init success, trigger_rules: %s", self.trigger_rules
        )

    def _get_vision_understaning_llm_proxy(self) -> LLMProxy:
        return self._get_llm_proxy_by_purpose(
            ModelPurpose.VISION_UNDERSTANDING)

    def add_trigger_rule(self, trigger_rule: TriggerRule):
        """Add trigger rule"""
        self.trigger_rules[trigger_rule.id] = trigger_rule

    def remove_trigger_rule(self, rule_id: str):
        """Remove trigger rule"""
        if rule_id in self.trigger_rules:
            del self.trigger_rules[rule_id]
            self._sending_states.pop(rule_id, None)
        # Clean up cache entries for this rule
        keys_to_remove = [k for k in self._last_happened_cache if k[0] == rule_id]
        for key in keys_to_remove:
            del self._last_happened_cache[key]

    async def _periodic_task(self):
        """Scheduled task execution method, runs at configured interval"""
        while self._is_running:
            try:
                # Execute scheduled task logic
                asyncio.create_task(self._execute_scheduled_task())
                # Wait for configured interval
                await asyncio.sleep(self._interval_seconds)
            except Exception as e:  # pylint: disable=broad-except
                logger.error(
                    "Error occurred while executing scheduled task: %s", e)
                await asyncio.sleep(self._interval_seconds)

    async def _check_scheduled_task(self, llm_proxy, enabled_rules):
        # only load used camera in rules
        needed_camera_ids = set()
        for _, rule in enabled_rules:
            needed_camera_ids.update(rule.cameras)

        # Load used camera info
        miot_camera_info_dict = await self.miot_proxy.get_cameras()
        camera_info_dict = {
            camera_id: CameraInfo.model_validate(miot_camera_info.model_dump())
            for camera_id, miot_camera_info in miot_camera_info_dict.items()
            if camera_id in needed_camera_ids
        }

        camera_motion_dict: dict[str,
                                 dict[int,
                                      tuple[bool,
                                            Optional[CameraImgSeq]]]] = {}

        # Calculate motion changes
        for camera_id, camera_info in camera_info_dict.items():
            if camera_id not in camera_motion_dict:
                camera_motion_dict[camera_id] = {}
            for channel in range(camera_info.channel_count or 1):
                logger.info(
                    "camera %s channel %s get recent camera img", camera_id, channel
                )
                camera_img_seq = self.miot_proxy.get_recent_camera_img(
                    camera_id, channel, self._vision_use_img_count)
                if camera_img_seq and self._check_camera_motion(
                        camera_img_seq):
                    logger.info(
                        "camera %s channel %s motion: true", camera_id, channel)
                    camera_motion_dict[camera_id][channel] = (True,
                                                              camera_img_seq)
                else:
                    logger.info(
                        "camera %s channel %s motion: false", camera_id, channel)
                    camera_motion_dict[camera_id][channel] = (False,
                                                              camera_img_seq)

        # Create concurrent task list
        tasks = []
        rule_info_list = []
        for rule_id, rule in enabled_rules:
            logger.info(
                "Preparing to check trigger rule: %s %s", rule_id, rule.name)
            task = self._check_trigger_condition(rule, llm_proxy,
                                                 camera_motion_dict,
                                                 camera_info_dict)
            tasks.append(task)
            rule_info_list.append((rule_id, rule))

        # Concurrently execute all trigger rule checks
        condition_results = await asyncio.gather(*tasks, 
                                                 return_exceptions=True)

        return rule_info_list, condition_results, camera_motion_dict

    async def _execute_scheduled_task(self):
        start_time = int(time.time() * 1000)

        all_enabled_rules = [
            (rule_id, rule)
            for rule_id, rule in self.trigger_rules.items()
            if rule.enabled
        ]

        llm_proxy = self._get_vision_understaning_llm_proxy()
        if not llm_proxy:
            logger.warning(
                "Vision understaning LLM proxy not available, skipping rules trigger")
            for _, rule in all_enabled_rules:
                await self._log_rule_diagnostic(
                    start_time,
                    rule,
                    TriggerRuleLogStatus.FAILED,
                    TriggerRuleLogReason.LLM_ERROR,
                    "Vision understanding LLM proxy not available",
                )
            return

        # Filter triggerable rules and record business skips.
        enabled_rules = []
        for rule_id, rule in all_enabled_rules:
            if trigger_filter.pre_filter(rule):
                enabled_rules.append((rule_id, rule))
            else:
                logger.info(
                    "Rule %s skipped by trigger period or frequency filter",
                    rule_id,
                )

        if not enabled_rules:
            logger.info("No enabled trigger rules to check")
            return

        rule_info_list, condition_results, camera_motion_dict = await self._check_scheduled_task(llm_proxy, enabled_rules)

        # Process results
        for (rule_id,
             rule), condition_result_list in zip(rule_info_list,
                                                 condition_results):
            # Check for exceptions
            if isinstance(condition_result_list, Exception):
                logger.error(
                    "Rule check failed for %s %s: %s", rule_id, rule.name, condition_result_list
                )
                await self._log_rule_diagnostic(
                    start_time,
                    rule,
                    TriggerRuleLogStatus.FAILED,
                    TriggerRuleLogReason.LLM_ERROR,
                    f"Rule check failed: {condition_result_list}",
                )
                continue

            # Ensure return type is valid
            if not isinstance(condition_result_list, dict):
                logger.error(
                    "Invalid condition result type for rule %s: %s", rule_id, type(condition_result_list)
                )
                await self._log_rule_diagnostic(
                    start_time,
                    rule,
                    TriggerRuleLogStatus.FAILED,
                    TriggerRuleLogReason.LLM_ERROR,
                    f"Invalid condition result type: {type(condition_result_list)}",
                )
                continue

            for diagnostic in condition_result_list.get("diagnostics", []):
                await self._log_rule_diagnostic(
                    start_time,
                    rule,
                    diagnostic["status"],
                    diagnostic["reason_code"],
                    diagnostic["message"],
                    camera_motion_dict,
                    diagnostic.get("condition_results") or [],
                )

            trigger_condition_results = condition_result_list.get("condition_results", [])
            executable_condition_results = []
            skipped_by_post_filter = False
            for condition_result in trigger_condition_results:
                if trigger_filter.post_filter(rule_id, condition_result.result):
                    executable_condition_results.append(condition_result)
                else:
                    skipped_by_post_filter = True

            execable = bool(executable_condition_results)

            is_dynamic_action_running = self._check_dynamic_action_is_running(rule_id)
            logger.info(
                "Rule %s is execable: %s, dynamic action is running: %s",
                rule_id, execable, is_dynamic_action_running)

            if execable and not is_dynamic_action_running:
                execute_id = str(uuid.uuid4())
                execute_result, status, reason_code, message = await self._execute_trigger_action(
                    execute_id, rule, camera_motion_dict)
                await self._log_rule_execution(execute_id, start_time, rule,
                                               camera_motion_dict,
                                               executable_condition_results,
                                               execute_result,
                                               status,
                                               reason_code,
                                               message)
            elif execable and is_dynamic_action_running:
                await self._log_rule_diagnostic(
                    start_time,
                    rule,
                    TriggerRuleLogStatus.SKIPPED,
                    TriggerRuleLogReason.DYNAMIC_ACTION_RUNNING,
                    "Dynamic action is still running, skip this trigger",
                    camera_motion_dict,
                    executable_condition_results,
                )
            elif skipped_by_post_filter:
                await self._log_rule_diagnostic(
                    start_time,
                    rule,
                    TriggerRuleLogStatus.SKIPPED,
                    TriggerRuleLogReason.PRE_FILTER_SKIPPED,
                    "Rule skipped by minimum trigger interval",
                    camera_motion_dict,
                    trigger_condition_results,
                )

        logger.info(
            "Scheduled task completed, checked %d trigger rules", len(enabled_rules)
        )

    async def _log_rule_execution(
            self,
            execute_id: str,
            start_time: int,
            rule: TriggerRule,
            camera_motion_dict: dict[str, dict[int,
                                           tuple[bool,
                                                 Optional[CameraImgSeq]]]],
            condition_result_list: list[TriggerConditionResult],
            execute_result: Optional[ExecuteResult] = None,
            status: str = TriggerRuleLogStatus.TRIGGERED,
            reason_code: Optional[str] = None,
            message: Optional[str] = None):
        """Record rule trigger and execution logs, save to database"""
        logger.info(
            "Rule %s triggered, condition results: %s", rule.name, condition_result_list
        )

        for condition_result in condition_result_list:
            is_motion, camera_img_seq = camera_motion_dict[condition_result.camera_info.did][condition_result.channel]
            if is_motion and camera_img_seq:
                path_seq: CameraImgPathSeq = await camera_img_seq.store_to_path()
                condition_result.images = path_seq.img_list

        trigger_rule_log = TriggerRuleLog(
            id=execute_id,
            timestamp=start_time,
            trigger_rule_id=rule.id,
            trigger_rule_name=rule.name,
            trigger_rule_condition=rule.condition,
            condition_results=condition_result_list,
            execute_result=execute_result,
            status=status,
            reason_code=reason_code,
            message=message,
        )

        # Save to database
        log_id = self.trigger_rule_log_dao.create(trigger_rule_log)
        if log_id:
            logger.info(
                "Trigger rule log saved to database: id=%s, rule_id=%s", log_id, rule.id
            )
        else:
            logger.error(
                "Failed to save trigger rule log to database: rule_id=%s", rule.id
            )

    async def _log_rule_diagnostic(
            self,
            start_time: int,
            rule: TriggerRule,
            status: str,
            reason_code: str,
            message: str,
            camera_motion_dict: Optional[dict[str, dict[int,
                                           tuple[bool,
                                                 Optional[CameraImgSeq]]]]] = None,
            condition_result_list: Optional[list[TriggerConditionResult]] = None):
        """Record failed or skipped rule diagnostic logs."""
        condition_results = condition_result_list or []
        if camera_motion_dict:
            for condition_result in condition_results:
                camera_channels = camera_motion_dict.get(condition_result.camera_info.did, {})
                is_motion, camera_img_seq = camera_channels.get(
                    condition_result.channel, (False, None))
                if is_motion and camera_img_seq:
                    path_seq: CameraImgPathSeq = await camera_img_seq.store_to_path()
                    condition_result.images = path_seq.img_list

        trigger_rule_log = TriggerRuleLog(
            id=str(uuid.uuid4()),
            timestamp=start_time,
            trigger_rule_id=rule.id,
            trigger_rule_name=rule.name,
            trigger_rule_condition=rule.condition,
            condition_results=condition_results,
            execute_result=None,
            status=status,
            reason_code=reason_code,
            message=message,
        )
        log_id = self.trigger_rule_log_dao.create(trigger_rule_log)
        if log_id:
            logger.info(
                "Trigger rule diagnostic log saved: id=%s, rule_id=%s, status=%s, reason=%s",
                log_id, rule.id, status, reason_code
            )
        else:
            logger.error(
                "Failed to save trigger rule diagnostic log: rule_id=%s, status=%s, reason=%s",
                rule.id, status, reason_code
            )

    def start_periodic_task(self):
        """Start async scheduled task"""
        if self._is_running:
            logger.warning("Scheduled task is already running")
            return

        self._is_running = True
        self._task = asyncio.create_task(self._periodic_task())
        logger.info("Scheduled task started, executing every %d seconds", self._interval_seconds)

    async def stop_periodic_task(self):
        """Stop async scheduled task"""
        if not self._is_running:
            logger.warning("Scheduled task is not running")
            return

        self._is_running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

        logger.info("Scheduled task stopped")

    def is_task_running(self) -> bool:
        """Check if scheduled task is running"""
        return self._is_running

    async def _call_vision_understaning(self, llm_proxy: LLMProxy, messages):
        """
        Call vision understanding LLM

        Returns:
            LLM response result
        """
        return await asyncio.wait_for(llm_proxy.async_call_llm(messages), timeout=TRIGGER_RULE_RUNNER_CONFIG["request_timeout_seconds"])

    @staticmethod
    def _parse_llm_output(content) -> Optional[dict[str, Any]]:
        """Parse structured or legacy LLM output into a normalized result.
        Returns None if output is invalid."""
        try:
            stripped = str(content).strip()
        except Exception:  # pylint: disable=broad-except
            logger.error("Invalid LLM output: %s", content)
            return None

        def legacy_result(is_happened: bool, is_same_action: bool) -> dict[str, Any]:
            return {
                "is_happened": is_happened,
                "is_same_action": is_same_action,
                "reason": "",
                "raw_output": stripped,
            }
        
        if stripped == "0":
            return legacy_result(False, False)
        if stripped == "1":
            return legacy_result(True, False)
        if stripped == "2":
            return legacy_result(True, True)

        json_text = stripped
        if json_text.startswith("```"):
            json_text = json_text.strip("`").strip()
            if json_text.lower().startswith("json"):
                json_text = json_text[4:].strip()

        try:
            parsed_json = json.loads(json_text)
        except json.JSONDecodeError:
            start = json_text.find("{")
            end = json_text.rfind("}")
            if start >= 0 and end > start:
                try:
                    parsed_json = json.loads(json_text[start:end + 1])
                except json.JSONDecodeError:
                    logger.error("Invalid LLM output: %s", content)
                    return None
            else:
                logger.error("Invalid LLM output: %s", content)
                return None

        if not isinstance(parsed_json, dict):
            logger.error("Invalid LLM output JSON type: %s", type(parsed_json))
            return None

        def parse_bool(value):
            if isinstance(value, bool):
                return value
            if isinstance(value, str):
                normalized = value.strip().lower()
                if normalized == "true":
                    return True
                if normalized == "false":
                    return False
            return None

        is_happened = parse_bool(parsed_json.get("is_happened"))
        is_same_action = parse_bool(parsed_json.get("is_same_action"))

        if not isinstance(is_happened, bool) or not isinstance(is_same_action, bool):
            logger.error("Invalid LLM output fields: %s", content)
            return None

        reason = parsed_json.get("reason") or parsed_json.get("llm_reason") or ""
        return {
            "is_happened": is_happened,
            "is_same_action": is_same_action,
            "reason": str(reason).strip(),
            "raw_output": stripped,
        }

    async def _check_trigger_condition(
        self, rule: TriggerRule, llm_proxy: LLMProxy,
        camera_motion_dict: dict[str, dict[int,
                                           tuple[bool,
                                                 Optional[CameraImgSeq]]]],
        camera_info_dict: dict[str,
                               CameraInfo]) -> dict[str, list[Any]]:

        cameras_video: dict[tuple[str, int], CameraImgSeq] = {}
        condition_result_list: List[TriggerConditionResult] = []
        diagnostics: list[dict[str, Any]] = []
        start_time = time.time()

        sending_state = self._sending_states.get(rule.id)
        if sending_state and sending_state.flag and start_time - sending_state.time < TRIGGER_RULE_RUNNER_CONFIG["request_timeout_seconds"]:
            logger.info("%s %s Rule %s is sending, skip", start_time, rule.name, rule.id)
            return {
                "condition_results": [],
                "diagnostics": [{
                    "status": TriggerRuleLogStatus.SKIPPED,
                    "reason_code": TriggerRuleLogReason.DYNAMIC_ACTION_RUNNING,
                    "message": "Previous rule condition check is still running",
                    "condition_results": [],
                }],
            }
        logger.info("%s %s Rule %s start check", start_time, rule.name, rule.id)
        self._sending_states[rule.id] = SendingState(flag=True, time=start_time)

        try:
            for camera_id in rule.cameras:
                if camera_id not in camera_info_dict:
                    diagnostics.append({
                        "status": TriggerRuleLogStatus.FAILED,
                        "reason_code": TriggerRuleLogReason.LLM_ERROR,
                        "message": f"Camera info not found: {camera_id}",
                        "condition_results": [],
                    })
                    continue
                camera_info = camera_info_dict[camera_id]
                channel_motion_dict = camera_motion_dict[camera_id]
                for channel, (if_motion,
                            camera_img_seq) in channel_motion_dict.items():
                    # check sending state flag:
                    if not if_motion or not camera_img_seq:
                        continue
                    cameras_video[camera_id, channel] = camera_img_seq

            # Concurrently execute LLM calls for all cameras  
            tasks = []
            for (camera_id, channel), camera_img_seq in cameras_video.items():
                # Load last happened frames for this camera/channel
                last_happened_img_seq = self._last_happened_cache.get((rule.id, camera_id, channel))
                messages = TriggerRuleConditionPromptBuilder.build_trigger_rule_prompt(
                    camera_img_seq, rule.condition, self._get_language(),
                    last_happened_img_seq=last_happened_img_seq)
                task = self._call_vision_understaning(llm_proxy, messages.get_messages())
                tasks.append(task)

            # Concurrently execute all tasks
            responses = await asyncio.gather(*tasks, return_exceptions=True)
            
            for ((camera_id, channel),
                camera_img_seq), response in zip(cameras_video.items(),
                                                responses):
                logger.info("Rule %s %s Camera %s channel %s LLM response: %s", rule.id, rule.name, camera_id, channel, response)

                condition_result = TriggerConditionResult(
                    camera_info=camera_info_dict[camera_id],
                    channel=channel,
                    result=False)

                if isinstance(response, (asyncio.TimeoutError, TimeoutError)):
                    logger.error(
                        "LLM call timeout for camera %s channel %s", camera_id, channel
                    )
                    diagnostics.append({
                        "status": TriggerRuleLogStatus.FAILED,
                        "reason_code": TriggerRuleLogReason.LLM_TIMEOUT,
                        "message": f"LLM call timeout for camera {camera_id} channel {channel}",
                        "condition_results": [condition_result],
                    })
                    continue

                # Check for exceptions
                if isinstance(response, Exception):
                    logger.error(
                        "LLM call failed for camera %s channel %s: %s", camera_id, channel, response
                    )
                    diagnostics.append({
                        "status": TriggerRuleLogStatus.FAILED,
                        "reason_code": TriggerRuleLogReason.LLM_ERROR,
                        "message": f"LLM call failed for camera {camera_id} channel {channel}: {response}",
                        "condition_results": [condition_result],
                    })
                    continue

                # Ensure response is dict type before accessing
                if not isinstance(response, dict):
                    logger.error(
                        "Invalid response type for camera %s channel %s: %s", camera_id, channel, type(response)
                    )
                    diagnostics.append({
                        "status": TriggerRuleLogStatus.FAILED,
                        "reason_code": TriggerRuleLogReason.LLM_ERROR,
                        "message": f"Invalid LLM response type for camera {camera_id} channel {channel}: {type(response)}",
                        "condition_results": [condition_result],
                    })
                    continue

                content = response.get("content")
                condition_result.llm_raw_output = "" if content is None else str(content).strip()
                
                logger.info(
                    "Condition result, rule name: %s, rule condition: %s, camera_id: %s, channel: %s, content: %s",
                    rule.name, rule.condition, camera_id, channel, content
                )

                if not content:
                    diagnostics.append({
                        "status": TriggerRuleLogStatus.FAILED,
                        "reason_code": TriggerRuleLogReason.INVALID_LLM_OUTPUT,
                        "message": f"Empty LLM output for camera {camera_id} channel {channel}",
                        "condition_results": [condition_result],
                    })
                    continue

                parsed = self._parse_llm_output(content)
                if parsed is None:
                    logger.error(
                        "Invalid LLM output for rule %s camera %s channel %s: "
                        "expected 0/1/2, got: %s",
                        rule.name, camera_id, channel, content)
                    diagnostics.append({
                        "status": TriggerRuleLogStatus.FAILED,
                        "reason_code": TriggerRuleLogReason.INVALID_LLM_OUTPUT,
                        "message": f"Invalid LLM output for camera {camera_id} channel {channel}: expected 0/1/2, got {content}",
                        "condition_results": [condition_result],
                    })
                    continue

                is_happened = parsed["is_happened"]
                is_same_action = parsed["is_same_action"]
                llm_reason = parsed["reason"]
                condition_result.result = is_happened
                condition_result.is_same_action = is_same_action
                condition_result.llm_reason = llm_reason
                condition_result.llm_raw_output = parsed["raw_output"]

                # Output 0: no action detected
                if not is_happened:
                    logger.info(
                        "Rule %s camera %s channel %s: no action detected (output 0)",
                        rule.name, camera_id, channel)
                    diagnostics.append({
                        "status": TriggerRuleLogStatus.SKIPPED,
                        "reason_code": TriggerRuleLogReason.NO_CONDITION_MATCH,
                        "message": llm_reason or f"Condition did not match for camera {camera_id} channel {channel}",
                        "condition_results": [condition_result],
                    })
                    continue

                # Output 1: action triggered, and is a new action(execution needed)
                if is_happened and not is_same_action:
                    logger.info(
                        "Rule %s camera %s channel %s: action triggered, and is a new action(execution needed) (output 1), updating cache and returning True",
                        rule.name, camera_id, channel)
                    self._last_happened_cache[(rule.id, camera_id, channel)] = camera_img_seq
                    condition_result_list.append(condition_result)
                    continue

                # Output 2 : action triggered, but is not a new action (No execution needed)
                if is_happened:
                    logger.info(
                        "Rule %s camera %s channel %s: action triggered, but is not a new action (No execution needed) (output 2), only update cache",
                        rule.name, camera_id, channel)
                    self._last_happened_cache[(rule.id, camera_id, channel)] = camera_img_seq
                    diagnostics.append({
                        "status": TriggerRuleLogStatus.SKIPPED,
                        "reason_code": TriggerRuleLogReason.SAME_ACTION_SKIPPED,
                        "message": llm_reason or f"Same action already happened for camera {camera_id} channel {channel}",
                        "condition_results": [condition_result],
                    })
                    continue

        finally:
            end_time = time.time()
            self._sending_states[rule.id] = SendingState(flag=False, time=end_time)

        return {
            "condition_results": condition_result_list,
            "diagnostics": diagnostics,
        }

    def _check_camera_motion(self, camera_img_seq: CameraImgSeq) -> bool:
        """Detect motion in images"""
        if len(camera_img_seq.img_list) < 2:
            return False
        from miloco_server.utils.check_img_motion import check_camera_motion
        return check_camera_motion(camera_img_seq.img_list[0].data,
                                   camera_img_seq.img_list[-1].data)

    async def _execute_trigger_action(
        self, execute_id: str, rule: TriggerRule,
        camera_motion_dict: dict[str, dict[int,
                                           tuple[bool,
                                                 Optional[CameraImgSeq]]]]
    ) -> tuple[Optional[ExecuteResult], str, Optional[str], Optional[str]]:
        """Execute trigger action"""
        logger.info("[%s] Executing trigger action: %s", execute_id, rule.name)

        if not rule.execute_info:
            return None, TriggerRuleLogStatus.TRIGGERED, None, None

        execute_type = rule.execute_info.ai_recommend_execute_type
        ai_recommend_action_execute_results = None
        ai_recommend_dynamic_execute_result = None
        automation_action_execute_results = None
        notify_result = None
        failure_reason_code = None
        failure_messages = []

        # Handle STATIC action type
        if execute_type == ExecuteType.STATIC and rule.execute_info.ai_recommend_actions:
            ai_recommend_action_execute_results = []
            for action in rule.execute_info.ai_recommend_actions:
                result = await self.execute_action(action)
                if not result:
                    failure_reason_code = TriggerRuleLogReason.ACTION_FAILED
                    failure_messages.append(
                        f"MCP action failed: {action.mcp_server_name}.{action.mcp_tool_name}")
                ai_recommend_action_execute_results.append(
                    ActionExecuteResult(action=action, result=result))

        # Handle DYNAMIC action type
        if execute_type == ExecuteType.DYNAMIC:
            ai_recommend_dynamic_execute_result = AiRecommendDynamicExecuteResult(
                is_done=False,
                ai_recommend_action_descriptions=rule.execute_info.ai_recommend_action_descriptions,
                chat_history_session=None)
            if rule.execute_info.ai_recommend_action_descriptions:
                # execute dynamic action in background
                asyncio.create_task(self._execute_dynamic_action(execute_id, rule, camera_motion_dict))
            else:
                ai_recommend_dynamic_execute_result.is_done = True
                logger.warning("[%s] Dynamic action descriptions not found, skip dynamic action", execute_id)

        # Handle automation actions
        if rule.execute_info.automation_actions:
            automation_action_execute_results = []
            for action in rule.execute_info.automation_actions:
                result = await self.execute_action(action)
                if not result:
                    failure_reason_code = TriggerRuleLogReason.ACTION_FAILED
                    failure_messages.append(
                        f"Automation action failed: {action.mcp_server_name}.{action.mcp_tool_name}")
                automation_action_execute_results.append(
                    ActionExecuteResult(action=action, result=result))

        # Send MiOT notification
        if rule.execute_info.notify:
            try:
                notify_res = await self.miot_proxy.send_app_notify(rule.execute_info.notify.id)
            except Exception as err:  # pylint: disable=broad-except
                notify_res = False
                logger.error("Send miot notify failed: %s, notify: %s", err, rule.execute_info.notify)
                failure_messages.append(f"Mi Home notification failed: {err}")
            else:
                if not notify_res:
                    failure_messages.append("Mi Home notification failed")
            if not notify_res and failure_reason_code is None:
                failure_reason_code = TriggerRuleLogReason.NOTIFY_FAILED
            logger.info("Send miot notify result: %s, notify: %s", notify_res, rule.execute_info.notify)
            notify_result = NotifyResult(notify=rule.execute_info.notify, result=notify_res)

        execute_result = ExecuteResult(
            ai_recommend_execute_type=execute_type,
            ai_recommend_action_execute_results=ai_recommend_action_execute_results,
            ai_recommend_dynamic_execute_result=ai_recommend_dynamic_execute_result,
            automation_action_execute_results=automation_action_execute_results,
            notify_result=notify_result
        )
        if failure_messages:
            return (
                execute_result,
                TriggerRuleLogStatus.FAILED,
                failure_reason_code or TriggerRuleLogReason.ACTION_FAILED,
                "; ".join(failure_messages),
            )
        return execute_result, TriggerRuleLogStatus.TRIGGERED, None, None

    async def _execute_dynamic_action(self, execute_id: str, rule: TriggerRule,
                                    camera_motion_dict: dict[str, dict[int,
                                           tuple[bool,
                                                 Optional[CameraImgSeq]]]]) -> None:
        """Execute dynamic action"""
        trigger_rule_dynamic_executor = None
        created_dynamic_executor = None
        try:
            logger.info("[%s] Executing dynamic action: %s", execute_id, rule.name)
            trigger_rule_dynamic_executor = trigger_rule_dynamic_executor_cache.get(rule.id)
            if trigger_rule_dynamic_executor:
                logger.error(
                    "[%s] Dynamic executor already exists pass it, trigger_rule: %s",
                    execute_id, rule.name)
                self.trigger_rule_log_dao.update_status(
                    execute_id,
                    TriggerRuleLogStatus.SKIPPED,
                    TriggerRuleLogReason.DYNAMIC_ACTION_RUNNING,
                    "Dynamic executor already exists",
                )
                return

            created_dynamic_executor = actor_system.createActor(
                lambda: TriggerRuleDynamicExecutor(
                    execute_id, rule, self.trigger_rule_log_dao, camera_motion_dict))
            trigger_rule_dynamic_executor = created_dynamic_executor
            trigger_rule_dynamic_executor_cache[rule.id] = trigger_rule_dynamic_executor
            future = actor_system.ask(trigger_rule_dynamic_executor, START, timeout=5)
            result = await asyncio.wait_for(future, timeout=300)
            logger.info("[%s] Dynamic executor executed, result: %s", execute_id, result)
        except asyncio.TimeoutError as exc:
            logger.error("[%s] Dynamic executor timeout: %s", execute_id, exc)
            self.trigger_rule_log_dao.update_status(
                execute_id,
                TriggerRuleLogStatus.FAILED,
                TriggerRuleLogReason.DYNAMIC_EXECUTE_FAILED,
                f"Dynamic executor timeout: {exc}",
            )
        except Exception as e:  # pylint: disable=broad-except
            logger.error("[%s] Dynamic executor error: %s", execute_id, e)
            self.trigger_rule_log_dao.update_status(
                execute_id,
                TriggerRuleLogStatus.FAILED,
                TriggerRuleLogReason.DYNAMIC_EXECUTE_FAILED,
                f"Dynamic executor error: {e}",
            )
        finally:
            if created_dynamic_executor:
                actor_system.tell(created_dynamic_executor, ActorExitRequest())
                trigger_rule_dynamic_executor_cache.pop(rule.id, None)

    async def execute_action(self, action: Action) -> bool:
        """Execute MCP action"""
        try:
            logger.info("Executing MCP action: %s on server %s", action.mcp_tool_name, action.mcp_server_name)

            result: CallToolResult = await self._tool_executor.execute_tool_by_params(
                action.mcp_client_id, action.mcp_tool_name,
                action.mcp_tool_input)

            logger.info("MCP action executed successfully: %s, result: %s", action.mcp_tool_name, result)
            return result.success

        except Exception as e:  # pylint: disable=broad-except
            logger.error(
                "Failed to execute MCP action %s: %s", action.mcp_tool_name, e)
            return False

    def _check_dynamic_action_is_running(self, rule_id: str) -> bool:
        """Check if dynamic action is running"""
        return rule_id in trigger_rule_dynamic_executor_cache
