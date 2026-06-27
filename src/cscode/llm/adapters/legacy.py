"""LegacyProviderAdapter — wraps old LLMProvider into LLMService interface.

Bridge between the old provider system (providers/base.py) and the new
typed LLM layer (schema.Message, LLMService, LLMEvent).

This adapter is the transition layer. Once all providers are rewritten
to use the new Route system, this adapter will be removed.
"""

from __future__ import annotations

import json
import time
from collections.abc import AsyncIterator
from typing import Any

from cscode.llm.service import LLMResponse, LLMService, ToolExecution
from cscode.providers.base import LLMProvider, LLMResult
from cscode.schema.errors import LLMError, LLMErrorReason
from cscode.schema.events import (
    Finish,
    LLMEvent,
    Pending,
    TextDelta,
    TextEnded,
    TextStarted,
    ToolCallDelta,
    ToolCallEnded,
    ToolCallStarted,
)
from cscode.schema.events import (
    ToolFailure as EventToolFailure,
)
from cscode.schema.events import (
    ToolResult as EventToolResult,
)
from cscode.schema.ids import ModelID, ToolCallID
from cscode.schema.messages import (
    Message as SchemaMessage,
)
from cscode.schema.messages import (
    MessageRole,
    TextPart,
    ToolCallPart,
)
from cscode.schema.options import GenerationOptions
from cscode.schema.tool import ToolChoice
from cscode.tools2.base import Tool, ToolResult
from cscode.tools2.registry import ToolRegistry


