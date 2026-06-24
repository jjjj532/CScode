from __future__ import annotations

import asyncio
import collections.abc
import json
from dataclasses import dataclass
from typing import Any

from cscode.core.compression import ContextCompressor
from cscode.core.config import Config
from cscode.core.images import ImageAttachment, is_image_file, process_image_file
from cscode.core.messages import Message, MessageRole
from cscode.core.permissions import PermissionResult, PermissionService
from cscode.git.snapshot import GitSnapshot
from cscode.providers.base import LLMProvider
from cscode.tools.base import ToolRegistry
from cscode.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class AgentOptions:
    max_tool_rounds: int | None = None
    system_prompt: str | None = None
    timeout: float = 300.0


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
        self.session_id: str = ""

    async def run(self, user_input: str) -> str:
        messages = self._build_initial_messages()
        messages.append(Message(role=MessageRole.USER, content=user_input))
        return await self._run_loop(messages)

    async def run_with_permissions(
        self,
        user_input: str,
        permission_service: PermissionService | None = None,
        attached_filenames: list[str] | None = None,
        on_event: collections.abc.Callable[[dict[str, Any]], collections.abc.Awaitable[None]] | None = None,
        compressor: ContextCompressor | None = None,
    ) -> str:
        messages = self._build_initial_messages()
        messages.append(Message(role=MessageRole.USER, content=user_input))
        return await self._run_loop(messages, attached_filenames=attached_filenames, on_event=on_event, permission_service=permission_service, compressor=compressor)

    async def _run_loop(self, messages: list[Message], attached_filenames: list[str] | None = None, timeout: float | None = None, on_event: collections.abc.Callable[[dict[str, Any]], collections.abc.Awaitable[None]] | None = None, permission_service: PermissionService | None = None, compressor: ContextCompressor | None = None) -> str:
        if compressor is not None:
            original_len = len(messages)
            messages = compressor.compress(messages)
            if len(messages) < original_len:
                logger.info("Context compressed: %d -> %d messages", original_len, len(messages))

        if attached_filenames:
            image_attachments: list[ImageAttachment] = []
            for fname in attached_filenames:
                if is_image_file(fname):
                    att = process_image_file(fname)
                    if att is not None:
                        image_attachments.append(att)

            if image_attachments:
                for msg in reversed(messages):
                    if msg.role == MessageRole.USER:
                        msg.image_attachments = image_attachments
                        break

        tool_rounds = 0
        effective_timeout = timeout if timeout is not None else self.options.timeout
        file_guard = bool(attached_filenames)
        search_tools = {"Glob", "Grep", "Ls"}
        search_keywords = ["find ", "locate ", "rg ", "ripgrep ", "cat ", "head ", "tail ", "less ", "more "]
        python_read_patterns = ["open(", ".read()", "read_text", "read_file", "Path(", "pathlib"]

        async def _emit(event: dict[str, Any]) -> None:
            logger.debug("event: %s", event)
            if on_event:
                await on_event(event)

        async def _intercept(tool_call: dict[str, Any], msgs: list[Message]) -> bool:
            if not file_guard:
                return False
            func_name = tool_call.get("function", {}).get("name", "")
            try:
                args_raw = tool_call.get("function", {}).get("arguments", "{}")
                arguments = json.loads(args_raw) if isinstance(args_raw, str) else args_raw
            except json.JSONDecodeError:
                arguments = {}

            if func_name in search_tools:
                logger.warning("FILE_GUARD: blocked %s (files attached)", func_name)
                msgs.append(
                    Message(
                        role=MessageRole.TOOL,
                        content="[File Guard] Do not search for files. The attached file(s) are already provided in [FILE: ...] blocks above in this conversation.",
                        tool_call_id=tool_call.get("id"),
                        name=func_name,
                    )
                )
                return True

            if func_name == "Bash":
                cmd = (arguments.get("command", "") if isinstance(arguments, dict) else str(arguments)).lower()
                for kw in search_keywords:
                    if kw in cmd:
                        logger.warning("FILE_GUARD: blocked Bash '%s' (files attached)", cmd[:50])
                        msgs.append(
                            Message(
                                role=MessageRole.TOOL,
                                content="[File Guard] Do not use shell commands to search for or read files. The attached file(s) are already provided in [FILE: ...] blocks above. Use the Read tool instead to read any other files you need.",
                                tool_call_id=tool_call.get("id"),
                                name=func_name,
                            )
                        )
                        return True

                for pat in python_read_patterns:
                    if pat in cmd:
                        logger.warning("FILE_GUARD: blocked Python file read '%s' (files attached)", cmd[:50])
                        msgs.append(
                            Message(
                                role=MessageRole.TOOL,
                                content="[File Guard] Do not use Python file I/O to read files. The attached file(s) are already provided in [FILE: ...] blocks above. Use the Read tool instead to read any other files you need.",
                                tool_call_id=tool_call.get("id"),
                                name=func_name,
                            )
                        )
                        return True

            return False

        async def _loop() -> str:
            nonlocal tool_rounds

            def _brief_args(name: str, args: dict[str, Any]) -> str:
                if name == "Browser":
                    url = args.get("url", "")
                    if url:
                        return url[:80]
                    action = args.get("action", "")
                    sel = args.get("selector", "")
                    val = args.get("value", "")
                    if action == "click":
                        return f"click {sel[:40]}"
                    if action == "type":
                        return f"type '{val[:30]}' into {sel[:30]}"
                    if action in ("get_text", "get_html"):
                        return f"read {sel[:40]}"
                    if action == "screenshot":
                        return "screenshot"
                    return f"{action} {sel[:40] or url[:60]}"
                if name == "Bash":
                    cmd = args.get("command", "")
                    return cmd[:80].replace("\n", " ")
                if name == "Read":
                    return args.get("file_path", "")[:60]
                if name == "Write":
                    return args.get("file_path", "")[:60]
                if name == "Edit":
                    return args.get("file_path", "")[:60]
                if name == "Glob":
                    return args.get("pattern", "")[:60]
                if name == "Grep":
                    return args.get("pattern", "")[:60]
                return ""

            while True:
                await _emit({"type": "thinking"})
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

                if result.tool_calls is None:
                    return result.content

                if self.options.max_tool_rounds is not None and tool_rounds >= self.options.max_tool_rounds:
                    return result.content

                tool_rounds += 1
                logger.info("TOOL: round %s/%s, %s tool call(s)", tool_rounds, self.options.max_tool_rounds if self.options.max_tool_rounds is not None else "∞", len(result.tool_calls))
                git_snapshot = GitSnapshot()
                for tool_call in result.tool_calls:
                    func_name = tool_call.get("function", {}).get("name", "?")
                    if func_name in ("Write", "Edit", "Bash"):
                        git_snapshot.snapshot(f"before {func_name}")
                    try:
                        args_json = tool_call.get("function", {}).get("arguments", "{}")
                        fn_args = json.loads(args_json) if isinstance(args_json, str) else args_json
                    except (json.JSONDecodeError, TypeError):
                        fn_args = {}
                    # Extract brief args summary for display
                    brief_args = _brief_args(func_name, fn_args) if fn_args else ""
                    await _emit({"type": "tool:start", "name": func_name, "args": brief_args, "round": tool_rounds, "max": self.options.max_tool_rounds if self.options.max_tool_rounds is not None else 0})
                    if await _intercept(tool_call, messages):
                        await _emit({"type": "tool:complete", "name": func_name, "success": True, "intercepted": True})
                        continue
                    if permission_service is not None:
                        perm = await permission_service.check(func_name, fn_args)
                        if perm == PermissionResult.DENIED:
                            messages.append(Message(
                                role=MessageRole.TOOL,
                                content=f"[Permission Denied] Tool '{func_name}' is not permitted.",
                                tool_call_id=tool_call.get("id"),
                                name=func_name,
                            ))
                            await _emit({"type": "tool:complete", "name": func_name, "success": False, "intercepted": True})
                            continue
                        elif perm == PermissionResult.ASK:
                            await _emit({"type": "permission:ask", "name": func_name, "args": fn_args})
                    context = {"session_id": self.session_id, "on_event": _emit}
                    tool_result = await self.registry.execute_tool_call(tool_call, context=context)
                    # Truncate result for display (~200 chars)
                    result_preview = (tool_result.data or tool_result.error or "")[:200]
                    await _emit({"type": "tool:complete", "name": func_name, "success": tool_result.success, "content": result_preview})
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

        try:
            return await asyncio.wait_for(_loop(), timeout=effective_timeout)
        except asyncio.TimeoutError:
            return f"Task timed out after {effective_timeout:.0f}s. {tool_rounds} tool rounds completed. Please try a simpler request or split into smaller steps."

    async def run_loop_events(
        self,
        messages: list[Message],
        on_event: collections.abc.Callable[[dict[str, Any]], collections.abc.Awaitable[None]] | None = None,
        attached_filenames: list[str] | None = None,
        timeout: float | None = None,
        permission_service: PermissionService | None = None,
        compressor: ContextCompressor | None = None,
    ) -> str:
        if compressor is not None:
            original_len = len(messages)
            messages = compressor.compress(messages)
            if len(messages) < original_len:
                logger.info("Context compressed: %d -> %d messages", original_len, len(messages))

        if attached_filenames:
            image_attachments: list[ImageAttachment] = []
            for fname in attached_filenames:
                if is_image_file(fname):
                    att = process_image_file(fname)
                    if att is not None:
                        image_attachments.append(att)

            if image_attachments:
                for msg in reversed(messages):
                    if msg.role == MessageRole.USER:
                        msg.image_attachments = image_attachments
                        break

        tool_rounds = 0
        effective_timeout = timeout if timeout is not None else self.options.timeout
        file_guard = bool(attached_filenames)
        search_tools = {"Glob", "Grep", "Ls"}
        search_keywords = ["find ", "locate ", "rg ", "ripgrep ", "cat ", "head ", "tail ", "less ", "more "]
        python_read_patterns = ["open(", ".read()", "read_text", "read_file", "Path(", "pathlib"]

        async def _emit(event: dict[str, Any]) -> None:
            logger.debug("event: %s", event)
            if on_event:
                await on_event(event)

        async def _intercept(tool_call: dict[str, Any], msgs: list[Message]) -> bool:
            if not file_guard:
                return False
            func_name = tool_call.get("function", {}).get("name", "")
            try:
                args_raw = tool_call.get("function", {}).get("arguments", "{}")
                arguments = json.loads(args_raw) if isinstance(args_raw, str) else args_raw
            except json.JSONDecodeError:
                arguments = {}

            if func_name in search_tools:
                logger.warning("FILE_GUARD: blocked %s (files attached)", func_name)
                msgs.append(
                    Message(
                        role=MessageRole.TOOL,
                        content="[File Guard] Do not search for files. The attached file(s) are already provided in [FILE: ...] blocks above in this conversation.",
                        tool_call_id=tool_call.get("id"),
                        name=func_name,
                    )
                )
                return True

            if func_name == "Bash":
                cmd = (arguments.get("command", "") if isinstance(arguments, dict) else str(arguments)).lower()
                for kw in search_keywords:
                    if kw in cmd:
                        logger.warning("FILE_GUARD: blocked Bash '%s' (files attached)", cmd[:50])
                        msgs.append(
                            Message(
                                role=MessageRole.TOOL,
                                content="[File Guard] Do not use shell commands to search for or read files. The attached file(s) are already provided in [FILE: ...] blocks above. Use the Read tool instead to read any other files you need.",
                                tool_call_id=tool_call.get("id"),
                                name=func_name,
                            )
                        )
                        return True

                for pat in python_read_patterns:
                    if pat in cmd:
                        logger.warning("FILE_GUARD: blocked Python file read '%s' (files attached)", cmd[:50])
                        msgs.append(
                            Message(
                                role=MessageRole.TOOL,
                                content="[File Guard] Do not use Python file I/O to read files. The attached file(s) are already provided in [FILE: ...] blocks above. Use the Read tool instead to read any other files you need.",
                                tool_call_id=tool_call.get("id"),
                                name=func_name,
                            )
                        )
                        return True

            return False

        async def _loop() -> str:
            nonlocal tool_rounds
            max_rounds = self.options.max_tool_rounds

            while True:
                await _emit({"type": "step.started", "data": {"round": tool_rounds + 1, "max": max_rounds if max_rounds is not None else 0}})

                # Inject wrap-up hint when approaching limit, but let LLM decide
                if max_rounds is not None and tool_rounds >= max_rounds - 3:
                    hint = (
                        f"\n\n[System] You have used {tool_rounds}/{max_rounds} tool rounds. "
                        "Please wrap up your work and provide a final response without further tool calls."
                    )
                    if messages and messages[-1].role == MessageRole.USER:
                        messages[-1].content += hint
                    else:
                        messages.append(Message(role=MessageRole.USER, content=hint))

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

                await _emit({"type": "text.ended", "data": {"content": result.content}})

                # LLM decided to stop — no more tool calls
                if result.tool_calls is None:
                    await _emit({"type": "step.ended", "data": {"round": tool_rounds, "finish_reason": "stop"}})
                    return result.content

                # Hard limit reached — force stop
                if max_rounds is not None and tool_rounds >= max_rounds:
                    await _emit({"type": "step.ended", "data": {"round": tool_rounds, "finish_reason": "max_rounds"}})
                    return result.content

                tool_rounds += 1
                logger.info("TOOL: round %s/%s, %s tool call(s)", tool_rounds, max_rounds if max_rounds is not None else "∞", len(result.tool_calls))
                git_snapshot = GitSnapshot()
                for tool_call in result.tool_calls:
                    func_name = tool_call.get("function", {}).get("name", "?")
                    if func_name in ("Write", "Edit", "Bash"):
                        git_snapshot.snapshot(f"before {func_name}")
                    try:
                        args_json = tool_call.get("function", {}).get("arguments", "{}")
                        fn_args = json.loads(args_json) if isinstance(args_json, str) else args_json
                    except (json.JSONDecodeError, TypeError):
                        fn_args = {}
                    await _emit({"type": "tool.called", "data": {"name": func_name, "args": fn_args, "round": tool_rounds, "max": max_rounds if max_rounds is not None else 0}})
                    if await _intercept(tool_call, messages):
                        await _emit({"type": "tool.failed", "data": {"name": func_name, "error": "Intercepted by file guard"}})
                        continue
                    if permission_service is not None:
                        perm = await permission_service.check(func_name, fn_args)
                        if perm == PermissionResult.DENIED:
                            messages.append(Message(
                                role=MessageRole.TOOL,
                                content=f"[Permission Denied] Tool '{func_name}' is not permitted.",
                                tool_call_id=tool_call.get("id"),
                                name=func_name,
                            ))
                            await _emit({"type": "tool.failed", "data": {"name": func_name, "error": "[Permission Denied] Tool is not permitted."}})
                            continue
                        elif perm == PermissionResult.ASK:
                            await _emit({"type": "permission:ask", "name": func_name, "args": fn_args})
                    context = {"session_id": self.session_id, "on_event": _emit}
                    tool_result = await self.registry.execute_tool_call(tool_call, context=context)
                    if tool_result.success:
                        await _emit({"type": "tool.success", "data": {"name": func_name, "result": (tool_result.data or "")[:200]}})
                    else:
                        await _emit({"type": "tool.failed", "data": {"name": func_name, "error": (tool_result.error or "")[:200]}})
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

                await _emit({"type": "step.ended", "data": {"round": tool_rounds, "finish_reason": "tool_use"}})

        try:
            return await asyncio.wait_for(_loop(), timeout=effective_timeout)
        except asyncio.TimeoutError:
            return f"Task timed out after {effective_timeout:.0f}s. {tool_rounds} tool rounds completed. Please try a simpler request or split into smaller steps."

    def _build_initial_messages(self) -> list[Message]:
        msgs: list[Message] = []
        if self.options.system_prompt:
            msgs.append(Message(role=MessageRole.SYSTEM, content=self.options.system_prompt))
        return msgs
