"""OpenAI Chat Completions protocol adapter.

Translates between the internal LLMRequest/LLMEvent model and
the OpenAI Chat Completions API wire format.

Protocol: openai-chat | openai-compatible
Endpoint: POST /chat/completions
Auth: Bearer token (Authorization header)
Streaming: SSE with data: lines, terminated by [DONE]
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
from cscode.utils.logging import get_logger

logger = get_logger(__name__)


class OpenAIProtocolAdapter(_ProtocolAdapter):
    """Protocol adapter for OpenAI Chat Completions API."""

    async def complete(
        self,
        route: Route,
        request: LLMRequest,
        client: httpx.AsyncClient,
    ) -> dict[str, Any]:
        """Non-streaming completion via POST /chat/completions."""
        payload = self._build_request(request, stream=False)
        headers = self._build_headers(route)
        url = f"{route.endpoint.url.rstrip('/')}/chat/completions"

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
        """Streaming via POST /chat/completions with stream=True."""
        payload = self._build_request(request, stream=True)
        headers = self._build_headers(route)
        url = f"{route.endpoint.url.rstrip('/')}/chat/completions"

        async with client.stream("POST", url, json=payload, headers=headers) as response:
            if response.status_code >= 400:
                await response.aread()
            response.raise_for_status()
            content_type = (response.headers.get("content-type") or "").lower()

            if "text/event-stream" not in content_type:
                body = b""
                async for chunk in response.aiter_bytes():
                    body += chunk
                data = json.loads(body)

                yield TextStarted()
                choice = data.get("choices", [{}])[0]
                msg = choice.get("message", {})
                content = msg.get("content", "")
                if content:
                    yield TextDelta(text=content)
                    yield TextEnded(full_text=content)
                finish_reason = choice.get("finish_reason", "stop")
                usage = data.get("usage")
                yield Finish(
                    finish_reason=finish_reason,
                    usage={
                        "prompt_tokens": usage.get("prompt_tokens", 0),
                        "completion_tokens": usage.get("completion_tokens", 0),
                    }
                    if usage
                    else None,
                )
                return

            tool_calls_in_progress: dict[str, dict[str, Any]] = {}

            yield TextStarted()

            # Track accumulated text across SSE chunks (some providers emit
            # finish_reason on a chunk where content is already empty, wiping
            # accumulated assistant_text in _run_loop — this ensures TextEnded
            # carries the full accumulated text.)
            accumulated_text = ""

            async for line in response.aiter_lines():
                if not line.startswith("data: "):
                    continue
                data_str = line[6:].strip()
                if not data_str:
                    continue
                if data_str == "[DONE]":
                    break

                try:
                    data = json.loads(data_str)
                except json.JSONDecodeError:
                    continue

                choices = data.get("choices", [])
                if not choices:
                    continue

                delta = choices[0].get("delta", {})
                finish_reason = choices[0].get("finish_reason")

                # Text content (some providers e.g. MiniMax only populate
                # content after their reasoning phase — skip empty chunks)
                content = delta.get("content", "")
                if content:
                    accumulated_text += content
                    yield TextDelta(text=content)

                # Tool calls
                tc_delta = delta.get("tool_calls")
                if tc_delta:
                    for tc in tc_delta:
                        idx = tc.get("index", 0)
                        tc_id = tc.get("id", "")
                        fn = tc.get("function", {})

                        if idx not in tool_calls_in_progress:
                            tool_calls_in_progress[idx] = {
                                "tool_call_id": ToolCallID(tc_id or f"call_{idx}"),
                                "name": fn.get("name", ""),
                                "args_text": "",
                            }
                            yield ToolCallStarted(
                                tool_call_id=tool_calls_in_progress[idx]["tool_call_id"],
                                name=tool_calls_in_progress[idx]["name"],
                            )

                        args_chunk = fn.get("arguments", "")
                        if args_chunk:
                            tool_calls_in_progress[idx]["args_text"] += args_chunk
                            yield ToolCallDelta(
                                tool_call_id=tool_calls_in_progress[idx]["tool_call_id"],
                                args_text=args_chunk,
                            )

                if finish_reason:
                    # Use accumulated text instead of last chunk's content
                    # (some providers e.g. MiniMax send finish_reason on a
                    # chunk where content is already "")
                    yield TextEnded(full_text=accumulated_text)

                    # Emit completed tool calls
                    for tc_data in tool_calls_in_progress.values():
                        try:
                            parsed_args: dict[str, Any] = json.loads(tc_data["args_text"]) if tc_data["args_text"] else {}
                        except json.JSONDecodeError:
                            parsed_args = {"_raw": tc_data["args_text"]}
                        yield ToolCallEnded(
                            tool_call_id=tc_data["tool_call_id"],
                            name=tc_data["name"],
                            args=parsed_args,
                        )

                    usage = data.get("usage")
                    yield Finish(
                        finish_reason=finish_reason,
                        usage={
                            "prompt_tokens": usage.get("prompt_tokens", 0),
                            "completion_tokens": usage.get("completion_tokens", 0),
                        }
                        if usage
                        else None,
                    )

    # ─── Helpers ───────────────────────────────────────────────────

    def _build_headers(self, route: Route) -> dict[str, str]:
        """Build HTTP headers for the request."""
        headers: dict[str, str] = {
            "Content-Type": "application/json",
        }
        if route.auth.scheme == AuthScheme.BEARER and route.auth.value:
            headers["Authorization"] = f"Bearer {route.auth.value}"
        elif route.auth.scheme == AuthScheme.HEADER:
            headers[route.auth.header_name] = route.auth.value
        return headers

    def _build_request(self, request: LLMRequest, stream: bool) -> dict[str, Any]:
        """Build the OpenAI-compatible request payload."""
        payload: dict[str, Any] = {
            "model": request.model,
            "messages": self._serialize_messages(request.messages),
            "stream": stream,
            **self._build_generation_params(request),
        }

        if request.tools:
            payload["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": t.name,
                        "description": t.description,
                        "parameters": t.input_schema,
                    },
                }
                for t in request.tools
            ]

        return payload

    def _serialize_messages(self, messages: tuple[Message, ...]) -> list[dict[str, Any]]:
        """Serialize internal Message list to OpenAI API format."""
        result: list[dict[str, Any]] = []
        for msg in messages:
            if msg.role == MessageRole.SYSTEM:
                result.append({"role": "system", "content": msg.content})
            elif msg.role == MessageRole.USER:
                result.append(self._serialize_user_message(msg))
            elif msg.role == MessageRole.ASSISTANT:
                result.append(self._serialize_assistant_message(msg))
            elif msg.role == MessageRole.TOOL:
                for part in msg.parts:
                    if isinstance(part, ToolResultPart):
                        result.append({
                            "role": "tool",
                            "tool_call_id": part.tool_call_id,
                            "content": part.result,
                        })
        return result

    def _serialize_user_message(self, msg: Message) -> dict[str, Any]:
        """Serialize a user message, handling multi-part content."""
        parts = list(msg.parts)
        # Check if there are media parts
        media_parts = [p for p in parts if isinstance(p, MediaPart)]
        if not media_parts:
            # Simple text-only message
            return {"role": "user", "content": msg.content}

        # Multi-part content with media
        content: list[dict[str, Any]] = []
        for part in parts:
            match part:
                case TextPart(text=t):
                    content.append({"type": "text", "text": t})
                case MediaPart(media_type=m, data=d):
                    mime = m or "image/png"
                    if mime.startswith("image/"):
                        content.append({
                            "type": "image_url",
                            "image_url": {"url": f"data:{mime};base64,{d}"},
                        })
                    else:
                        content.append({"type": "text", "text": f"[{mime} attachment (base64, {len(d)} chars)]"})
        return {"role": "user", "content": content}

    def _serialize_assistant_message(self, msg: Message) -> dict[str, Any]:
        """Serialize an assistant message with optional tool calls."""
        text = msg.content
        tool_call_parts = [p for p in msg.parts if isinstance(p, ToolCallPart)]

        entry: dict[str, Any] = {"role": "assistant"}
        if text:
            entry["content"] = text
        else:
            entry["content"] = ""

        if tool_call_parts:
            entry["tool_calls"] = [
                {
                    "id": p.tool_call_id,
                    "type": "function",
                    "function": {
                        "name": p.name,
                        "arguments": json.dumps(p.args, ensure_ascii=False),
                    },
                }
                for p in tool_call_parts
            ]

        return entry

    def _build_generation_params(self, request: LLMRequest) -> dict[str, Any]:
        """Build generation parameter dict from options."""
        params: dict[str, Any] = {}
        opts = request.options
        if opts.temperature is not None:
            params["temperature"] = opts.temperature
        if opts.top_p is not None:
            params["top_p"] = opts.top_p
        if opts.max_tokens is not None:
            params["max_tokens"] = opts.max_tokens
        if opts.stop:
            params["stop"] = list(opts.stop)
        if opts.seed is not None:
            params["seed"] = opts.seed
        return params

    def _parse_complete_response(self, data: dict[str, Any]) -> dict[str, Any]:
        """Parse a non-streaming response into a standardized dict."""
        choice = data["choices"][0]
        msg = choice["message"]
        return {
            "content": msg.get("content") or "",
            "finish_reason": choice.get("finish_reason", ""),
            "usage": data.get("usage"),
            "model": data.get("model", ""),
        }
