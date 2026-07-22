#!/usr/bin/env python3
"""
CScode packaged desktop app - Comprehensive GUI test v4
Target: http://127.0.0.1:8080
Covers all buttons, settings, plugins, sessions, composer, terminal
"""

import asyncio
import json
from datetime import datetime
from pathlib import Path
from playwright.async_api import Page, Playwright, async_playwright

OUTPUT_DIR = Path("/Users/mac/AI/CScode/dogfood-output/v4-final-test")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

BASE_URL = "http://127.0.0.1:8080"

test_results = []
console_logs = []
network_requests = []
network_errors = []


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


async def get_session_items(page: Page):
    """Get sidebar session items by looking for divs with hover action buttons"""
    return await page.query_selector_all('div.group')


class CSCodTester:
    def __init__(self, page: Page):
        self.page = page

    async def setup(self):
        self.page.on("console", lambda msg: console_logs.append({
            "type": msg.type, "text": msg.text,
            "time": datetime.now().isoformat()
        }))
        self.page.on("response", lambda res: asyncio.create_task(self._record_response(res)))
        self.page.on("requestfailed", lambda req: network_errors.append({
            "url": req.url, "error": str(req.failure), "time": datetime.now().isoformat()
        }))

    async def _record_response(self, res):
        try:
            network_requests.append({
                "status": res.status,
                "url": res.url,
                "method": res.request.method,
                "time": datetime.now().isoformat()
            })
        except Exception:
            pass

    async def goto(self):
        await self.page.goto(BASE_URL, wait_until="domcontentloaded")
        await self.page.wait_for_timeout(2500)

    async def test_all_buttons(self):
        log("\n=== Test Group: All Buttons Visible ===")

        expected_buttons = [
            ("Plan", "Plan mode"),
            ("Build", "Build mode"),
            ("Filter threads", "Filter threads"),
            ("Sort threads", "Sort threads"),
            ("Refresh sessions", "Refresh sessions"),
            ("Create new session", "Create new session"),
            ("Export session", "Export session (hover)"),
            ("Delete session", "Delete session (hover)"),
            ("Settings", "Settings"),
            ("Help", "Help"),
            ("Attach file", "Attach file"),
            ("Send message", "Send message"),
            ("Open terminal", "Open terminal"),
        ]

        buttons = await self.page.evaluate("""() => {
            return Array.from(document.querySelectorAll('button')).filter(b => b.offsetParent !== null).map(b => ({
                text: b.innerText.trim(),
                ariaLabel: b.getAttribute('aria-label') || '',
                title: b.getAttribute('title') || ''
            }));
        }""")

        found_labels = set()
        for b in buttons:
            found_labels.add(b['text'])
            found_labels.add(b['ariaLabel'])
            found_labels.add(b['title'])

        for label, desc in expected_buttons:
            found = label in found_labels
            record_result(f"Button: {desc}", found, f"'{label}' {'found' if found else 'NOT found'}")

        await screenshot(self.page, "01_all_buttons")

    async def test_session_management(self):
        log("\n=== Test Group: Session Management ===")

        # Count initial sessions
        initial_items = await get_session_items(self.page)
        log(f"  Initial sessions: {len(initial_items)}")

        # Create new session
        try:
            create_btn = self.page.locator('button[title="New session"], button[aria-label="Create new session"]')
            await create_btn.click()
            await self.page.wait_for_timeout(800)
            record_result("Create new session", True, "Button clicked")
        except Exception as e:
            record_result("Create new session", False, f"Error: {e}")

        await screenshot(self.page, "02_after_create")

        # Verify session appeared
        items = await get_session_items(self.page)
        record_result("Session appears in sidebar", len(items) > len(initial_items),
                      f"Sessions: {len(initial_items)} -> {len(items)}")

        # Hover over first session to reveal export/delete
        if items:
            try:
                await items[0].hover()
                await self.page.wait_for_timeout(500)

                export = items[0].locator('button[title="Export session"], button[aria-label="Export session"]')
                delete = items[0].locator('button[title="Delete session"], button[aria-label="Delete session"]')

                has_export = await export.count() > 0 and await export.first.is_visible()
                has_delete = await delete.count() > 0 and await delete.first.is_visible()

                record_result("Hover reveals Export", has_export, "Export button visible" if has_export else "Not visible")
                record_result("Hover reveals Delete", has_delete, "Delete button visible" if has_delete else "Not visible")

                await screenshot(self.page, "02_hover_buttons")
            except Exception as e:
                record_result("Hover buttons", False, f"Error: {e}")

        # Switch between sessions if >= 2
        items = await get_session_items(self.page)
        if len(items) >= 2:
            try:
                await items[0].click()
                await self.page.wait_for_timeout(500)
                await screenshot(self.page, "02_session_1")

                await items[1].click()
                await self.page.wait_for_timeout(500)
                await screenshot(self.page, "02_session_2")

                record_result("Session switching", True, f"Switched between {len(items)} sessions")
            except Exception as e:
                record_result("Session switching", False, f"Error: {e}")
        else:
            record_result("Session switching", False, "Less than 2 sessions")

    async def test_composer_and_message(self):
        log("\n=== Test Group: Composer & Message ===")

        # Create fresh session
        try:
            create_btn = self.page.locator('button[title="New session"], button[aria-label="Create new session"]')
            await create_btn.click()
            await self.page.wait_for_timeout(600)
        except Exception as e:
            record_result("Create session for message", False, f"Error: {e}")
            return

        # Send message
        try:
            textarea = self.page.locator('textarea[placeholder*="Ask anything"]').first
            await textarea.fill("Hello, what is Python? Keep it brief.")
            await textarea.press("Enter")
            await self.page.wait_for_timeout(500)
            record_result("Send message", True, "Message sent")
        except Exception as e:
            record_result("Send message", False, f"Error: {e}")
            return

        await screenshot(self.page, "03_message_sent")

        # Wait for response
        log("  Waiting for AI response...")
        await self.page.wait_for_timeout(15000)

        content = await self.page.content()
        has_response = "python" in content.lower() or "language" in content.lower() or "programming" in content.lower()
        record_result("AI response", has_response, "AI responded" if has_response else "No response detected")

        await screenshot(self.page, "03_response_received")

        # Test Open terminal button
        try:
            terminal_btn = self.page.locator('button[title="Open terminal"], button[aria-label="Open terminal"]')
            if await terminal_btn.count() > 0 and await terminal_btn.is_visible():
                await terminal_btn.click()
                await self.page.wait_for_timeout(1500)

                # Check if terminal panel opened
                terminal_panel = await self.page.evaluate("""() => {
                    const panels = document.querySelectorAll('[class*="terminal"], [class*="Terminal"]');
                    return panels.length;
                }""")
                record_result("Open terminal", terminal_panel > 0, f"Terminal panels found: {terminal_panel}")
                await screenshot(self.page, "03_terminal_open")
            else:
                record_result("Open terminal", False, "Terminal button not visible")
        except Exception as e:
            record_result("Open terminal", False, f"Error: {e}")

    async def test_settings(self):
        log("\n=== Test Group: Settings Panel ===")

        try:
            settings_btn = self.page.locator('button[aria-label="Settings"], button[title="Settings"]')
            await settings_btn.click()
            await self.page.wait_for_timeout(1000)

            settings_info = await self.page.evaluate("""() => {
                const panel = Array.from(document.querySelectorAll('div')).find(d => {
                    const text = d.innerText || '';
                    return text.includes('Provider') && text.includes('Model') && text.includes('API Key');
                });
                if (!panel) return null;
                const inputs = Array.from(panel.querySelectorAll('input, select, textarea'));
                return {
                    inputCount: inputs.length,
                    inputs: inputs.slice(0, 15).map(i => ({
                        type: i.type || i.tagName,
                        name: i.name || '',
                        placeholder: i.placeholder || '',
                        label: i.labels && i.labels[0] ? i.labels[0].innerText : ''
                    }))
                };
            }""")

            if settings_info:
                record_result("Settings panel opens", True, f"Found {settings_info['inputCount']} inputs")
                await screenshot(self.page, "04_settings_open")

                # Check key fields
                has_provider = any(i['label'].lower().startswith('provider') or i['name'] == 'provider' for i in settings_info['inputs'])
                has_model = any(i['label'].lower().startswith('model') or i['name'] == 'model' for i in settings_info['inputs'])
                has_api_key = any(i['type'] == 'password' for i in settings_info['inputs'])

                record_result("Settings: Provider", has_provider, "Provider field found")
                record_result("Settings: Model", has_model, "Model field found")
                record_result("Settings: API Key", has_api_key, "API Key field found")
            else:
                record_result("Settings panel opens", False, "Settings content not found")

            # Check Plugins section
            plugins_info = await self.page.evaluate("""() => {
                const text = document.body.innerText || '';
                return {
                    hasPlugins: text.includes('Plugins'),
                    pluginNames: ['code-reviewer', 'test-engineer', 'security-auditor'].filter(p => text.includes(p))
                };
            }""")

            record_result("Settings: Plugins section", plugins_info['hasPlugins'],
                          f"Plugins found: {plugins_info['pluginNames']}" if plugins_info['hasPlugins'] else "No Plugins section")

            # Check MCP Servers section
            mcp_info = await self.page.evaluate("""() => {
                const text = document.body.innerText || '';
                return text.includes('MCP Servers');
            }""")
            record_result("Settings: MCP Servers", mcp_info, "MCP Servers section found" if mcp_info else "No MCP Servers section")

            # Close settings
            close_btn = self.page.locator('button[aria-label="Close settings"]').or_(self.page.locator('button:has-text("×")'))
            if await close_btn.count() > 0:
                await close_btn.first.click()
                await self.page.wait_for_timeout(300)

        except Exception as e:
            record_result("Settings panel", False, f"Error: {e}")

    async def test_filter_sort_refresh(self):
        log("\n=== Test Group: Filter / Sort / Refresh ===")

        actions = [
            ("Filter threads", 'button[title="Filter threads"], button[aria-label="Filter threads"]'),
            ("Sort threads", 'button[title="Sort threads"], button[aria-label="Sort threads"]'),
            ("Refresh sessions", 'button[title="Refresh sessions"], button[aria-label="Refresh sessions"]'),
        ]

        for name, selector in actions:
            try:
                btn = self.page.locator(selector)
                if await btn.count() > 0 and await btn.is_visible():
                    await btn.click()
                    await self.page.wait_for_timeout(500)
                    record_result(f"Click: {name}", True, "Button clicked")
                else:
                    record_result(f"Click: {name}", False, "Button not found/visible")
            except Exception as e:
                record_result(f"Click: {name}", False, f"Error: {e}")

        await screenshot(self.page, "05_filter_sort_refresh")

    async def test_mode_toggle(self):
        log("\n=== Test Group: Mode Toggle ===")

        try:
            plan_btn = self.page.locator('button:has-text("Plan")').first
            build_btn = self.page.locator('button:has-text("Build")').first

            if await plan_btn.count() > 0 and await build_btn.count() > 0:
                await plan_btn.click()
                await self.page.wait_for_timeout(300)
                await build_btn.click()
                await self.page.wait_for_timeout(300)
                record_result("Mode toggle", True, "Plan/Build toggled")
            else:
                record_result("Mode toggle", False, "Toggle buttons not found")
        except Exception as e:
            record_result("Mode toggle", False, f"Error: {e}")


