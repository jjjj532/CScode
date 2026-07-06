"""AgentV2 — App-level Agent 封装 LLMClient + ToolRegistry。

实现了完整的 Agent Loop：

  1. Build messages from history + user input
  2. Send LLMRequest with tool definitions
  3. Collect TextDelta → content, ToolCallEnded → tool calls
  4. Settle tool calls via ToolRegistry.settle()
  5. Append results back to message list
  6. Loop until Finish or max tool rounds
  7. Return final content

架构: LLMClient(网络层) + ToolRegistryV2(工具调度)
"""

from __future__ import annotations

import inspect
from collections.abc import AsyncIterator, Callable
from typing import Any

from cscode.core.permission_v2 import Ruleset
from cscode.core.session import SessionV2
from cscode.core.sub_agent import SubAgentOrchestrator
from cscode.core.tool_registry import ToolRegistryV2
from cscode.llm.client import LLMClient
from cscode.llm.types import LLMRequest
from cscode.schema.events import (
    Error as LLMEventError,
)
from cscode.schema.events import (
    Finish,
    LLMEvent,
    TextDelta,
    TextEnded,
    ToolCallEnded,
)
from cscode.schema.ids import ModelID, ToolCallID
from cscode.schema.messages import (
    Message,
    MessageRole,
    TextPart,
    ToolCallPart,
)
from cscode.schema.options import GenerationOptions
from cscode.tools2.base import ToolResult as Tool2Result
from cscode.utils.logging import get_logger

logger = get_logger(__name__)


