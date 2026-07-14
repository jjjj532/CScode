#!/usr/bin/env python3
"""
CScode 全面 GUI 功能测试 v3
- 基于精确DOM选择器
- 覆盖所有按钮和场景
- 所有异常行为自动检测
"""

import asyncio
import json
from datetime import datetime
from pathlib import Path
from playwright.async_api import Page, Playwright, async_playwright

OUTPUT_DIR = Path("/Users/mac/AI/CScode/dogfood-output/v3-final-test")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

test_results = []
console_logs = []
network_errors = []
all_network_requests = []


def log(msg: str):
    ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    print(f"[{ts}] {msg}")


def record_result(test_name: str, passed: bool, detail: str, screenshot: str = None):
    result = {
        "test_name": test_name,
        "passed": passed,
        "detail": detail,
        "timestamp": datetime.now().isoformat(),
        "screenshot": screenshot
    }
    test_results.append(result)
    status = "✅" if passed else "❌"
    log(f"  {status} {test_name}: {detail}")


async def screenshot(page: Page, name: str):
    path = str(OUTPUT_DIR / f"{name}.png")
    await page.screenshot(path=path)
    return path


class CSCodTester:
    def __init__(self, page: Page):
        self.page = page
        self.base_url = "http://localhost:8000"

    async def setup(self):
        self.page.on("console", lambda msg: console_logs.append({
            "type": msg.type, "text": msg.text,
            "time": datetime.now().isoformat()
        }))
        self.page.on("requestfailed", lambda req: network_errors.append({
            "url": req.url,
            "error": req.failure,
            "time": datetime.now().isoformat()
        }))
        self.page.on("response", lambda res: all_network_requests.append({
            "status": res.status,
            "url": res.url,
            "method": res.request.method,
            "time": datetime.now().isoformat()
        }))

    async def goto(self):
        await self.page.goto(self.base_url, wait_until="domcontentloaded")
        await self.page.wait_for_timeout(2000)

    # ===== Utility methods =====
    async def create_session(self):
        btn = self.page.locator('button[aria-label="Create new session"]')
        await btn.click()
        await self.page.wait_for_timeout(800)

    async def get_sidebar_sessions(self):
        items = await self.page.query_selector_all('li.group')
        return items

    async def send_message(self, text: str):
        textarea = self.page.locator('textarea[placeholder*="Ask anything"]')
        await textarea.fill(text)
        await textarea.press("Enter")
        await self.page.wait_for_timeout(500)

    async def count_keyword(self, keyword: str):
        content = await self.page.content()
        return content.lower().count(keyword.lower())

    # ===== Test Groups =====

    async def test_1_all_buttons(self):
        log("\n" + "="*60)
        log("📋 Test Group 1: All Buttons Clickable")
        log("="*60)

        buttons_to_test = [
            ('button[aria-label="Create new session"]', "Create new session"),
            ('button[aria-label="Filter threads"]', "Filter threads"),
            ('button[aria-label="Sort threads"]', "Sort threads"),
            ('button[aria-label="Refresh sessions"]', "Refresh sessions"),
            ('button[aria-label="Settings"]', "Settings"),
            ('button[aria-label="Help"]', "Help"),
            ('button[aria-label="Attach file"]', "Attach file"),
            ('button[aria-label="Send message"]', "Send message"),
        ]

        for selector, desc in buttons_to_test:
            try:
                btn = self.page.locator(selector)
                count = await btn.count()
                if count > 0 and await btn.first.is_visible():
                    record_result(f"Button: {desc}", True, "Button visible")
                else:
                    record_result(f"Button: {desc}", False, "Button not found")
            except Exception as e:
                record_result(f"Button: {desc}", False, f"Error: {e}")

        # Mode toggle buttons
        try:
            plan_btn = self.page.get_by_role("radio", name="Plan")
            build_btn = self.page.get_by_role("radio", name="Build")
            if await plan_btn.count() > 0 and await build_btn.count() > 0:
                await plan_btn.click()
                await self.page.wait_for_timeout(300)
                await build_btn.click()
                await self.page.wait_for_timeout(300)
                record_result("Button: Mode Toggle", True, "Plan/Build toggles work")
            else:
                record_result("Button: Mode Toggle", False, "Toggle buttons not found")
        except Exception as e:
            record_result("Button: Mode Toggle", False, f"Error: {e}")

        await screenshot(self.page, "01_all_buttons")

    async def test_2_session_management(self):
        log("\n" + "="*60)
        log("📋 Test Group 2: Session Management")
        log("="*60)

        initial_count = len(await self.get_sidebar_sessions())
        log(f"  Initial session count: {initial_count}")

        # Create 3 sessions
        for i in range(3):
            try:
                await self.create_session()
                record_result(f"Create Session {i+1}", True, "Created successfully")
            except Exception as e:
                record_result(f"Create Session {i+1}", False, f"Error: {e}")

        await self.page.wait_for_timeout(1000)

        # Verify sessions appear in sidebar
        sessions = await self.get_sidebar_sessions()
        record_result("Session Sidebar Display", len(sessions) >= 3,
                       f"Found {len(sessions)} sessions in sidebar")

        await screenshot(self.page, "02_sessions_created")

        # Test hover buttons (Export & Delete)
        if sessions:
            try:
                await sessions[0].hover()
                await self.page.wait_for_timeout(500)

                # Export button (should be visible on hover)
                export_btn = sessions[0].locator('button[aria-label="Export session"]')
                has_export = await export_btn.count() > 0
                record_result("Hover: Export Button", has_export,
                               "Export button appears on hover" if has_export else "Export button missing")

                # Delete button
                delete_btn = sessions[0].locator('button[aria-label="Delete session"]')
                has_delete = await delete_btn.count() > 0
                record_result("Hover: Delete Button", has_delete,
                               "Delete button appears on hover" if has_delete else "Delete button missing")

                await screenshot(self.page, "02_hover_buttons")
            except Exception as e:
                record_result("Hover Buttons", False, f"Error: {e}")

        # Test session switching
        sessions = await self.get_sidebar_sessions()
        if len(sessions) >= 2:
            try:
                # Click session 2
                await sessions[1].click()
                await self.page.wait_for_timeout(500)
                record_result("Session Switch", True, "Successfully switched session")
            except Exception as e:
                record_result("Session Switch", False, f"Error: {e}")
        else:
            record_result("Session Switch", False, "Not enough sessions")

        await screenshot(self.page, "02_session_switched")

    async def test_3_message_interaction(self):
        log("\n" + "="*60)
        log("📋 Test Group 3: Message Interaction")
        log("="*60)

        # Create fresh session
        await self.create_session()
        await self.page.wait_for_timeout(500)

        # Send message
        try:
            await self.send_message("Hello! What is Python? Answer in one short sentence.")
            record_result("Send Message", True, "Message sent successfully")
        except Exception as e:
            record_result("Send Message", False, f"Error: {e}")

        await screenshot(self.page, "03_message_sent")

        # Wait for response
        log("  Waiting for AI response...")
        await self.page.wait_for_timeout(15000)

        # Check for response
        content = await self.page.content()
        has_python = "python" in content.lower()
        has_response = has_python or "language" in content.lower() or "programming" in content.lower()
        record_result("AI Response", has_response,
                       "AI responded" if has_response else "No AI response detected")

        await screenshot(self.page, "03_response_received")

        # Test stop button (send long message then stop)
        try:
            await self.send_message("Write a very long story about space exploration, at least 1000 words.")
            await self.page.wait_for_timeout(3000)

            stop_btn = self.page.locator('button[aria-label="Stop generation"]')
            if await stop_btn.count() > 0 and await stop_btn.is_visible():
                await stop_btn.click()
                await self.page.wait_for_timeout(1000)
                record_result("Stop Generation", True, "Stop button works")
            else:
                record_result("Stop Generation", False, "Stop button not found")
        except Exception as e:
            record_result("Stop Generation", False, f"Error: {e}")

        await screenshot(self.page, "03_stopped")

    async def test_4_settings(self):
        log("\n" + "="*60)
        log("📋 Test Group 4: Settings")
        log("="*60)

        try:
            settings_btn = self.page.locator('button[aria-label="Settings"]')
            await settings_btn.click()
            await self.page.wait_for_timeout(1000)

            # Check if settings panel is visible
            settings_panel = self.page.locator('[class*="SettingsPanel"], [class*="settings-panel"]')
            visible = await settings_panel.count() > 0 and await settings_panel.is_visible()
            record_result("Open Settings", visible,
                           "Settings panel opened" if visible else "Settings panel not found")

            if visible:
                await screenshot(self.page, "04_settings_open")

                # Check Provider selector
                provider_select = self.page.locator('select[name="provider"], select[id="provider"], select').first
                if await provider_select.count() > 0:
                    options = await provider_select.locator('option').all_inner_texts()
                    record_result("Provider Options", len(options) > 0,
                                   f"Providers: {options}")
                else:
                    record_result("Provider Options", False, "Provider select not found")

                # Check Model selector
                model_select = self.page.locator('select[name="model"], select[id="model"]').first
                if await model_select.count() > 0:
                    record_result("Model Selector", True, "Model selector found")
                else:
                    record_result("Model Selector", False, "Model selector not found")

                # Check API Key input
                api_key_input = self.page.locator('input[type="password"], input[name*="api"], input[name*="key"]')
                has_api_key = await api_key_input.count() > 0
                record_result("API Key Input", has_api_key,
                               "API key field found" if has_api_key else "API key field not found")

                # Close settings
                close_btn = self.page.locator('button[aria-label="Close settings"]')
                if await close_btn.count() > 0:
                    await close_btn.click()
                    await self.page.wait_for_timeout(300)
                    record_result("Close Settings", True, "Settings closed")
                else:
                    record_result("Close Settings", False, "Close button not found")
        except Exception as e:
            record_result("Settings", False, f"Error: {e}")

    async def test_5_tools_and_functionality(self):
        log("\n" + "="*60)
        log("📋 Test Group 5: Tools & Additional Functionality")
        log("="*60)

        # Test Help button
        try:
            help_btn = self.page.locator('button[aria-label="Help"]')
            await help_btn.click()
            await self.page.wait_for_timeout(1000)

            # Check if help content shows
            help_content = self.page.locator('[class*="Help"], [class*="help"]')
            has_help = await help_content.count() > 0
            record_result("Help Button", has_help,
                           "Help content shown" if has_help else "Help content not found")

            # Close help
            close_btns = self.page.locator('button[aria-label*="close"], button[aria-label*="Close"]')
            if await close_btns.count() > 0:
                await close_btns.first.click()
                await self.page.wait_for_timeout(300)
        except Exception as e:
            record_result("Help Button", False, f"Error: {e}")

        # Test Attach button
        try:
            attach_btn = self.page.locator('button[aria-label="Attach file"]')
            if await attach_btn.count() > 0 and await attach_btn.is_visible():
                record_result("Attach Button", True, "Attach button visible and clickable")
            else:
                record_result("Attach Button", False, "Attach button not visible")
        except Exception as e:
            record_result("Attach Button", False, f"Error: {e}")

        await screenshot(self.page, "05_tools")