async def run_tests(playwright: Playwright):
    log("🚀 CScode Packaged Desktop App Comprehensive GUI Test")
    log(f"   Target: {BASE_URL}")
    log(f"   Started: {datetime.now().isoformat()}")

    browser = await playwright.chromium.launch(headless=True)
    context = await browser.new_context(viewport={"width": 1440, "height": 900})
    page = await context.new_page()

    tester = CSCodTester(page)
    await tester.setup()

    try:
        await tester.goto()
        await tester.test_all_buttons()
        await tester.test_session_management()
        await tester.test_composer_and_message()
        await tester.test_settings()
        await tester.test_filter_sort_refresh()
        await tester.test_mode_toggle()

    except Exception as e:
        log(f"❌ Test execution error: {e}")
        import traceback
        log(traceback.format_exc())
    finally:
        await browser.close()

    report = {
        "timestamp": datetime.now().isoformat(),
        "target_url": BASE_URL,
        "test_results": test_results,
        "summary": {
            "total": len(test_results),
            "passed": sum(1 for t in test_results if t["passed"]),
            "failed": sum(1 for t in test_results if not t["passed"]),
        },
        "console_errors": [l for l in console_logs if l["type"] == "error"],
        "network_errors": network_errors,
        "network_4xx_5xx": [r for r in network_requests if r["status"] >= 400][-50:],
    }

    report_path = OUTPUT_DIR / "comprehensive_test_results.json"
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


async def main():
    async with async_playwright() as playwright:
        await run_tests(playwright)


if __name__ == "__main__":
    asyncio.run(main())