class AgentV2:
    """App-level Agent built on LLMClient + ToolRegistry.

    Provides a run() interface compatible with the legacy Agent,
    but uses the new layered architecture internally.

    Usage:
        agent = AgentV2(llm_client, tool_registry, system_prompt="...")
        result = await agent.run("Hello!")
    """

    def __init__(
        self,
        llm_client: LLMClient,
        tool_registry: ToolRegistryV2,
        max_tool_rounds: int = 20,
        system_prompt: str | None = None,
        permissions: list[Ruleset] | None = None,
    ) -> None:
        self._llm_client = llm_client
        self._tool_registry = tool_registry
        self._max_tool_rounds = max_tool_rounds
        self._system_prompt = system_prompt
        self._permissions = permissions

        # Materialize tool definitions + settle once
        mat = tool_registry.materialize(permissions=permissions)
        self._tool_definitions = mat.definitions
        self._settle = mat.settle

        # SubAgentOrchestrator for @tool mention processing
        self._sub_agent = SubAgentOrchestrator(tool_registry)

        logger.info(
            "AgentV2 initialized: model=%s tools=%d max_rounds=%d permissions=%s",
            llm_client.route.model,
            len(self._tool_definitions),
            max_tool_rounds,
            len(permissions) if permissions else None,
        )

    @property
    def llm_client(self) -> LLMClient:
        return self._llm_client

    @property
    def tool_registry(self) -> ToolRegistryV2:
        return self._tool_registry

    async def run(
        self,
        user_input: str,
        session: SessionV2 | None = None,
        on_event: Callable[[LLMEvent], Any] | None = None,
        generation_options: GenerationOptions | None = None,
    ) -> str:
        """Process a user prompt through the agent loop.

        Args:
            user_input: The user's prompt text.
            session: Optional SessionV2 for event-sourced persistence.
            on_event: Optional callback for streaming LLMEvents.
            generation_options: Optional generation parameters.

        Returns:
            The final assistant response text.
        """
        logger.info(
            "AgentV2.run: user_input_len=%d has_session=%s", len(user_input), session is not None
        )
        messages = self._build_messages(user_input, session)
        return await self._run_loop(messages, on_event, generation_options, session)

    async def run_with_messages(
        self,
        messages: list[Message],
        on_event: Callable[[LLMEvent], Any] | None = None,
        generation_options: GenerationOptions | None = None,
    ) -> str:
        """Run the agent loop on a pre-built message list.

        Unlike run() which builds messages from user_input + session,
        this method accepts a pre-built message list directly.
        The message list is modified in place (assistant + tool messages appended).

        Args:
            messages: Pre-built message list (modified in place).
            on_event: Optional callback for streaming LLMEvents.
            generation_options: Optional generation parameters.

        Returns:
            The final assistant response text.
        """
        logger.info("AgentV2.run_with_messages: messages=%d", len(messages))
        return await self._run_loop(messages, on_event, generation_options)

    async def _run_loop(
        self,
        messages: list[Message],
        on_event: Callable[[LLMEvent], Any] | None = None,
        generation_options: GenerationOptions | None = None,
        session: SessionV2 | None = None,
    ) -> str:
        """Shared inner agent loop used by run() and run_with_messages()."""
        model = ModelID(self._llm_client.route.model)
        logger.debug("_run_loop: start model=%s messages=%d", model, len(messages))
        options = generation_options or GenerationOptions()
        full_content = ""
        tool_round = 0

        # Process @tool mentions in user messages (single pass at start)
        messages = await self._sub_agent.process_messages(messages)

        while tool_round < self._max_tool_rounds:
            logger.debug(
                "_run_loop: tool_round=%d/%d messages=%d",
                tool_round + 1,
                self._max_tool_rounds,
                len(messages),
            )
            request = LLMRequest(
                model=model,
                messages=tuple(messages),
                tools=tuple(self._tool_definitions),
                options=options,
            )

            # ── Stream LLM response ──────────────────────────────
            assistant_parts: list[TextPart] = []
            assistant_text = ""
            tool_calls: list[ToolCallPart] = []

            async for event in self._llm_client.stream(request):
                if on_event is not None:
                    if inspect.iscoroutinefunction(on_event):
                        await on_event(event)
                    else:
                        on_event(event)

                match event:
                    case TextDelta(text=t):
                        assistant_text += t
                    case TextEnded(full_text=t):
                        logger.debug("_run_loop: TextEnded(full_text=%r) current_assistant=%r parts=%d", t, assistant_text, len(assistant_parts))
                        # Some providers (e.g. MiniMax) emit finish_reason on a
                        # chunk where content is already "" — in that case t is
                        # empty.  Don't overwrite the accumulated text.
                        if t:
                            assistant_text = t
                        if t or not assistant_parts:
                            assistant_parts.append(TextPart(text=t or assistant_text))
                    case ToolCallEnded(tool_call_id=tcid, name=n, args=a):
                        tool_calls.append(
                            ToolCallPart(
                                tool_call_id=ToolCallID(tcid),
                                name=n,
                                args=a,
                            )
                        )
                    case Finish():
                        break
                    case LLMEventError(error=e):
                        logger.error(
                            "_run_loop: llm error tool_round=%d error=%s", tool_round + 1, e.message
                        )
                        return f"LLM error: {e.message}"

            if not assistant_text and not tool_calls:
                logger.warning(
                    "_run_loop: streaming returned empty for round=%d, trying non-streaming fallback",
                    tool_round + 1,
                )
                try:
                    raw = await self._llm_client.generate(request)
                    if raw.content:
                        assistant_text = raw.content
                        assistant_parts.append(TextPart(text=raw.content))
                        if on_event is not None:
                            evt: LLMEvent = TextDelta(text=raw.content)
                            await on_event(evt) if hasattr(on_event, "__await__") else on_event(evt)
                            evt = TextEnded(full_text=raw.content)
                            await on_event(evt) if hasattr(on_event, "__await__") else on_event(evt)
                except Exception as fallback_err:
                    logger.error("_run_loop: non-streaming fallback also failed: %s", fallback_err)

            # ── Build assistant message ──────────────────────────
            all_parts: list[TextPart | ToolCallPart] = list(assistant_parts)
            all_parts.extend(tool_calls)

            if all_parts:
                assistant_msg = Message(
                    role=MessageRole.ASSISTANT,
                    parts=tuple(all_parts),
                )
                messages.append(assistant_msg)

            full_content += assistant_text

            # Persist to session if provided
            if session is not None and assistant_text:
                await session.add_text(assistant_text)

            # ── No tool calls → done ─────────────────────────────
            if not tool_calls:
                logger.debug("_run_loop: no tool calls, finishing after round=%d", tool_round + 1)
                break

            # ── Settle tool calls ────────────────────────────────
            logger.info(
                "_run_loop: tool_round=%d tool_calls=%s",
                tool_round + 1,
                [tc.name for tc in tool_calls],
            )
            for tc in tool_calls:
                tool_result: Tool2Result[Any] = await self._settle(tc.name, dict(tc.args))

                logger.debug(
                    "_run_loop: tool=%s success=%s result_len=%d",
                    tc.name,
                    tool_result.success,
                    len(str(tool_result.data or tool_result.error or "")),
                )
                is_error = not tool_result.success
                error_str = tool_result.error or ""
                data_str = str(tool_result.data) if tool_result.data is not None else ""
                result_str: str = error_str if is_error else data_str

                from cscode.schema.messages import ToolResultPart

                tool_msg = Message(
                    role=MessageRole.TOOL,
                    parts=(
                        ToolResultPart(
                            tool_call_id=tc.tool_call_id,
                            name=tc.name,
                            result=result_str,
                            is_error=is_error,
                        ),
                    ),
                )
                messages.append(tool_msg)

                # Emit tool result event
                if on_event is not None:
                    from cscode.schema.events import ToolFailure, ToolResult

                    # Extract metadata from tool result (task_id, evidence, etc.)
                    tool_metadata: dict[str, object] = {}
                    if hasattr(tool_result, "metadata") and isinstance(tool_result.metadata, dict):
                        tool_metadata = dict(tool_result.metadata)

                    if is_error:
                        evt = ToolFailure(
                            tool_call_id=tc.tool_call_id,
                            error=result_str,
                            tool_name=tc.name,
                            tool_args=dict(tc.args),
                            metadata=tool_metadata,
                        )
                    else:
                        evt = ToolResult(
                            tool_call_id=tc.tool_call_id,
                            result=result_str,
                            tool_name=tc.name,
                            tool_args=dict(tc.args),
                            metadata=tool_metadata,
                        )
                    await on_event(evt) if hasattr(on_event, "__await__") else on_event(evt)

                if session is not None:
                    await session.add_tool_call(tc.name, dict(tc.args))

            tool_round += 1

        if tool_round >= self._max_tool_rounds:
            logger.warning("_run_loop: max tool rounds (%d) reached", self._max_tool_rounds)
        logger.info("_run_loop: done tool_rounds=%d content_len=%d", tool_round, len(full_content))
        return full_content

    async def run_stream(
        self,
        user_input: str,
        session: SessionV2 | None = None,
        generation_options: GenerationOptions | None = None,
    ) -> AsyncIterator[LLMEvent]:
        """Stream LLMEvents for a user prompt through the agent loop.

        Yields ALL events including tool result events.
        The caller is responsible for consuming them.
        """
        logger.info(
            "AgentV2.run_stream: user_input_len=%d has_session=%s",
            len(user_input),
            session is not None,
        )
        messages = self._build_messages(user_input, session)
        model = ModelID(self._llm_client.route.model)
        options = generation_options or GenerationOptions()
        tool_round = 0

        while tool_round < self._max_tool_rounds:
            logger.debug(
                "run_stream: tool_round=%d/%d messages=%d",
                tool_round + 1,
                self._max_tool_rounds,
                len(messages),
            )
            request = LLMRequest(
                model=model,
                messages=tuple(messages),
                tools=tuple(self._tool_definitions),
                options=options,
            )

            assistant_text = ""
            tool_calls: list[ToolCallPart] = []

            async for event in self._llm_client.stream(request):
                yield event

                match event:
                    case TextDelta(text=t):
                        assistant_text += t
                    case ToolCallEnded(tool_call_id=tcid, name=n, args=a):
                        tool_calls.append(
                            ToolCallPart(
                                tool_call_id=ToolCallID(tcid),
                                name=n,
                                args=a,
                            )
                        )
                    case Finish():
                        break
                    case LLMEventError(error=e):
                        logger.error(
                            "run_stream: llm error tool_round=%d error=%s",
                            tool_round + 1,
                            e.message,
                        )
                        return

            if assistant_text:
                messages.append(
                    Message(
                        role=MessageRole.ASSISTANT,
                        parts=(TextPart(text=assistant_text),),
                    )
                )
                if session is not None:
                    await session.add_text(assistant_text)

            if not tool_calls:
                logger.debug("run_stream: no tool calls, finishing after round=%d", tool_round + 1)
                break

            logger.info(
                "run_stream: tool_round=%d tool_calls=%s",
                tool_round + 1,
                [tc.name for tc in tool_calls],
            )
            for tc in tool_calls:
                tool_result: Tool2Result[Any] = await self._settle(tc.name, dict(tc.args))
                is_error = not tool_result.success
                error_str = tool_result.error or ""
                data_str = str(tool_result.data) if tool_result.data is not None else ""
                result_str: str = error_str if is_error else data_str

                from cscode.schema.events import ToolFailure, ToolResult
                from cscode.schema.messages import ToolResultPart

                if is_error:
                    yield ToolFailure(tool_call_id=tc.tool_call_id, error=result_str)
                else:
                    yield ToolResult(tool_call_id=tc.tool_call_id, result=result_str)

                tool_msg = Message(
                    role=MessageRole.TOOL,
                    parts=(
                        ToolResultPart(
                            tool_call_id=tc.tool_call_id,
                            name=tc.name,
                            result=result_str,
                            is_error=is_error,
                        ),
                    ),
                )
                messages.append(tool_msg)

                if session is not None:
                    await session.add_tool_call(tc.name, dict(tc.args))

            tool_round += 1

    def _build_messages(
        self,
        user_input: str,
        session: SessionV2 | None = None,
    ) -> list[Message]:
        """Build the message list from session state and/or user input."""
        messages: list[Message] = []
        logger.debug(
            "_build_messages: has_system_prompt=%s has_session=%s",
            self._system_prompt is not None,
            session is not None,
        )

        # Inject system prompt
        if self._system_prompt:
            messages.append(Message.system(self._system_prompt))

        # Load existing messages from session
        if session is not None:
            messages.extend(session.state.messages)

        # Append the new user input
        messages.append(Message.user(user_input))
        return messages
