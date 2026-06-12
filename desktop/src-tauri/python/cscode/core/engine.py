from __future__ import annotations

from dataclasses import dataclass

from cscode.core.config import Config
from cscode.core.messages import Message, MessageRole
from cscode.providers.base import LLMProvider
from cscode.tools.base import ToolRegistry


@dataclass
class AgentOptions:
    max_tool_rounds: int = 25
    system_prompt: str | None = None


class Agent:
    def __init__(
        self,
        config: Config,
        provider: LLMProvider,
        registry: ToolRegistry,
        options: AgentOptions | None = None,
    ) -> None:
        self.config = config
        self.provider = provider
        self.registry = registry
        self.options = options or AgentOptions()

    async def run(self, user_input: str) -> str:
        messages = self._build_initial_messages()
        messages.append(Message(role=MessageRole.USER, content=user_input))
        return await self._run_loop(messages)

    async def _run_loop(self, messages: list[Message]) -> str:
        tool_rounds = 0

        while True:
            result = await self.provider.complete(
                messages,
                tools=self.registry.to_llm_tools(),
            )

            assistant_msg = Message(
                role=MessageRole.ASSISTANT,
                content=result.content,
                tool_calls=result.tool_calls,
            )
            messages.append(assistant_msg)

            if result.tool_calls is None or tool_rounds >= self.options.max_tool_rounds:
                return result.content

            tool_rounds += 1
            for tool_call in result.tool_calls:
                tool_result = await self.registry.execute_tool_call(tool_call)
                messages.append(
                    Message(
                        role=MessageRole.TOOL,
                        content=tool_result.data
                        if tool_result.success
                        else (tool_result.error or ""),
                        tool_call_id=tool_call.get("id"),
                        name=tool_call.get("function", {}).get("name"),
                    )
                )

    def _build_initial_messages(self) -> list[Message]:
        msgs: list[Message] = []
        if self.options.system_prompt:
            msgs.append(Message(role=MessageRole.SYSTEM, content=self.options.system_prompt))
        return msgs
