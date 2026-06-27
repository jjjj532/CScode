"""SubAgentOrchestrator — processes @tool mentions in user input.

Parses `@tool:ToolName key=value` patterns from text, executes the
referenced tool via ToolRegistry, and injects the result back into
the text.

Usage:
    orchestrator = SubAgentOrchestrator(tool_registry)
    result = await orchestrator.process_mentions(
        "Read @tool:ReadTool path=foo.py and summarize"
    )
    # → "Read [Tool ReadTool result: file contents] and summarize"
"""

from __future__ import annotations

import re

from cscode.schema.messages import Message, MessageRole, TextPart
from cscode.tools2.registry import ToolRegistry


class SubAgentOrchestrator:
    """Processes @tool mentions by executing tools and injecting results."""

    def __init__(self, tool_registry: ToolRegistry) -> None:
        _, self._settle = tool_registry.materialize()

    async def process_messages(self, messages: list[Message]) -> list[Message]:
        """Process @tool mentions in all user messages.

        Returns a new message list with TextPart text in USER-role messages
        processed for @tool mentions.
        """
        result: list[Message] = []
        for msg in messages:
            if msg.role != MessageRole.USER:
                result.append(msg)
                continue

            new_parts: list[TextPart] = []
            changed = False
            for part in msg.parts:
                if isinstance(part, TextPart):
                    new_text = await self.process_mentions(part.text)
                    if new_text != part.text:
                        changed = True
                        new_parts.append(TextPart(text=new_text))
                    else:
                        new_parts.append(part)
                else:
                    new_parts.append(part)  # type: ignore[arg-type]

            if changed:
                result.append(Message(role=MessageRole.USER, parts=tuple(new_parts)))
            else:
                result.append(msg)

        return result

    async def process_mentions(self, text: str) -> str:
        """Find and execute all @tool mentions in text.

        Pattern: @tool:ToolName key=value or @tool:ToolName key="value with spaces"

        Returns text with @tool mentions replaced by their execution results.
        Unknown tools or execution errors produce inline error messages.
        """
        if "@tool:" not in text:
            return text

        # Find all @tool mentions with their positions
        pattern = re.compile(r'@tool:(\w+)((?:\s+\w+=(?:"[^"]*"|\S+))*)')
        matches = list(pattern.finditer(text))
        if not matches:
            return text

        # Process in reverse order so positions don't shift
        result = text
        offset = 0
        for match in reversed(matches):
            full_match = match.group(0)
            tool_name = match.group(1)
            args_str = match.group(2).strip()

            args = self._parse_args(args_str)
            replacement = await self._execute_and_format(tool_name, args)

            start = match.start() + offset
            end = match.end() + offset
            result = result[:start] + replacement + result[end:]
            offset += len(replacement) - len(full_match)

        return result

    def _parse_args(self, args_str: str) -> dict[str, str]:
        """Parse key=value or key="quoted value" pairs into a dict."""
        args: dict[str, str] = {}
        arg_pattern = re.compile(r'(\w+)=(?:"([^"]*)"|(\S+))')
        for m in arg_pattern.finditer(args_str):
            key = m.group(1)
            value = m.group(2) if m.group(2) is not None else m.group(3)
            args[key] = value
        return args

    async def _execute_and_format(self, tool_name: str, args: dict[str, str]) -> str:
        """Execute a tool and format its result as inline text."""
        try:
            result = await self._settle(tool_name, args)
            if result.success:
                data = str(result.data) if result.data is not None else ""
                return f"[Tool {tool_name} result: {data}]"
            else:
                error = result.error or "Unknown error"
                return f"[Tool {tool_name} error: {error}]"
        except Exception as e:
            return f"[Tool {tool_name} error: {e}]"
