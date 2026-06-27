"""BrowserTool v2 — browser automation with typed output."""

from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel

from cscode.tools2.base import Tool, ToolResult

EVIDENCE_DIR = "/tmp/cscode-outputs/evidence"

_browser = None
_page = None

_SYSTEM_CHROME_PATHS = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/usr/bin/google-chrome",
    "/usr/bin/google-chrome-stable",
    "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
    "C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe",
]


def _find_system_chrome() -> str | None:
    for p in _SYSTEM_CHROME_PATHS:
        if os.path.exists(p):
            return p
    return None


BrowserAction = Literal[
    "open", "click", "type", "press", "screenshot",
    "get_text", "get_html", "wait", "scroll", "close", "status",
]


class BrowserInput(BaseModel):
    action: BrowserAction
    url: str | None = None
    selector: str | None = None
    text: str | None = None
    key: str | None = None
    seconds: float | None = None
    task_id: str = ""


class BrowserOutput(BaseModel):
    result: str


class BrowserTool(Tool[BrowserInput, BrowserOutput]):
    name = "browser"
    description = "Control a web browser for automation"
    input_schema = BrowserInput
    output_schema = BrowserOutput

    async def execute(self, input: BrowserInput) -> ToolResult[BrowserOutput]:
        global _browser, _page

        evidence: dict[str, Any] = {
            "screenshot_path": "",
            "html": False,
            "html_length": 0,
            "content_length": 0,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        try:
            return await self._handle_action(input, evidence)
        except Exception as e:
            return ToolResult(
                success=False,
                error=str(e),
                metadata={"task_id": input.task_id},
            )

    async def _ensure_browser(self) -> None:
        global _browser, _page
        if _browser is not None:
            return
        from playwright.async_api import async_playwright

        pw = await async_playwright().start()
        chrome_path = _find_system_chrome()
        if chrome_path:
            _browser = await pw.chromium.launch(headless=True, executable_path=chrome_path)
        else:
            _browser = await pw.chromium.launch(headless=True)
        _page = await _browser.new_page()

    async def _handle_action(
        self,
        input: BrowserInput,
        evidence: dict[str, Any],
    ) -> ToolResult[BrowserOutput]:
        global _page, _browser

        if input.action == "open":
            url = input.url or "about:blank"
            if not url.startswith(("http://", "https://", "file://")):
                url = "https://" + url
            await self._ensure_browser()
            assert _page is not None
            await _page.goto(url, wait_until="domcontentloaded", timeout=30000)
            title = await _page.title()
            return ToolResult(
                success=True,
                data=BrowserOutput(result=f"Opened {url}. Page title: {title}"),
                metadata={"url": url, "title": title, "task_id": input.task_id},
            )

        elif input.action == "click":
            if not input.selector:
                return ToolResult(success=False, error="selector is required for click")
            assert _page is not None
            await _page.click(input.selector, timeout=10000)
            return ToolResult(
                success=True,
                data=BrowserOutput(result=f"Clicked element: {input.selector}"),
                metadata={"task_id": input.task_id},
            )

        elif input.action == "type":
            if not input.selector:
                return ToolResult(success=False, error="selector is required for type")
            assert _page is not None
            await _page.fill(input.selector, input.text or "")
            return ToolResult(
                success=True,
                data=BrowserOutput(result=f"Typed into {input.selector}"),
                metadata={"task_id": input.task_id},
            )

        elif input.action == "press":
            assert _page is not None
            sel = input.selector or "body"
            key = input.key or "Enter"
            await _page.press(sel, key)
            return ToolResult(
                success=True,
                data=BrowserOutput(result=f"Pressed {key} on {sel}"),
                metadata={"task_id": input.task_id},
            )

        elif input.action == "screenshot":
            assert _page is not None
            os.makedirs(EVIDENCE_DIR, exist_ok=True)
            path = os.path.join(EVIDENCE_DIR, f"{input.task_id}_screenshot.png")
            await _page.screenshot(path=path, full_page=True)
            evidence["screenshot_path"] = path
            return ToolResult(
                success=True,
                data=BrowserOutput(result=f"Screenshot saved to {path}"),
                metadata={"task_id": input.task_id, "evidence": json.dumps(evidence)},
            )

        elif input.action == "get_text":
            if not input.selector:
                return ToolResult(success=False, error="selector is required for get_text")
            assert _page is not None
            text = await _page.locator(input.selector).text_content()
            evidence["html"] = bool(text)
            evidence["content_length"] = len(text or "")
            return ToolResult(
                success=True,
                data=BrowserOutput(result=text or ""),
                metadata={"selector": input.selector, "task_id": input.task_id},
            )

        elif input.action == "get_html":
            assert _page is not None
            if input.selector:
                html = await _page.locator(input.selector).inner_html()
            else:
                html = await _page.content()
            import re
            html = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL)
            html = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.DOTALL)
            html = re.sub(r'<svg[^>]*>.*?</svg>', '', html, flags=re.DOTALL)
            html = re.sub(r'\s+', ' ', html).strip()
            truncated = html[:8000]
            if len(html) > 8000:
                truncated += "\n\n[truncated]"
            return ToolResult(
                success=True,
                data=BrowserOutput(result=truncated),
                metadata={"task_id": input.task_id},
            )

        elif input.action == "wait":
            assert _page is not None
            seconds = input.seconds or 2
            if input.selector:
                await _page.wait_for_selector(input.selector, timeout=int(seconds * 1000))
                return ToolResult(
                    success=True,
                    data=BrowserOutput(result=f"Waited for {input.selector}"),
                    metadata={"task_id": input.task_id},
                )
            await asyncio.sleep(seconds)
            return ToolResult(
                success=True,
                data=BrowserOutput(result=f"Waited {seconds}s"),
                metadata={"task_id": input.task_id},
            )

        elif input.action == "scroll":
            assert _page is not None
            if input.selector:
                await _page.locator(input.selector).scroll_into_view_if_needed()
            else:
                await _page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            return ToolResult(
                success=True,
                data=BrowserOutput(result="Scrolled"),
                metadata={"task_id": input.task_id},
            )

        elif input.action == "close":
            if _browser:
                await _browser.close()
                _browser = None
                _page = None
            return ToolResult(
                success=True,
                data=BrowserOutput(result="Browser closed"),
                metadata={"task_id": input.task_id},
            )

        elif input.action == "status":
            if _browser and _page:
                url = _page.url
                title = await _page.title()
                return ToolResult(
                    success=True,
                    data=BrowserOutput(result=f"Running. Page: {url}, title: {title}"),
                    metadata={"url": url, "title": title, "task_id": input.task_id},
                )
            return ToolResult(
                success=True,
                data=BrowserOutput(result="Browser is not running"),
                metadata={"task_id": input.task_id},
            )

        else:
            return ToolResult(
                success=False,
                error=f"Unknown action: {input.action}",
                metadata={"task_id": input.task_id},
            )
