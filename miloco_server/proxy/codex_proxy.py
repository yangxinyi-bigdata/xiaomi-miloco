# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Codex-backed LLM proxy using the local Codex CLI login."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, AsyncGenerator, Optional

import aiohttp
from openai.types.chat import ChatCompletion, ChatCompletionChunk
from openai.types.chat import ChatCompletionMessageParam, ChatCompletionToolParam

from miloco_server.proxy.codex_auth import (
    CODEX_RESPONSES_URL,
    CodexAuthError,
    CodexRefreshRequired,
    build_headers,
    proxy_for_url,
    refresh_access_token,
    refresh_tokens_if_needed,
)
from miloco_server.proxy.llm_proxy import LLMProxy


def _content_text(content: Any) -> str:
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str) and item.strip():
                parts.append(item.strip())
            elif isinstance(item, dict):
                text = str(item.get("text") or "").strip()
                if text:
                    parts.append(text)
        return "\n".join(parts).strip()
    return str(content or "").strip()


def _message_content_items(content: Any, role: str) -> list[dict[str, Any]]:
    if isinstance(content, str):
        text = content.strip()
        if not text:
            return []
        return [{"type": "output_text" if role == "assistant" else "input_text", "text": text}]
    if not isinstance(content, list):
        text = str(content or "").strip()
        return [{"type": "input_text", "text": text}] if text else []

    items: list[dict[str, Any]] = []
    for item in content:
        if not isinstance(item, dict):
            text = str(item or "").strip()
            if text:
                items.append({"type": "input_text", "text": text})
            continue
        item_type = str(item.get("type") or "").strip()
        if item_type in {"text", "input_text", "output_text"}:
            text = str(item.get("text") or "").strip()
            if text:
                items.append({
                    "type": "output_text" if role == "assistant" else "input_text",
                    "text": text,
                })
        elif item_type == "image_url":
            image_url = item.get("image_url") if isinstance(item.get("image_url"), dict) else {}
            url = str(image_url.get("url") or "").strip()
            if url:
                items.append({"type": "input_image", "image_url": url, "detail": "auto"})
        elif item_type == "input_image":
            url = str(item.get("image_url") or "").strip()
            if url:
                items.append({"type": "input_image", "image_url": url, "detail": item.get("detail") or "auto"})
    return items


def _messages_to_instructions(messages: list[ChatCompletionMessageParam]) -> str:
    instructions = []
    for message in messages:
        if not isinstance(message, dict) or str(message.get("role") or "") != "system":
            continue
        text = _content_text(message.get("content"))
        if text:
            instructions.append(text)
    return "\n\n".join(instructions).strip()


def _messages_to_input(messages: list[ChatCompletionMessageParam]) -> list[dict[str, Any]]:
    input_items: list[dict[str, Any]] = []
    for message in messages:
        if not isinstance(message, dict):
            continue
        role = str(message.get("role") or "user").strip().lower()
        if role == "system":
            continue
        if role == "tool":
            call_id = str(message.get("tool_call_id") or "").strip()
            if call_id:
                input_items.append({
                    "type": "function_call_output",
                    "call_id": call_id,
                    "output": _content_text(message.get("content")),
                })
            continue
        content_items = _message_content_items(message.get("content"), role)
        if content_items:
            input_items.append({
                "role": "assistant" if role == "assistant" else "user",
                "content": content_items,
            })
        for tool_call in message.get("tool_calls") or []:
            if not isinstance(tool_call, dict):
                continue
            function = tool_call.get("function") if isinstance(tool_call.get("function"), dict) else {}
            input_items.append({
                "type": "function_call",
                "call_id": str(tool_call.get("id") or "").strip(),
                "name": str(function.get("name") or "").strip(),
                "arguments": str(function.get("arguments") or "{}"),
            })
    return input_items


def _tools_to_responses_tools(tools: Optional[list[ChatCompletionToolParam]]) -> list[dict[str, Any]]:
    converted: list[dict[str, Any]] = []
    for tool in tools or []:
        if not isinstance(tool, dict) or tool.get("type") != "function":
            continue
        raw_function = tool.get("function")
        if isinstance(raw_function, dict):
            function = raw_function
        elif hasattr(raw_function, "model_dump"):
            function = raw_function.model_dump(exclude_none=True)
        else:
            function = {
                "name": getattr(raw_function, "name", ""),
                "description": getattr(raw_function, "description", ""),
                "parameters": getattr(raw_function, "parameters", None),
            }
        name = str(function.get("name") or "").strip()
        if not name:
            continue
        converted.append({
            "type": "function",
            "name": name,
            "description": str(function.get("description") or ""),
            "parameters": function.get("parameters") or {"type": "object", "properties": {}},
        })
    return converted


