from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime, timezone
from typing import Any

from cscode.tools.base import BaseTool, ToolResult

EVIDENCE_DIR = "/tmp/cscode-outputs/evidence"

_browser = None
_page = None
_playwright = None

def _get_playwright() -> Any:
    global _playwright
    if _playwright is None:
        try:
            from playwright.async_api import async_playwright
            _playwright = async_playwright
        except ImportError:
            raise ImportError("playwright not installed. Run: pip install playwright && playwright install chromium")
    return _playwright


class BrowserTool(BaseTool):
    name = "browser"
    description = "Control a web browser for automation. Use this tool to open websites, click elements, fill forms, take screenshots, and extract content."
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": "Action to perform: open, click, type, screenshot, get_text, wait, scroll, get_html, close",
            },
            "url": {"type": "string", "description": "URL to open (for 'open' action)"},
            "task_id": {"type": "string", "description": "Test case ID (format: TC-XXX) for tracking"},
            "selector": {"type": "string", "description": "CSS selector for elements (for click, type, get_text, wait actions)"},
            "text": {"type": "string", "description": "Text to type (for 'type' action)"},
            "key": {"type": "string", "description": "Key to press (for 'press' action): Enter, Escape, Tab, ArrowUp, ArrowDown, etc."},
            "seconds": {"type": "number", "description": "Seconds to wait (for 'wait' action)"},
        },
        "required": ["action"],
    }

    async def execute(self, args: dict[str, Any], context: dict | None = None) -> ToolResult:
        global _browser, _page

        action = args.get("action", "")
        session_id = (context or {}).get("session_id", "")
        task_id = args.get("task_id", "")

        evidence = {
            "screenshot_path": "",
            "html": False,
            "html_length": 0,
            "content_length": 0,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        try:
            if action == "open":
                url = args.get("url", "about:blank")
                if not url.startswith(("http://", "https://", "file://")):
                    url = "https://" + url

                if _browser is None:
                    from playwright.async_api import async_playwright
                    pw = await async_playwright().start()
                    _browser = await pw.chromium.launch(headless=True)
                    _page = await _browser.new_page()

                await _page.goto(url, wait_until="domcontentloaded", timeout=30000)
                title = await _page.title()
                return ToolResult(
                    success=True,
                    data=f"Opened {url}. Page title: {title}",
                    metadata={"url": url, "title": title, "task_id": task_id},
                )

            elif action == "click":
                selector = args.get("selector")
                if not selector:
                    return ToolResult(success=False, data="", error="selector is required for click action")
                assert _page is not None
                await _page.click(selector, timeout=10000)
                return ToolResult(success=True, data=f"Clicked element: {selector}", metadata={"task_id": task_id})

            elif action == "type":
                selector = args.get("selector")
                text = args.get("text", "")
                if not selector:
                    return ToolResult(success=False, data="", error="selector is required for type action")
                assert _page is not None
                await _page.fill(selector, text)
                return ToolResult(success=True, data=f"Typed '{text}' into {selector}", metadata={"task_id": task_id})

            elif action == "press":
                selector = args.get("selector", "body")
                key = args.get("key", "Enter")
                assert _page is not None
                await _page.press(selector, key)
                return ToolResult(success=True, data=f"Pressed {key} on {selector}", metadata={"task_id": task_id})

            elif action == "screenshot":
                path = args.get("path", "/tmp/cscode-outputs/screenshot.png")
                os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
                if task_id:
                    os.makedirs(EVIDENCE_DIR, exist_ok=True)
                    path = os.path.join(EVIDENCE_DIR, f"{session_id}_{task_id}_screenshot.png")
                assert _page is not None
                await _page.screenshot(path=path, full_page=True)
                evidence["screenshot_path"] = path
                evidence["content_length"] = os.path.getsize(path) if os.path.exists(path) else 0
                verified = bool(evidence["screenshot_path"])
                return ToolResult(
                    success=True,
                    data=f"Screenshot saved to {path}",
                    metadata={"task_id": task_id, "evidence": json.dumps(evidence), "verified": str(verified)},
                )

            elif action == "get_text":
                selector = args.get("selector")
                if not selector:
                    return ToolResult(success=False, data="", error="selector is required for get_text action")
                assert _page is not None
                text = await _page.locator(selector).text_content()
                evidence["html"] = bool(text)
                evidence["html_length"] = len(text) if text else 0
                evidence["content_length"] = len(text) if text else 0
                verified = bool(evidence["screenshot_path"]) or evidence["html"]
                return ToolResult(
                    success=True,
                    data=text or "",
                    metadata={"selector": selector, "task_id": task_id, "evidence": json.dumps(evidence), "verified": str(verified)},
                )

            elif action == "get_html":
                selector = args.get("selector")
                assert _page is not None
                if selector:
                    html = await _page.locator(selector).inner_html()
                else:
                    html = await _page.content()
                import re
                html = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL)
                html = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.DOTALL)
                html = re.sub(r'<svg[^>]*>.*?</svg>', '', html, flags=re.DOTALL)
                html = re.sub(r'\s+', ' ', html).strip()
                truncated = html[:8000]
                if len(html) > 8000:
                    truncated += "\n\n[truncated: output too long]"
                evidence["html"] = bool(html)
                evidence["html_length"] = len(html)
                evidence["content_length"] = len(html)
                verified = bool(evidence["screenshot_path"]) or evidence["html"]
                return ToolResult(
                    success=True,
                    data=truncated,
                    metadata={"task_id": task_id, "evidence": json.dumps(evidence), "verified": str(verified)},
                )

            elif action == "wait":
                selector = args.get("selector")
                seconds = args.get("seconds", 2)
                assert _page is not None
                if selector:
                    await _page.wait_for_selector(selector, timeout=seconds * 1000)
                    return ToolResult(success=True, data=f"Waited for {selector}", metadata={"task_id": task_id})
                else:
                    await asyncio.sleep(seconds)
                    return ToolResult(success=True, data=f"Waited {seconds} seconds", metadata={"task_id": task_id})

            elif action == "scroll":
                selector = args.get("selector")
                assert _page is not None
                if selector:
                    await _page.locator(selector).scroll_into_view_if_needed()
                else:
                    await _page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                return ToolResult(success=True, data="Scrolled", metadata={"task_id": task_id})

            elif action == "close":
                if _browser:
                    await _browser.close()
                    _browser = None
                    _page = None
                return ToolResult(success=True, data="Browser closed", metadata={"task_id": task_id})

            elif action == "status":
                if _browser:
                    url = _page.url if _page else "none"
                    title = await _page.title() if _page else ""
                    return ToolResult(
                        success=True,
                        data=f"Browser is running. Current page: {url}, title: {title}",
                        metadata={"url": url, "title": title, "task_id": task_id},
                    )
                return ToolResult(success=True, data="Browser is not running", metadata={"task_id": task_id})

            else:
                return ToolResult(
                    success=False,
                    data="",
                    error=f"Unknown action: {action}. Available: open, click, type, press, screenshot, get_text, get_html, wait, scroll, close, status",
                    metadata={"task_id": task_id, "evidence": json.dumps(evidence), "verified": "False"},
                )

        except Exception as e:
            return ToolResult(
                success=False,
                data="",
                error=str(e),
                metadata={"task_id": task_id, "evidence": json.dumps(evidence), "verified": "False"},
            )