class LegacyProviderAdapter(LLMService):
    """Adapts old LLMProvider + ToolRegistry into LLMService.

    Usage:
        adapter = LegacyProviderAdapter(old_provider, tools2_registry)
        response = await adapter.generate(
            model="gpt-4o",
            messages=[Message.user("Hello")],
            tools=[ReadTool(), BashTool()],
        )
    """

    def __init__(
        self,
        provider: LLMProvider,
        registry: ToolRegistry | None = None,
    ) -> None:
        self._provider = provider
        self._registry = registry or ToolRegistry()

    # ── helpers: schema → old format ──────────────────────────────

    def _to_old_messages(self, messages: list[SchemaMessage]) -> list[Any]:
        """Convert schema.Message list to old Message list format.

        Old Message expects a single 'content' string and optional
        'tool_calls' list. We merge all text parts into content and
        extract tool_calls from ToolCallPart.
        """
        from cscode.core.messages import Message as OldMessage
        from cscode.core.messages import MessageRole as OldRole

        old_msgs: list[OldMessage] = []
        for msg in messages:
            content_parts: list[str] = []
            tool_calls: list[dict[str, object]] = []
            for part in msg.parts:
                match part:
                    case TextPart(text=t):
                        content_parts.append(t)
                    case ToolCallPart(tool_call_id=i, name=n, args=a):
                        tool_calls.append({
                            "id": i,
                            "type": "function",
                            "function": {
                                "name": n,
                                "arguments": json.dumps(a, ensure_ascii=False),
                            },
                        })

            role = OldRole.SYSTEM if msg.role == MessageRole.SYSTEM else (
                OldRole.USER if msg.role == MessageRole.USER else (
                    OldRole.ASSISTANT if msg.role == MessageRole.ASSISTANT else OldRole.TOOL
                )
            )
            old_msg = OldMessage(
                role=role,
                content="".join(content_parts),
            )
            if tool_calls:
                old_msg.tool_calls = tool_calls
            old_msgs.append(old_msg)
        return old_msgs

    def _to_old_tools(self, tools: list[Tool[Any, Any]]) -> list[dict[str, object]]:
        """Convert tools2.Tool list to old tool dict format.

        Old provider expects list[dict] with OpenAI-compatible format.
        """
        old_tools: list[dict[str, object]] = []
        for tool in tools:
            defn = tool.to_definition()
            old_tools.append({
                "type": "function",
                "function": {
                    "name": defn.name,
                    "description": defn.description,
                    "parameters": defn.input_schema,
                },
            })
        return old_tools

    def _register_tools(self, tools: list[Tool[Any, Any]]) -> None:
        """Ensure tools are registered in the registry."""
        for tool in tools:
            if self._registry.get(tool.name) is None:
                self._registry.register(tool)

    # ── helpers: old format → schema ──────────────────────────────

    @staticmethod
    def _tool_calls_from_result(
        result: LLMResult,
    ) -> list[tuple[str, str, dict[str, object]]]:
        """Extract (tool_call_id, name, args) from old LLMResult."""
        if not result.tool_calls:
            return []
        extracted: list[tuple[str, str, dict[str, object]]] = []
        for tc in result.tool_calls:
            if not isinstance(tc, dict):
                continue
            tc_id = str(tc.get("id", ""))
            fn = tc.get("function", {})
            name = str(fn.get("name", "")) if isinstance(fn, dict) else ""
            args_raw = fn.get("arguments", "{}") if isinstance(fn, dict) else "{}"
            if isinstance(args_raw, str):
                try:
                    args: dict[str, object] = json.loads(args_raw) if args_raw.strip() else {}
                except json.JSONDecodeError:
                    args = {"_parse_error": args_raw}
            elif isinstance(args_raw, dict):
                args = args_raw
            else:
                args = {}
            extracted.append((tc_id, name, args))
        return extracted

    # ── LLMService implementation ─────────────────────────────────

    async def generate(
        self,
        model: ModelID,
        messages: list[SchemaMessage],
        *,
        tools: list[Tool[Any, Any]] | None = None,
        tool_choice: ToolChoice | None = None,
        system: str | None = None,
        options: GenerationOptions | None = None,
        max_tool_rounds: int | None = 50,
    ) -> LLMResponse:
        # Register tools so they can be settled
        tool_list = tools or []
        self._register_tools(tool_list)

        # Prepare messages with optional system prompt
        working_messages = list(messages)
        if system:
            working_messages.insert(0, SchemaMessage.system(system))

        # Convert to old format for provider call
        old_messages = self._to_old_messages(working_messages)
        old_tools = self._to_old_tools(tool_list) if tool_list else None

        all_executions: list[ToolExecution] = []
        total_usage: dict[str, int] = {}
        final_content = ""
        final_model = ""
        finish_reason = ""

        tool_rounds = 0

        while True:
            # Call the old provider
            try:
                result: LLMResult = await self._provider.complete(
                    old_messages,
                    tools=old_tools if old_tools else None,
                )
            except Exception as e:
                raise LLMError(
                    module="LLM",
                    method="generate",
                    reason=LLMErrorReason.PROVIDER_INTERNAL,
                    message=str(e),
                ) from e

            # Track model and usage
            final_model = result.model or str(model)
            if result.usage:
                for k, v in result.usage.items():
                    total_usage[k] = total_usage.get(k, 0) + v

            # Extract content and tool calls
            content = result.content or ""
            final_content += content
            tool_calls = self._tool_calls_from_result(result)

            # Check stop conditions
            if not tool_calls:
                finish_reason = result.finish_reason or "stop"
                break

            if max_tool_rounds is not None and tool_rounds >= max_tool_rounds:
                finish_reason = "max_rounds"
                break

            tool_rounds += 1

            # Add assistant message with tool calls to old format
            # (so the provider sees it in the next round)
            from cscode.core.messages import Message as OldMessage
            from cscode.core.messages import MessageRole as OldRole

            # Build old format tool_calls for the assistant message
            old_tc_list: list[dict[str, object]] = []
            for tc_id, tc_name, tc_args in tool_calls:
                old_tc_list.append({
                    "id": tc_id,
                    "type": "function",
                    "function": {
                        "name": tc_name,
                        "arguments": json.dumps(tc_args, ensure_ascii=False),
                    },
                })
            old_messages.append(OldMessage(
                role=OldRole.ASSISTANT,
                content=content,
                tool_calls=old_tc_list if old_tc_list else None,
            ))

            # Settle each tool call
            for tc_id, tc_name, tc_args in tool_calls:
                start = time.monotonic()
                tool_result: ToolResult[Any] = await self._settle_one(tc_name, tc_args)
                elapsed = (time.monotonic() - start) * 1000

                raw_output: object = tool_result.data if tool_result.success else (tool_result.error or "")
                output = str(raw_output) if raw_output is not None else ""
                all_executions.append(ToolExecution(
                    name=tc_name,
                    tool_call_id=tc_id,
                    input=tc_args,
                    output=output,
                    success=tool_result.success,
                    duration_ms=elapsed,
                ))

                # Add tool result as old-format tool message
                old_messages.append(OldMessage(
                    role=OldRole.TOOL,
                    content=output,
                    tool_call_id=tc_id,
                    name=tc_name,
                ))

        return LLMResponse(
            content=final_content,
            tool_executions=tuple(all_executions),
            usage=total_usage if total_usage else None,
            model=final_model,
            finish_reason=finish_reason,
        )

    async def _settle_one(
        self,
        name: str,
        args: dict[str, object],
    ) -> ToolResult[Any]:
        """Execute a single tool via the registry."""
        tool = self._registry.get(name)
        if tool is None:
            return ToolResult[Any](
                success=False,
                error=f"Unknown tool: {name}",
            )
        try:
            validated = tool.input_schema.model_validate(args)
            return await tool.execute(validated)
        except Exception as e:
            return ToolResult[Any](
                success=False,
                error=tool.format_error(e),
            )

    # ── Stream ─────────────────────────────────────────────────────

    async def stream(
        self,
        model: ModelID,
        messages: list[SchemaMessage],
        *,
        tools: list[Tool[Any, Any]] | None = None,
        tool_choice: ToolChoice | None = None,
        system: str | None = None,
        options: GenerationOptions | None = None,
    ) -> AsyncIterator[LLMEvent]:
        """Stream a single request as LLMEvent sequence.

        This does NOT auto-loop. One call = one API request.
        For tool loop, use generate().
        """
        tool_list = tools or []
        self._register_tools(tool_list)

        working_messages = list(messages)
        if system:
            working_messages.insert(0, SchemaMessage.system(system))

        old_messages = self._to_old_messages(working_messages)
        old_tools = self._to_old_tools(tool_list) if tool_list else None

        yield Pending()

        # We use the old streaming interface and convert to events
        # Old stream returns AsyncIterator[str] (just text chunks)
        try:
            # Collect tool call info from the first complete() call
            # (old stream() only yields text; we need complete() for tool calls)
            # Strategy: use complete() for tool calls, stream() for text

            # For the initial stream version: do a non-stream complete
            # to detect tool calls, then yield appropriate events
            result = await self._provider.complete(
                old_messages,
                tools=old_tools if old_tools else None,
            )

            tool_calls = self._tool_calls_from_result(result)
            content = result.content or ""

            # Yield text events
            if content:
                yield TextStarted()
                yield TextDelta(text=content)
                yield TextEnded(full_text=content)

            # Yield tool call events
            for tc_id, tc_name, tc_args in tool_calls:
                yield ToolCallStarted(
                    tool_call_id=ToolCallID(tc_id),
                    name=tc_name,
                )
                yield ToolCallDelta(
                    tool_call_id=ToolCallID(tc_id),
                    args_text=json.dumps(tc_args),
                )
                yield ToolCallEnded(
                    tool_call_id=ToolCallID(tc_id),
                    name=tc_name,
                    args=tc_args,
                )

                # Settle and yield result
                tool_result = await self._settle_one(tc_name, tc_args)
                if tool_result.success:
                    yield EventToolResult(
                        tool_call_id=ToolCallID(tc_id),
                        result=tool_result.data or "",
                    )
                else:
                    yield EventToolFailure(
                        tool_call_id=ToolCallID(tc_id),
                        error=tool_result.error or "Unknown error",
                    )

            # Detect errors
            finish_reason = result.finish_reason or ("tool_use" if tool_calls else "stop")
            # Check for provider-level errors

            yield Finish(
                finish_reason=finish_reason,
                usage=result.usage,
            )

        except Exception as e:
            from cscode.schema.events import Error as LLMEventError

            llm_err = LLMError(
                module="LLM",
                method="stream",
                reason=LLMErrorReason.PROVIDER_INTERNAL,
                message=str(e),
            )
            yield LLMEventError(error=llm_err)