def _extract_output_text(payload: dict[str, Any]) -> str:
    text = payload.get("output_text")
    if isinstance(text, str) and text.strip():
        return text.strip()
    output = payload.get("output")
    if not isinstance(output, list):
        return ""
    parts: list[str] = []
    for item in output:
        if not isinstance(item, dict):
            continue
        content = item.get("content")
        if isinstance(content, list):
            for entry in content:
                if isinstance(entry, dict) and entry.get("type") in {"output_text", "text"}:
                    value = str(entry.get("text") or "").strip()
                    if value:
                        parts.append(value)
    return "\n".join(parts).strip()


def _chunk(
    *,
    model: str,
    content: Optional[str] = None,
    tool_calls: Optional[list[dict[str, Any]]] = None,
    finish_reason: Optional[str] = None,
) -> ChatCompletionChunk:
    delta: dict[str, Any] = {}
    if content is not None:
        delta["content"] = content
    if tool_calls:
        delta["tool_calls"] = tool_calls
    return ChatCompletionChunk(
        id=f"codex-{int(time.time() * 1000)}",
        object="chat.completion.chunk",
        created=int(time.time()),
        model=model,
        choices=[{"index": 0, "delta": delta, "finish_reason": finish_reason}],
    )


def _completion(
    *,
    model: str,
    content: str,
    tool_calls: list[dict[str, Any]],
    finish_reason: str,
) -> ChatCompletion:
    message: dict[str, Any] = {"role": "assistant", "content": content}
    if tool_calls:
        message["tool_calls"] = [
            {
                "id": call.get("id"),
                "type": "function",
                "function": call.get("function"),
            }
            for call in tool_calls
        ]
    return ChatCompletion(
        id=f"codex-{int(time.time() * 1000)}",
        object="chat.completion",
        created=int(time.time()),
        model=model,
        choices=[{"index": 0, "message": message, "finish_reason": finish_reason}],
    )


