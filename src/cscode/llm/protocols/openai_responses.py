"""OpenAI Responses API protocol adapter.

Translates between the internal LLMRequest/LLMEvent model and
the OpenAI Responses API wire format.

Protocol: openai-responses
Endpoint: POST /v1/responses
Auth: Bearer token (Authorization header)
Streaming: SSE with structured event types (response.output_text.delta, etc.)
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
    ToolCallEnded,
    ToolCallStarted,
)
from cscode.schema.ids import ToolCallID
from cscode.utils.logging import get_logger

logger = get_logger(__name__)


class OpenAIResponsesProtocolAdapter(_ProtocolAdapter):
    """Protocol adapter for OpenAI Responses API."""

    async def complete(
        self,
        route: Route,
        request: LLMRequest,
        client: httpx.AsyncClient,
    ) -> dict[str, Any]:
        """Non-streaming completion via POST /v1/responses."""
        payload = self._build_request(request, stream=False)
        headers = self._build_headers(route)
        url = f"{route.endpoint.url.rstrip('/')}/responses"

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
        """Streaming via POST /v1/responses?stream=true.

        Responses API uses SSE events like:
          - response.output_text.delta
          - response.output_item.added
          - response.output_item.done
          - response.completed
        """
        payload = self._build_request(request, stream=True)
        headers = self._build_headers(route)
        url = f"{route.endpoint.url.rstrip('/')}/responses"

        async with client.stream("POST", url, json=payload, headers=headers) as response:
            response.raise_for_status()

            accumulated_text = ""
            tc_state: dict[str, Any] = {}

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

                async for event in self._process_sse_event(data, tc_state):
                    if isinstance(event, TextDelta):
                        accumulated_text += event.text
                    elif isinstance(event, TextEnded) and accumulated_text:
                        yield TextEnded(full_text=accumulated_text)
                        continue
                    elif isinstance(event, Finish) and accumulated_text:
                        yield TextEnded(full_text=accumulated_text)
                    yield event

    # ─── SSE Event Processing ─────────────────────────────────────

    async def _process_sse_event(
        self,
        data: dict[str, Any],
        tc_state: dict[str, Any] | None = None,
    ) -> AsyncIterator[LLMEvent]:
        """Process a single Responses API SSE event."""
        if tc_state is None:
            tc_state = {}

        event_type = data.get("type", "")

        match event_type:
            case "response.output_text.delta":
                delta = data.get("delta", "")
                if delta:
                    yield TextDelta(text=delta)

            case "response.output_item.added":
                item = data.get("item", {})
                item_type = item.get("type", "")
                if item_type == "tool_call":
                    tc_state["tool_call_id"] = ToolCallID(item.get("id", ""))
                    tc_state["name"] = item.get("name", "")
                    tc_state["args_text"] = ""
                    yield ToolCallStarted(
                        tool_call_id=tc_state["tool_call_id"],
                        name=tc_state["name"],
                    )
                elif item_type == "message":
                    yield TextStarted()

            case "response.output_item.done":
                item = data.get("item", {})
                item_type = item.get("type", "")
                if item_type == "tool_call":
                    args_raw = item.get("arguments", "")
                    try:
                        parsed_args: dict[str, Any] = json.loads(args_raw) if args_raw else {}
                    except json.JSONDecodeError:
                        parsed_args = {"_raw": args_raw}
                    yield ToolCallEnded(
                        tool_call_id=ToolCallID(item.get("id", "")),
                        name=item.get("name", ""),
                        args=parsed_args,
                    )

            case "response.completed":
                resp = data.get("response", {})
                status = resp.get("status", "")
                finish_reason = "stop"
                if status == "failed":
                    finish_reason = "error"
                elif status == "incomplete":
                    finish_reason = "length"

                usage_raw = resp.get("usage", {})
                mapped_usage = None
                if usage_raw:
                    mapped_usage = {
                        "prompt_tokens": usage_raw.get("input_tokens", 0),
                        "completion_tokens": usage_raw.get("output_tokens", 0),
                    }

                yield Finish(finish_reason=finish_reason, usage=mapped_usage)

            case _:
                # Skip unknown event types
                pass

    # ─── Response Parsing ─────────────────────────────────────────

    def _parse_complete_response(self, data: dict[str, Any]) -> dict[str, Any]:
        """Parse a non-streaming response into a standardized dict."""
        output = data.get("output", [])
        text_parts: list[str] = []
        has_tool_call = False

        for item in output:
            if item.get("type") == "message":
                content_items = item.get("content", [])
                for content in content_items:
                    ctype = content.get("type", "")
                    if ctype == "output_text":
                        text_parts.append(content.get("text", ""))
                    elif ctype == "tool_call":
                        has_tool_call = True

        content = "\n".join(text_parts)
        finish_reason = "tool_use" if has_tool_call else "stop"
        usage = data.get("usage")
        model = data.get("model", "")

        return {
            "content": content,
            "finish_reason": finish_reason,
            "usage": usage,
            "model": model,
        }

    # ─── Request Building ─────────────────────────────────────────

    def _build_request(self, request: LLMRequest, stream: bool) -> dict[str, Any]:
        """Build the OpenAI Responses API request payload.

        Responses API uses 'input' instead of 'messages'.
        """
        payload: dict[str, Any] = {
            "model": request.model,
            "input": self._serialize_input(request.messages),
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

    def _serialize_input(
        self, messages: tuple[Any, ...]
    ) -> list[dict[str, Any]]:
        """Serialize internal Message list to Responses API input format."""
        result: list[dict[str, Any]] = []
        for msg in messages:
            entry: dict[str, Any] = {"role": msg.role}
            entry["content"] = self._serialize_content(msg)
            result.append(entry)
        return result

    def _serialize_content(self, msg: Any) -> str | list[dict[str, Any]]:
        """Serialize message content.

        Simple text-only messages use a string; multi-part messages
        use an array of content items.
        """
        parts = list(getattr(msg, "parts", ()))
        if not parts:
            return str(getattr(msg, "content", ""))

        # Check for non-text parts
        has_media = any(
            getattr(p, "type", "") in ("media", "image_url", "tool_call", "tool_result", "reasoning")
            for p in parts
        )
        if not has_media:
            # All text parts — concatenate
            texts: list[str] = []
            for p in parts:
                if hasattr(p, "text"):
                    texts.append(p.text)
                elif hasattr(p, "text"):
                    texts.append(p.text)
            return "\n".join(texts)

        # Multi-part content
        content_items: list[dict[str, Any]] = []
        for p in parts:
            ptype = getattr(p, "type", "")
            if ptype in ("text", "system"):
                content_items.append({"type": "text", "text": getattr(p, "text", "")})
            elif ptype == "media":
                content_items.append({
                    "type": "media",
                    "media": {
                        "url": getattr(p, "data", ""),
                        "mime_type": getattr(p, "media_type", "image/png"),
                    },
                })
            else:
                content_items.append({"type": "text", "text": str(p)})
        return content_items

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
