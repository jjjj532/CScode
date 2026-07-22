#!/usr/bin/env python3
"""
CScode packaged app - Concurrent Session Isolation Test v4
Creates 2 sessions, sends different messages, switches during streaming,
verifies content isolation and no message leakage.
"""

import asyncio
import json
from datetime import datetime
from pathlib import Path
from playwright.async_api import Page, Playwright, async_playwright

OUTPUT_DIR = Path("/Users/mac/AI/CScode/dogfood-output/v4-final-test")
BASE_URL = "http://127.0.0.1:8080"

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


async def get_session_items(page: Page):
    """Get visible sidebar session items (div.group)"""
    items = await page.query_selector_all('div.group')
    result = []
    for item in items:
        if await item.is_visible():
            text = await item.inner_text()
            result.append({"el": item, "text": text.strip()})
    return result


async def create_session(page: Page):
    btn = page.locator('button[aria-label="Create new session"], button[title="New session"]')
    await btn.click()
    await page.wait_for_timeout(700)


async def send_message(page: Page, text: str):
    textarea = page.locator('textarea[placeholder*="Ask anything"]').first
    await textarea.fill(text)
    await textarea.press("Enter")
    await page.wait_for_timeout(500)


async def count_keyword(page: Page, keyword: str):
    content = await page.content()
    return content.lower().count(keyword.lower())


async def main():
    async with async_playwright() as p:
        log("🚀 CScode Packaged App - Concurrent Session Isolation Test")
        log(f"   Target: {BASE_URL}")

        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1440, "height": 900})
        page = await context.new_page()

        page.on("console", lambda msg: console_logs.append({
            "type": msg.type, "text": msg.text,
            "time": datetime.now().isoformat()
        }))

        await page.goto(BASE_URL, wait_until="domcontentloaded")
        await page.wait_for_timeout(2000)

        # === Phase 1: Create Session A and send message ===
        log("\n=== Phase 1: Create Session A ===")
        await create_session(page)
        await send_message(page, "Explain Python programming language in detail. Mention at least 8 Python features.")

        python_count_a_start = await count_keyword(page, "python")
        log(f"  Session A initial 'python' count: {python_count_a_start}")

        await screenshot(page, "iso_01_session_a_started")

        # === Phase 2: Create Session B and send message ===
        log("\n=== Phase 2: Create Session B ===")
        await create_session(page)
        await send_message(page, "Explain JavaScript programming language in detail. Mention at least 8 JavaScript features.")

        js_count_b_start = await count_keyword(page, "javascript")
        log(f"  Session B initial 'javascript' count: {js_count_b_start}")

        await screenshot(page, "iso_02_session_b_started")

        # === Phase 3: Switch rapidly during streaming ===
        log("\n=== Phase 3: Rapid session switching during streaming ===")

        for i in range(5):
            items = await get_session_items(page)
            if len(items) >= 2:
                await items[0]["el"].click()
                await page.wait_for_timeout(600)
                await items[1]["el"].click()
                await page.wait_for_timeout(600)
            log(f"  Switch cycle {i+1}/5 done")

        await screenshot(page, "iso_03_after_rapid_switch")

        # === Phase 4: Wait for both to complete ===
        log("\n=== Phase 4: Wait for responses ===")
        await page.wait_for_timeout(20000)

        # === Phase 5: Verify Session A content ===
        log("\n=== Phase 5: Verify Session A content ===")
        items = await get_session_items(page)
        if len(items) >= 2:
            await items[0]["el"].click()
            await page.wait_for_timeout(1000)

            await screenshot(page, "iso_04_session_a_final")

            python_count_a_final = await count_keyword(page, "python")
            js_in_a = await count_keyword(page, "javascript")

            log(f"  Session A final 'python' count: {python_count_a_final}")
            log(f"  Session A 'javascript' count: {js_in_a}")

            record_result("Session A content preserved",
                          python_count_a_final >= python_count_a_start,
                          f"Python: {python_count_a_start} -> {python_count_a_final}")

            record_result("No JS leakage into Session A",
                          js_in_a <= 2,
                          f"JavaScript mentions in A: {js_in_a}")

            # === Phase 6: Verify Session B content ===
            log("\n=== Phase 6: Verify Session B content ===")
            await items[1]["el"].click()
            await page.wait_for_timeout(1000)

            await screenshot(page, "iso_05_session_b_final")

            js_count_b_final = await count_keyword(page, "javascript")
            python_in_b = await count_keyword(page, "python")

            log(f"  Session B final 'javascript' count: {js_count_b_final}")
            log(f"  Session B 'python' count: {python_in_b}")

            record_result("Session B content preserved",
                          js_count_b_final >= js_count_b_start,
                          f"JavaScript: {js_count_b_start} -> {js_count_b_final}")

            record_result("No Python leakage into Session B",
                          python_in_b <= 2,
                          f"Python mentions in B: {python_in_b}")
        else:
            record_result("Session verification", False, f"Only {len(items)} sessions found")

        # === Phase 7: Log analysis ===
        log("\n=== Phase 7: Log analysis ===")

        applyevent_logs = [l for l in console_logs if "applyEvent" in l["text"]]
        setmessages_logs = [l for l in console_logs if "setMessages" in l["text"]]
        appendmessage_logs = [l for l in console_logs if "appendMessage" in l["text"]]
        wrong_session = [l for l in console_logs if "wrong session" in l["text"].lower()]
        dropped = [l for l in console_logs if "DROPPED" in l["text"]]
        superseded = [l for l in console_logs if "superseded" in l["text"].lower()]

        log(f"  applyEvent calls: {len(applyevent_logs)}")
        log(f"  setMessages calls: {len(setmessages_logs)}")
        log(f"  appendMessage calls: {len(appendmessage_logs)}")
        log(f"  wrong session events: {len(wrong_session)}")
        log(f"  DROPPED events: {len(dropped)}")
        log(f"  superseded streams: {len(superseded)}")

        record_result("No wrong session events", len(wrong_session) == 0,
                      f"Wrong session: {len(wrong_session)}")
        record_result("No stream superseded", len(superseded) == 0,
                      f"Superseded: {len(superseded)}")
        record_result("Events processed", len(applyevent_logs) > 0 or len(appendmessage_logs) > 0,
                      f"applyEvent={len(applyevent_logs)}, appendMessage={len(appendmessage_logs)}")

        # Show sample logs
        log("\n  Sample setMessages logs:")
        for l in setmessages_logs[:5]:
            log(f"    {l['text'][:120]}")

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
            "console_logs": console_logs[-400:],
            "log_counts": {
                "applyEvent": len(applyevent_logs),
                "setMessages": len(setmessages_logs),
                "appendMessage": len(appendmessage_logs),
                "wrong_session": len(wrong_session),
                "dropped": len(dropped),
                "superseded": len(superseded)
            }
        }

        with open(OUTPUT_DIR / "isolation_test_results.json", "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

        log("\n" + "="*60)
        log("📊 Isolation Test Summary")
        log("="*60)
        log(f"   Total: {report['summary']['total']}")
        log(f"   Passed: {report['summary']['passed']}")
        log(f"   Failed: {report['summary']['failed']}")

        failed = [t for t in test_results if not t["passed"]]
        if failed:
            log("\n❌ Failed Tests:")
            for t in failed:
                log(f"   - {t['test_name']}: {t['detail']}")


if __name__ == "__main__":
    asyncio.run(main())