class CodexProxy(LLMProxy):
    """LLM proxy that talks to the Codex backend with local Codex credentials."""

    def __init__(self, model_name: str, codex_home: Optional[Path] = None):
        super().__init__(model_name)
        self.codex_home = Path(codex_home).expanduser() if codex_home else None

    def __str__(self) -> str:
        return f"CodexProxy(model_name={self.model_name})"

    def _build_payload(
        self,
        messages: list[ChatCompletionMessageParam],
        tools: Optional[list[ChatCompletionToolParam]],
    ) -> dict[str, Any]:
        instructions = _messages_to_instructions(messages) or "你是一个简洁、准确的 AI 助手。"
        converted_tools = _tools_to_responses_tools(tools)
        return {
            "model": self.model_name,
            "instructions": instructions,
            "input": _messages_to_input(messages),
            "store": False,
            "stream": True,
            "tools": converted_tools,
            "tool_choice": "auto",
            "parallel_tool_calls": True,
            "include": [],
        }

    async def _stream_response_json(
        self,
        payload: dict[str, Any],
        auth_state: dict[str, Any],
        session: Optional[aiohttp.ClientSession] = None,
        timeout_seconds: float = 60.0,
    ) -> AsyncGenerator[dict[str, Any], None]:
        timeout = aiohttp.ClientTimeout(total=None, sock_read=timeout_seconds)
        owns_session = session is None
        client = session or aiohttp.ClientSession(timeout=timeout)
        request_kwargs: dict[str, Any] = {"headers": build_headers(auth_state), "json": payload}
        proxy_url = proxy_for_url(CODEX_RESPONSES_URL, self.codex_home)
        if proxy_url:
            request_kwargs["proxy"] = proxy_url
        buffer = ""
        try:
            async with client.post(CODEX_RESPONSES_URL, **request_kwargs) as resp:
                if resp.status == 401:
                    raise CodexRefreshRequired("Codex access_token 已失效")
                if resp.status >= 400:
                    detail = await resp.text()
                    raise RuntimeError(f"HTTP {resp.status}: {detail[:500]}")
                async for raw_chunk in resp.content.iter_any():
                    text = raw_chunk.decode("utf-8", errors="ignore")
                    if not text:
                        continue
                    buffer += text
                    while "\n" in buffer:
                        line, buffer = buffer.split("\n", 1)
                        line = line.strip()
                        if not line.startswith("data:"):
                            continue
                        raw = line[5:].strip()
                        if not raw or raw == "[DONE]":
                            continue
                        try:
                            item = json.loads(raw)
                        except json.JSONDecodeError:
                            continue
                        if isinstance(item, dict):
                            yield item
        finally:
            if owns_session:
                await client.close()

    @staticmethod
    def _event_to_function_call(event: dict[str, Any]) -> Optional[dict[str, Any]]:
        item = event.get("item") if isinstance(event.get("item"), dict) else event
        item_type = str(item.get("type") or event.get("type") or "").strip()
        if "function_call" not in item_type:
            return None
        name = str(item.get("name") or event.get("name") or "").strip()
        arguments = item.get("arguments", event.get("arguments", "{}"))
        call_id = str(item.get("call_id") or item.get("id") or event.get("call_id") or event.get("id") or "").strip()
        if not name or not call_id:
            return None
        return {
            "id": call_id,
            "type": "function",
            "function": {
                "name": name,
                "arguments": arguments if isinstance(arguments, str) else json.dumps(arguments, ensure_ascii=False),
            },
        }

    async def _collect_events(
        self,
        payload: dict[str, Any],
        timeout_seconds: float,
    ) -> tuple[str, list[dict[str, Any]]]:
        state = await refresh_tokens_if_needed(home=self.codex_home)
        if not state.get("logged_in"):
            raise CodexAuthError("未检测到本机可用的 Codex 凭据")
        text_parts: list[str] = []
        tool_calls_by_id: dict[str, dict[str, Any]] = {}
        for attempt in range(2):
            try:
                async for event in self._stream_response_json(payload, state, timeout_seconds=timeout_seconds):
                    event_type = str(event.get("type") or "")
                    if event_type.endswith("output_text.delta"):
                        delta = event.get("delta")
                        if isinstance(delta, str):
                            text_parts.append(delta)
                        continue
                    call = self._event_to_function_call(event)
                    if call:
                        tool_calls_by_id[call["id"]] = call
                        continue
                    text = _extract_output_text(event)
                    if text and not text_parts:
                        text_parts.append(text)
                break
            except CodexRefreshRequired:
                if attempt >= 1:
                    raise CodexAuthError("刷新 Codex 凭据后仍然鉴权失败")
                state = await refresh_access_token(home=self.codex_home)
        return "".join(text_parts).strip(), list(tool_calls_by_id.values())

    async def async_call_llm(
        self,
        messages: list[ChatCompletionMessageParam],
        tools: Optional[list[ChatCompletionToolParam]] = None,
    ) -> dict[str, Any]:
        try:
            content, tool_calls = await self._collect_events(self._build_payload(messages, tools), 60.0)
            finish_reason = "tool_calls" if tool_calls else "stop"
            completion = _completion(
                model=self.model_name,
                content=content,
                tool_calls=tool_calls,
                finish_reason=finish_reason,
            )
            return {"success": True, "response": completion, "content": content}
        except Exception as exc:  # pylint: disable=broad-exception-caught
            return {"success": False, "error": str(exc)}

    async def async_call_llm_stream(
        self,
        messages: list[ChatCompletionMessageParam],
        tools: Optional[list[ChatCompletionToolParam]] = None,
    ) -> AsyncGenerator[dict[str, Any], None]:
        try:
            payload = self._build_payload(messages, tools)
            state = await refresh_tokens_if_needed(home=self.codex_home)
            if not state.get("logged_in"):
                raise CodexAuthError("未检测到本机可用的 Codex 凭据")
            tool_calls_by_id: dict[str, dict[str, Any]] = {}
            for attempt in range(2):
                try:
                    async for event in self._stream_response_json(payload, state, timeout_seconds=60.0):
                        event_type = str(event.get("type") or "")
                        if event_type.endswith("output_text.delta"):
                            delta = event.get("delta")
                            if isinstance(delta, str) and delta:
                                yield {
                                    "success": True,
                                    "chunk": _chunk(model=self.model_name, content=delta),
                                }
                            continue
                        call = self._event_to_function_call(event)
                        if call:
                            tool_calls_by_id[call["id"]] = call
                    break
                except CodexRefreshRequired:
                    if attempt >= 1:
                        raise CodexAuthError("刷新 Codex 凭据后仍然鉴权失败")
                    state = await refresh_access_token(home=self.codex_home)

            tool_calls = list(tool_calls_by_id.values())
            if tool_calls:
                delta_calls = [
                    {
                        "index": index,
                        "id": call.get("id"),
                        "type": "function",
                        "function": call.get("function"),
                    }
                    for index, call in enumerate(tool_calls)
                ]
                yield {
                    "success": True,
                    "chunk": _chunk(
                        model=self.model_name,
                        tool_calls=delta_calls,
                        finish_reason="tool_calls",
                    ),
                }
            else:
                yield {"success": True, "chunk": _chunk(model=self.model_name, finish_reason="stop")}
        except Exception as exc:  # pylint: disable=broad-exception-caught
            yield {"success": False, "error": str(exc)}