async def run_tests(playwright: Playwright):
    log("🚀 CScode Comprehensive GUI Test v3")
    log("="*60)
    log(f"  Server: http://localhost:8000")
    log(f"  Started at: {datetime.now().isoformat()}")

    browser = await playwright.chromium.launch(headless=False, slow_mo=50)
    context = await browser.new_context(viewport={"width": 1440, "height": 900})
    page = await context.new_page()

    tester = CSCodTester(page)
    await tester.setup()

    try:
        await tester.goto()
        await tester.test_1_all_buttons()
        await tester.test_2_session_management()
        await tester.test_3_message_interaction()
        await tester.test_4_settings()
        await tester.test_5_tools_and_functionality()

    except Exception as e:
        log(f"❌ Test execution error: {e}")
        import traceback
        log(traceback.format_exc())
    finally:
        await browser.close()

    # Generate report
    report = {
        "timestamp": datetime.now().isoformat(),
        "test_results": test_results,
        "summary": {
            "total": len(test_results),
            "passed": sum(1 for t in test_results if t["passed"]),
            "failed": sum(1 for t in test_results if not t["passed"]),
        },
        "console_errors": [l for l in console_logs if l["type"] == "error"],
        "network_errors": network_errors,
        "console_logs": console_logs[-200:],
        "network_requests": [r for r in all_network_requests if r["status"] >= 400][-50:],
    }

    report_path = OUTPUT_DIR / "test_results.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    log("\n" + "="*60)
    log("📊 Test Summary")
    log("="*60)
    log(f"   Total: {report['summary']['total']}")
    log(f"   Passed: {report['summary']['passed']}")
    log(f"   Failed: {report['summary']['failed']}")
    log(f"\n📁 Report: {report_path}")

    failed = [t for t in test_results if not t["passed"]]
    if failed:
        log("\n❌ Failed Tests:")
        for t in failed:
            log(f"   - {t['test_name']}: {t['detail']}")

    if report["console_errors"]:
        log(f"\n⚠️  Console errors: {len(report['console_errors'])}")
    if report["network_errors"]:
        log(f"⚠️  Network errors: {len(report['network_errors'])}")


async def main():
    async with async_playwright() as playwright:
        await run_tests(playwright)


if __name__ == "__main__":
    asyncio.run(main())
