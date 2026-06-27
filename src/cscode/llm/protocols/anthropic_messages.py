"""Anthropic Messages API protocol adapter.

Translates between the internal LLMRequest/LLMEvent model and
the Anthropic Messages API wire format.

Protocol: anthropic-messages
Endpoint: POST /v1/messages
Auth: x-api-key header
Streaming: SSE with event: / data: pairs
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import httpx

from cscode.llm.route import AuthScheme, Route
from cscode.llm.types import LLMRequest, _ProtocolAdapter
from cscode.schema.events import (
    Finish,
    LLMEvent,
    TextDelta,
    TextEnded,
    TextStarted,
    ToolCallDelta,
    ToolCallEnded,
    ToolCallStarted,
)
from cscode.schema.ids import ToolCallID
from cscode.schema.messages import (
    MediaPart,
    Message,
    MessageRole,
    TextPart,
    ToolCallPart,
    ToolResultPart,
)


class AnthropicProtocolAdapter(_ProtocolAdapter):
    """Protocol adapter for Anthropic Messages API."""

    async def complete(
        self,
        route: Route,
        request: LLMRequest,
        client: httpx.AsyncClient,
    ) -> dict[str, Any]:
        """Non-streaming completion via POST /v1/messages."""
        payload = self._build_request(request, stream=False)
        headers = self._build_headers(route)
        url = f"{route.endpoint.url.rstrip('/')}/messages"

        response = await client.post(url, json=payload, headers=headers)
        response.raise_for_status()
        data = response.json()

        return self._parse_complete_response(data)

    async def stream(
        self,
        route: Route,
        request: LLMRequest,
        client: httpx.AsyncClient,
    ) -> AsyncIterator[LLMEvent]:
        """Streaming via POST /v1/messages with stream=True.

        Anthropic uses SSE with event:/data: pairs. Each logical SSE
        message spans two lines: event: <type> then data: <json>.
        We read raw bytes and parse line-by-line.
        """
        payload = self._build_request(request, stream=True)
        headers = self._build_headers(route)
        url = f"{route.endpoint.url.rstrip('/')}/messages"

        tc_state: dict[str, Any] = {}
        block_type: str = ""

        async with client.stream("POST", url, json=payload, headers=headers) as response:
            response.raise_for_status()

            buffer = ""
            current_event = ""

            async for chunk in response.aiter_bytes():
                buffer += chunk.decode("utf-8")

                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    line = line.strip()

                    if line.startswith("event: "):
                        current_event = line[7:]
                    elif line.startswith("data: "):
                        data_str = line[6:]
                        if not data_str:
                            continue

                        try:
                            data = json.loads(data_str)
                        except json.JSONDecodeError:
                            continue

                        async for event in self._process_sse(
                            current_event, data, tc_state, block_type
                        ):
                            yield event

    async def _process_sse(
        self,
        event_type: str,
        data: dict[str, Any],
        tc_state: dict[str, Any],
        _block_type: str,  # reserved for future block type tracking
    ) -> AsyncIterator[LLMEvent]:
        """Process a single SSE event pair (event: + data:)."""

        match event_type:
            case "message_start":
                yield TextStarted()

            case "content_block_start":
                block = data.get("content_block", {})
                bt = block.get("type", "")
                if bt == "text":
                    text = block.get("text", "")
                    if text:
                        yield TextDelta(text=text)
                elif bt == "tool_use":
                    tc_state["id"] = block.get("id", "")
                    tc_state["name"] = block.get("name", "")
                    tc_state["args"] = ""
                    yield ToolCallStarted(
                        tool_call_id=ToolCallID(tc_state.get("id", "")),
                        name=tc_state.get("name", ""),
                    )

            case "content_block_delta":
                delta = data.get("delta", {})
                dt = delta.get("type", "")
                if dt == "text_delta":
                    text = delta.get("text", "")
                    if text:
                        yield TextDelta(text=text)
                elif dt == "input_json_delta":
                    partial = delta.get("partial_json", "")
                    if partial:
                        tc_state["args"] = tc_state.get("args", "") + partial
                        yield ToolCallDelta(
                            tool_call_id=ToolCallID(tc_state.get("id", "")),
                            args_text=partial,
                        )

            case "content_block_stop":
                if tc_state.get("args") is not None:
                    args_raw = tc_state.get("args", "")
                    try:
                        parsed: dict[str, object] = json.loads(args_raw) if args_raw else {}
                    except json.JSONDecodeError:
                        parsed = {"_raw": args_raw}
                    yield ToolCallEnded(
                        tool_call_id=ToolCallID(tc_state.get("id", "")),
                        name=tc_state.get("name", ""),
                        args=parsed,
                    )
                else:
                    yield TextEnded(full_text="")

            case "message_delta":
                delta = data.get("delta", {})
                stop_reason = delta.get("stop_reason", "")
                usage = data.get("usage", {})

                finish = {"end_turn": "stop", "tool_use": "tool_use", "max_tokens": "length"}.get(
                    stop_reason, stop_reason or "stop"
                )

                mapped_usage = None
                if usage:
                    mapped_usage = {
                        "prompt_tokens": usage.get("input_tokens", 0),
                        "completion_tokens": usage.get("output_tokens", 0),
                    }

                yield Finish(finish_reason=finish, usage=mapped_usage)

            case "message_stop" | "ping":
                pass

    # ─── Helpers ───────────────────────────────────────────────────

    def _build_headers(self, route: Route) -> dict[str, str]:
        """Build HTTP headers for Anthropic API."""
        headers: dict[str, str] = {
            "Content-Type": "application/json",
            "anthropic-version": "2023-06-01",
        }
        if route.auth.scheme == AuthScheme.HEADER:
            headers[route.auth.header_name] = route.auth.value
        elif route.auth.scheme == AuthScheme.BEARER and route.auth.value:
            headers["x-api-key"] = route.auth.value
        return headers

    def _build_request(self, request: LLMRequest, stream: bool) -> dict[str, Any]:
        """Build the Anthropic-compatible request payload."""
        system_text = self._extract_system(request.messages)

        payload: dict[str, Any] = {
            "model": request.model,
            "messages": self._serialize_messages(request.messages),
            "max_tokens": request.options.max_tokens or 8192,
            "stream": stream,
        }

        if system_text:
            payload["system"] = system_text

        if request.tools:
            payload["tools"] = [
                {
                    "name": t.name,
                    "description": t.description,
                    "input_schema": t.input_schema,
                }
                for t in request.tools
            ]

        return payload

    def _extract_system(self, messages: tuple[Message, ...]) -> str:
        """Extract system prompt from messages."""
        texts: list[str] = []
        for msg in messages:
            if msg.role == MessageRole.SYSTEM:
                texts.append(msg.content)
        return "\n".join(texts)

    def _serialize_messages(self, messages: tuple[Message, ...]) -> list[dict[str, Any]]:
        """Serialize messages to Anthropic API format."""
        result: list[dict[str, Any]] = []
        for msg in messages:
            if msg.role == MessageRole.SYSTEM:
                continue
            elif msg.role == MessageRole.USER:
                result.append(self._serialize_user(msg))
            elif msg.role == MessageRole.ASSISTANT:
                result.append(self._serialize_assistant(msg))
            elif msg.role == MessageRole.TOOL:
                for part in msg.parts:
                    if isinstance(part, ToolResultPart):
                        result.append({
                            "role": "user",
                            "content": [
                                {
                                    "type": "tool_result",
                                    "tool_use_id": part.tool_call_id,
                                    "content": part.result,
                                    "is_error": part.is_error,
                                }
                            ],
                        })
        return result

    def _serialize_user(self, msg: Message) -> dict[str, Any]:
        """Serialize a user message."""
        parts = list(msg.parts)
        media_parts = [p for p in parts if isinstance(p, MediaPart)]
        if not media_parts:
            return {"role": "user", "content": msg.content}

        content: list[dict[str, Any]] = []
        for part in parts:
            match part:
                case TextPart(text=t):
                    content.append({"type": "text", "text": t})
                case MediaPart(media_type=m, data=d):
                    content.append({
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": m or "image/png",
                            "data": d,
                        },
                    })
        return {"role": "user", "content": content}

    def _serialize_assistant(self, msg: Message) -> dict[str, Any]:
        """Serialize an assistant message."""
        content: list[dict[str, Any]] = []
        for part in msg.parts:
            match part:
                case TextPart(text=t):
                    if t:
                        content.append({"type": "text", "text": t})
                case ToolCallPart(tool_call_id=i, name=n, args=a):
                    content.append({
                        "type": "tool_use",
                        "id": i,
                        "name": n,
                        "input": a,
                    })

        entry: dict[str, Any] = {"role": "assistant"}
        entry["content"] = content if content else ""
        return entry

    def _parse_complete_response(self, data: dict[str, Any]) -> dict[str, Any]:
        """Parse a non-streaming response."""
        content_text = ""
        for block in data.get("content", []):
            if block.get("type") == "text":
                content_text += block.get("text", "")

        usage = data.get("usage", {})
        mapped_usage = {
            "prompt_tokens": usage.get("input_tokens", 0),
            "completion_tokens": usage.get("output_tokens", 0),
        }

        return {
            "content": content_text,
            "finish_reason": "stop",
            "usage": mapped_usage,
            "model": data.get("model", ""),
        }
