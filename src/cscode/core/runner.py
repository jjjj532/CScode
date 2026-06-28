"""SessionRunner — standardized Agent Loop.

Extracts the core agent loop from engine.py's _run_loop into a
clean abstraction that uses the LLM layer (LLMClient + ToolRuntime)
and Event Sourcing (SessionV2).

The loop:
  1. Build LLM context from session events
  2. Call LLMClient.stream() → LLMEvents
  3. Forward LLMEvents to caller via callback
  4. On ToolCallEnded → ToolRuntime.dispatch() → append tool result
  5. Loop until Finish or max tool rounds
  6. Return final content
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from typing import Any

from cscode.core.session import SessionV2
from cscode.llm.client import LLMClient
from cscode.llm.tool_runtime import ToolRuntime
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
from cscode.utils.logging import get_logger

logger = get_logger(__name__)


class SessionRunner:
    """Standardized agent loop over a SessionV2.

    Processes a user prompt through LLM calls and tool dispatch.
    """

    def __init__(
        self,
        llm_client: LLMClient,
        tool_runtime: ToolRuntime,
        max_tool_rounds: int = 20,
        system_prompt: str | None = None,
    ) -> None:
        self._llm_client = llm_client
        self._tool_runtime = tool_runtime
        self._max_tool_rounds = max_tool_rounds
        self._system_prompt = system_prompt

    async def run(
        self,
        session: SessionV2,
        user_input: str,
        on_event: Callable[[LLMEvent], Any] | None = None,
        generation_options: GenerationOptions | None = None,
    ) -> str:
        """Process a user prompt through the agent loop.

        Args:
            session: The session to process within.
            user_input: The user's prompt text.
            on_event: Optional callback for streaming LLMEvents.
            generation_options: Optional generation parameters.

        Returns:
            The final assistant response text.
        """
        # Append the user prompt
        await session.prompt(user_input)

        logger.info(
            "SessionRunner.run: session=%s max_rounds=%d prompt_len=%d",
            session.session_id, self._max_tool_rounds, len(user_input),
        )

        # Build context messages from session state
        messages = list(session.state.messages)

        # Inject system prompt if configured
        if self._system_prompt and not any(
            m.role == MessageRole.SYSTEM for m in messages
        ):
            messages.insert(0, Message.system(self._system_prompt))

        # Build the LLM request
        model = ModelID(session.state.model)
        options = generation_options or GenerationOptions()

        tool_round = 0
        full_content = ""

        while tool_round < self._max_tool_rounds:
            logger.debug("LLM request round=%d messages=%d", tool_round, len(messages))
            request = LLMRequest(
                model=model,
                messages=tuple(messages),
                options=options,
            )

            # Stream LLM response
            assistant_msg_parts: list[TextPart] = []
            tool_calls: list[ToolCallPart] = []
            content = ""

            async for event in self._llm_client.stream(request):
                if on_event is not None:
                    await on_event(event) if hasattr(on_event, "__await__") else on_event(event)

                match event:
                    case TextDelta(text=t):
                        content += t
                    case TextEnded(full_text=t):
                        content = t
                        assistant_msg_parts.append(TextPart(text=t))
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
                        msg = f"LLM error: {e.message}"
                        return msg

            # Build assistant message from the response
            all_parts: list[TextPart | ToolCallPart] = list(assistant_msg_parts)
            all_parts.extend(tool_calls)
            if all_parts:
                assistant_msg = Message(
                    role=MessageRole.ASSISTANT,
                    parts=tuple(all_parts),
                )
                messages.append(assistant_msg)
                await session.add_text(content)

            full_content += content

            # If no tool calls, we're done
            if not tool_calls:
                break

            logger.debug("Dispatching %d tool calls round=%d", len(tool_calls), tool_round)
            # Dispatch tool calls
            for tc in tool_calls:
                tid = ToolCallID(tc.tool_call_id)
                logger.debug("Dispatching tool=%s id=%s", tc.name, tid)
                async for tool_event in self._tool_runtime.dispatch(
                    tid, tc.name, tc.args
                ):
                    if on_event is not None:
                        await on_event(tool_event) if hasattr(on_event, "__await__") else on_event(tool_event)

                    match tool_event:
                        case _:
                            result = getattr(tool_event, "result", "")
                            is_error = getattr(tool_event, "is_error", False)
                            if not is_error and not result:
                                error = getattr(tool_event, "error", "")
                                result = str(error) if error else ""
                                is_error = bool(error)

                            tool_msg = Message.from_tool_result(
                                tool_call_id=tid,
                                name=tc.name,
                                result=str(result),
                                is_error=is_error,
                            )
                            messages.append(tool_msg)

            tool_round += 1

        logger.info(
            "SessionRunner.run completed: session=%s rounds=%d final_len=%d",
            session.session_id, tool_round, len(full_content),
        )
        return full_content

    async def run_stream(
        self,
        session: SessionV2,
        user_input: str,
        generation_options: GenerationOptions | None = None,
    ) -> AsyncIterator[LLMEvent]:
        """Stream LLMEvents for a user prompt through the agent loop.

        Yields LLMEvents as they arrive. The caller is responsible
        for consuming them.
        """
        await session.prompt(user_input)

        logger.info(
            "SessionRunner.run_stream: session=%s max_rounds=%d",
            session.session_id, self._max_tool_rounds,
        )

        messages = list(session.state.messages)
        if self._system_prompt and not any(
            m.role == MessageRole.SYSTEM for m in messages
        ):
            messages.insert(0, Message.system(self._system_prompt))

        model = ModelID(session.state.model)
        options = generation_options or GenerationOptions()
        tool_round = 0

        while tool_round < self._max_tool_rounds:
            logger.debug("run_stream: LLM request round=%d messages=%d", tool_round, len(messages))
            request = LLMRequest(model=model, messages=tuple(messages), options=options)

            content = ""
            tool_calls: list[ToolCallPart] = []
            content = ""

            async for event in self._llm_client.stream(request):
                yield event

                match event:
                    case TextDelta(text=t):
                        content += t
                    case ToolCallEnded(tool_call_id=tcid, name=n, args=a):
                        tool_calls.append(
                            ToolCallPart(tool_call_id=ToolCallID(tcid), name=n, args=a)
                        )
                    case Finish():
                        break
                    case LLMEventError():
                        return

            if content:
                await session.add_text(content)
                messages.append(
                    Message(role=MessageRole.ASSISTANT, parts=(TextPart(text=content),))
                )

            if not tool_calls:
                break

            logger.debug("run_stream: dispatching %d tools", len(tool_calls))
            for tc in tool_calls:
                tid = ToolCallID(tc.tool_call_id)
                async for tool_event in self._tool_runtime.dispatch(tid, tc.name, tc.args):
                    yield tool_event
                    result = getattr(tool_event, "result", None) or getattr(tool_event, "error", "")
                    tool_msg = Message.from_tool_result(
                        tool_call_id=tid,
                        name=tc.name,
                        result=str(result),
                        is_error=hasattr(tool_event, "error") and bool(getattr(tool_event, "error", "")),
                    )
                    messages.append(tool_msg)

            tool_round += 1
