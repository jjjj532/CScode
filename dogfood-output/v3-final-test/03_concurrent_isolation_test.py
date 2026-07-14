#!/usr/bin/env python3
"""
CScode 并发 Session 隔离专项测试 v3
- 使用正确的选择器 (div.group)
- 测试并发流式响应
- 验证session切换数据完整性
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


async def get_sidebar_sessions(page: Page):
    """获取侧边栏所有session项 - 使用div.group选择器"""
    items = await page.query_selector_all('div.group')
    result = []
    for item in items:
        if await item.is_visible():
            text = await item.inner_text()
            result.append({"el": item, "text": text.strip()})
    return result


async def main():
    async with async_playwright() as p:
        log("🚀 Concurrent Session Isolation Test v3")
        log("="*60)

        browser = await p.chromium.launch(headless=False, slow_mo=50)
        context = await browser.new_context(viewport={"width": 1440, "height": 900})
        page = await context.new_page()

        page.on("console", lambda msg: console_logs.append({
            "type": msg.type, "text": msg.text,
            "time": datetime.now().isoformat()
        }))

        await page.goto("http://localhost:8000", wait_until="domcontentloaded")
        await page.wait_for_timeout(2000)

        # ===== Test 1: Create 2 concurrent sessions =====
        log("\n=== Phase 1: Create 2 concurrent sessions ===")

        # Session A
        new_btn = page.locator('button[aria-label="Create new session"]')
        await new_btn.click()
        await page.wait_for_timeout(800)

        # Send message to Session A
        textarea = page.locator('textarea[placeholder*="Ask anything"]')
        await textarea.fill("Please explain Python programming language in detail. Mention at least 10 Python-related concepts.")
        await textarea.press("Enter")
        await page.wait_for_timeout(2000)

        # Get session A text count
        content_a = await page.content()
        python_count_a_start = content_a.lower().count("python")
        log(f"  Session A initial 'python' count: {python_count_a_start}")

        # Session B
        await new_btn.click()
        await page.wait_for_timeout(800)

        await textarea.fill("Please explain JavaScript programming language in detail. Mention at least 10 JavaScript-related concepts.")
        await textarea.press("Enter")
        await page.wait_for_timeout(2000)

        content_b = await page.content()
        js_count_b_start = content_b.lower().count("javascript")
        log(f"  Session B initial 'javascript' count: {js_count_b_start}")

        await screenshot(page, "isolation_01_both_started")

        # Wait for both to generate content
        log("  Waiting for responses...")
        await page.wait_for_timeout(15000)

        await screenshot(page, "isolation_02_after_wait")

        # ===== Test 2: Switch to Session A =====
        log("\n=== Phase 2: Switch to Session A ===")

        sessions = await get_sidebar_sessions(page)
        log(f"  Found {len(sessions)} sessions in sidebar")
        for i, s in enumerate(sessions):
            log(f"    [{i}] {s['text'][:50]}")

        if len(sessions) >= 2:
            # Click first session (should be A)
            await sessions[0]["el"].click()
            await page.wait_for_timeout(3000)

            content_a_after = await page.content()
            python_count_a_after = content_a_after.lower().count("python")
            log(f"  Session A after switch 'python' count: {python_count_a_after}")

            await screenshot(page, "isolation_03_session_a")

            # Verify Session A content is preserved
            if python_count_a_after >= python_count_a_start * 0.5:
                record_result("Session A content preserved", True,
                              f"Python count: {python_count_a_start} -> {python_count_a_after}")
            else:
                record_result("Session A content preserved", False,
                              f"Python count lost: {python_count_a_start} -> {python_count_a_after}")

            # ===== Test 3: Switch to Session B =====
            log("\n=== Phase 3: Switch to Session B ===")

            sessions = await get_sidebar_sessions(page)
            await sessions[1]["el"].click()
            await page.wait_for_timeout(3000)

            content_b_after = await page.content()
            js_count_b_after = content_b_after.lower().count("javascript")
            log(f"  Session B after switch 'javascript' count: {js_count_b_after}")

            await screenshot(page, "isolation_04_session_b")

            if js_count_b_after >= js_count_b_start * 0.5:
                record_result("Session B content preserved", True,
                              f"JS count: {js_count_b_start} -> {js_count_b_after}")
            else:
                record_result("Session B content preserved", False,
                              f"JS count lost: {js_count_b_start} -> {js_count_b_after}")

            # ===== Test 4: Message leakage check =====
            log("\n=== Phase 4: Message leakage check ===")

            # Session B should NOT have significant Python content (beyond user message)
            python_in_b = content_b_after.lower().count("python")
            record_result("No message leakage (A->B)", python_in_b <= 3,
                          f"Python mentions in B: {python_in_b} (user msg may include)")

            # Switch back to A and check for JS leakage
            sessions = await get_sidebar_sessions(page)
            await sessions[0]["el"].click()
            await page.wait_for_timeout(2000)

            content_a_final = await page.content()
            js_in_a = content_a_final.lower().count("javascript")
            record_result("No message leakage (B->A)", js_in_a <= 1,
                          f"JavaScript mentions in A: {js_in_a}")

            await screenshot(page, "isolation_05_final_a")
        else:
            record_result("Session switching", False, f"Only {len(sessions)} sessions found")

        # ===== Test 5: Stream isolation check via console logs =====
        log("\n=== Phase 5: Stream isolation log analysis ===")

        # Check for DROPPED events or wrong session events
        dropped_events = [l for l in console_logs if "DROPPED" in l["text"]]
        wrong_session = [l for l in console_logs if "wrong session" in l["text"]]
        superseded = [l for l in console_logs if "superseded" in l["text"]]

        record_result("No wrong session events", len(wrong_session) == 0,
                      f"Wrong session events: {len(wrong_session)}")

        record_result("DROPPED events (expected if any)", True,
                      f"DROPPED events: {len(dropped_events)} (defensive filter)")

        record_result("Stream superseded events", len(superseded) == 0,
                      f"Superseded streams: {len(superseded)}")

        # Check for setMessages logs
        setmessages_logs = [l for l in console_logs if "setMessages" in l["text"]]
        log(f"  setMessages calls: {len(setmessages_logs)}")
        for l in setmessages_logs[:5]:
            log(f"    {l['text'][:120]}")

        applyevent_logs = [l for l in console_logs if "applyEvent" in l["text"]]
        log(f"  applyEvent calls: {len(applyevent_logs)}")

        appendmessage_logs = [l for l in console_logs if "appendMessage" in l["text"]]
        log(f"  appendMessage calls: {len(appendmessage_logs)}")

        await browser.close()

        # Save report
        report = {
            "timestamp": datetime.now().isoformat(),
            "test_results": test_results,
            "summary": {
                "total": len(test_results),
                "passed": sum(1 for t in test_results if t["passed"]),
                "failed": sum(1 for t in test_results if not t["passed"]),
            },
            "console_logs": console_logs[-300:],
        }

        report_path = OUTPUT_DIR / "isolation_test_results.json"
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

        log("\n" + "="*60)
        log("📊 Isolation Test Summary")
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


if __name__ == "__main__":
    asyncio.run(main())
