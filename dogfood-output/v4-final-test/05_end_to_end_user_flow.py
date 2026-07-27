#!/usr/bin/env python3
"""
End-to-End Real User Flow Test for CScode GUI
Simulates a real user performing complete workflows.
"""

import asyncio
import json
import re
import sys
from datetime import datetime
from pathlib import Path

from playwright.async_api import async_playwright

BASE_URL = "http://127.0.0.1:18080"
OUTPUT_DIR = Path(__file__).parent / "e2e_screenshots"
OUTPUT_DIR.mkdir(exist_ok=True)

results = []

def log(msg: str):
    ts = datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    results.append(line)

async def screenshot(page, name: str):
    path = OUTPUT_DIR / f"{name}.png"
    await page.screenshot(path=str(path), full_page=False)
    log(f"  Screenshot: {path}")
    return str(path)

async def run_e2e():
    log("=== E2E Real User Flow Test ===")
    log(f"Base URL: {BASE_URL}")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1400, "height": 900})
        page = await context.new_page()

        # Helper to capture console errors
        console_errors = []
        page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
        page.on("pageerror", lambda err: console_errors.append(str(err)))

        # === STEP 1: Fresh load, check landing state ===
        log("\n[STEP 1] Fresh load - landing state")
        await page.goto(BASE_URL, wait_until="networkidle")
        await asyncio.sleep(1)
        await screenshot(page, "01_landing")

        # Check welcome screen
        welcome = await page.locator("text=AI-powered coding assistant").count()
        log(f"  Welcome screen visible: {welcome > 0}")

        # Check sidebar has no sessions initially (or shows empty state)
        session_items = await page.locator("[data-testid='session-item'], div.group").count()
        log(f"  Session count in sidebar: {session_items}")

        # === STEP 2: Create Session A ===
        log("\n[STEP 2] Create Session A")
        new_btn = page.locator("button[aria-label='Create new session']").first
        if await new_btn.count() == 0:
            new_btn = page.locator("button[title='New session']").first
        if await new_btn.count() == 0:
            new_btn = page.locator("button").filter(has_text=re.compile(r"New")).first
        log(f"  New session button found: {await new_btn.count() > 0}")
        await new_btn.click()
        await asyncio.sleep(0.8)
        await screenshot(page, "02_session_a_created")

        # Get session A ID from URL or sidebar
        url = page.url
        log(f"  URL after create: {url}")
        session_items = await page.locator("[data-testid='session-item'], div.group").count()
        log(f"  Session count after create: {session_items}")

        # === STEP 3: Send a message in Session A ===
        log("\n[STEP 3] Send message in Session A")
        textarea = page.locator("textarea[placeholder*='message'], textarea[placeholder*='ask']").first
        if await textarea.count() == 0:
            textarea = page.locator("textarea").first
        await textarea.fill("Hello, this is a test message from Session A")
        await asyncio.sleep(0.3)
        await screenshot(page, "03_message_typed")

        send_btn = page.locator("button[aria-label='Send message'], button:has-text('Send')").first
        if await send_btn.count() == 0:
            send_btn = page.locator("button[type='submit']").first
        await send_btn.click()
        await asyncio.sleep(0.5)
        await screenshot(page, "04_message_sent")

        # Wait a bit for loading/thinking state (even if LLM fails)
        await asyncio.sleep(3)
        await screenshot(page, "05_after_3s")

        # Check for loading indicator or error message
        thinking = await page.locator("text=Thinking, text=loading, .animate-spin").count()
        error_msg = await page.locator("text=error, text=failed, text=connection").count()
        log(f"  Thinking/loading indicators: {thinking}")
        log(f"  Error indicators: {error_msg}")

        # === STEP 4: Create Session B while A is still active ===
        log("\n[STEP 4] Create Session B")
        await new_btn.click()
        await asyncio.sleep(0.8)
        await screenshot(page, "06_session_b_created")

        session_items = await page.locator("[data-testid='session-item'], div.group").count()
        log(f"  Session count after B: {session_items}")

        # === STEP 5: Send different message in Session B ===
        log("\n[STEP 5] Send message in Session B")
        await textarea.fill("This is Session B with different content")
        await asyncio.sleep(0.3)
        await send_btn.click()
        await asyncio.sleep(3)
        await screenshot(page, "07_session_b_message")

        # === STEP 6: Switch back to Session A ===
        log("\n[STEP 6] Switch back to Session A")
        items = await page.locator("[data-testid='session-item'], div.group").all()
        if len(items) >= 2:
            await items[0].click()
            await asyncio.sleep(0.8)
            await screenshot(page, "08_back_to_session_a")

            # Check Session A still has its message (only in main content area, not sidebar)
            main_content = page.locator("main, .flex-1.flex.flex-col").first
            has_a_msg = await main_content.locator("text=Session A").count() if await main_content.count() > 0 else await page.locator("text=Session A").count()
            has_b_msg = await main_content.locator("text=Session B").count() if await main_content.count() > 0 else await page.locator("text=Session B").count()
            log(f"  Session A content preserved: {has_a_msg > 0}")
            log(f"  Session B content leaked into A: {has_b_msg > 0} (should be False)")
        else:
            log("  WARNING: Less than 2 sessions found, skip switch test")

        # === STEP 7: Switch to Session B ===
        log("\n[STEP 7] Switch to Session B")
        if len(items) >= 2:
            await items[1].click()
            await asyncio.sleep(0.8)
            await screenshot(page, "09_back_to_session_b")

            main_content = page.locator("main, .flex-1.flex.flex-col").first
            has_a_msg = await main_content.locator("text=Session A").count() if await main_content.count() > 0 else await page.locator("text=Session A").count()
            has_b_msg = await main_content.locator("text=Session B").count() if await main_content.count() > 0 else await page.locator("text=Session B").count()
            log(f"  Session B content preserved: {has_b_msg > 0}")
            log(f"  Session A content leaked into B: {has_a_msg > 0} (should be False)")

        # === STEP 8: Open Settings panel ===
        log("\n[STEP 8] Open Settings panel")
        settings_btn = page.locator("button[aria-label='Settings'], button[title='Settings']").first
        if await settings_btn.count() == 0:
            settings_btn = page.locator("button").filter(has_text="Settings").first
        await settings_btn.click()
        await asyncio.sleep(0.8)
        await screenshot(page, "10_settings_open")

        # Try to interact with Provider selector
        provider_select = page.locator("select").first
        if await provider_select.count() > 0:
            options = await provider_select.locator("option").all_text_contents()
            log(f"  Provider options: {options}")
            # Try changing provider
            if len(options) > 1:
                await provider_select.select_option(options[1])
                await asyncio.sleep(0.3)
                await screenshot(page, "11_provider_changed")
                log(f"  Changed provider to: {options[1]}")
        else:
            log("  WARNING: No <select> found in Settings")

        # Close settings (click backdrop or close button)
        close_btn = page.locator("button:has-text('Close'), button[aria-label='Close']").first
        if await close_btn.count() > 0:
            await close_btn.click()
            await asyncio.sleep(0.5)
        # Also click backdrop to ensure panel is closed
        backdrop = page.locator("div.fixed.inset-0.z-50").first
        if await backdrop.count() > 0:
            await backdrop.click(position={"x": 10, "y": 10})
            await asyncio.sleep(0.3)

        # === STEP 9: Open Terminal ===
        log("\n[STEP 9] Open Terminal")
        terminal_btn = page.locator("button[aria-label='Open terminal'], button[title='Open terminal']").first
        if await terminal_btn.count() == 0:
            terminal_btn = page.locator("button").filter(has_text="Terminal").first
        if await terminal_btn.count() > 0:
            await terminal_btn.click()
            await asyncio.sleep(1)
            await screenshot(page, "12_terminal_open")
            log("  Terminal opened")
        else:
            log("  WARNING: Terminal button not found")

        # === STEP 10: Try Plan mode toggle ===
        log("\n[STEP 10] Toggle Plan/Build mode")
        plan_btn = page.locator("button:has-text('Plan')").first
        build_btn = page.locator("button:has-text('Build')").first
        if await plan_btn.count() > 0 and await build_btn.count() > 0:
            await plan_btn.click()
            await asyncio.sleep(0.3)
            await screenshot(page, "13_plan_mode")
            log("  Plan mode activated")
            await build_btn.click()
            await asyncio.sleep(0.3)
            await screenshot(page, "14_build_mode")
            log("  Build mode activated")
        else:
            log("  WARNING: Plan/Build buttons not found")

        # === STEP 11: Export session ===
        log("\n[STEP 11] Export session")
        # Hover over session to reveal export
        if len(items) >= 1:
            await items[0].hover()
            await asyncio.sleep(0.5)
            export_btn = page.locator("button[aria-label='Export session'], button[title='Export']").first
            if await export_btn.count() > 0:
                await export_btn.click()
                await asyncio.sleep(0.5)
                await screenshot(page, "15_export_clicked")
                log("  Export button clicked")
            else:
                log("  Export button not visible on hover")

        # === STEP 12: Delete session ===
        log("\n[STEP 12] Delete session")
        if len(items) >= 1:
            await items[0].hover()
            await asyncio.sleep(0.5)
            del_btn = page.locator("button[aria-label='Delete session'], button[title='Delete']").first
            if await del_btn.count() > 0:
                await del_btn.click()
                await asyncio.sleep(0.3)
                # Confirm delete if dialog appears
                confirm = page.locator("button:has-text('Confirm'), button:has-text('Delete')").first
                if await confirm.count() > 0:
                    await confirm.click()
                    await asyncio.sleep(0.5)
                await screenshot(page, "16_after_delete")
                log("  Session deleted")
            else:
                log("  Delete button not visible on hover")

        # === STEP 13: Final state ===
        log("\n[STEP 13] Final state check")
        await asyncio.sleep(1)
        await screenshot(page, "17_final_state")
        session_items_final = await page.locator("[data-testid='session-item'], div.group").count()
        log(f"  Final session count: {session_items_final}")

        # === Console errors ===
        log(f"\n[Console Errors] Total: {len(console_errors)}")
        for i, err in enumerate(console_errors[:20]):
            log(f"  {i+1}. {err[:200]}")

        await browser.close()

    # Save results
    results_path = Path(__file__).parent / "e2e_results.txt"
    results_path.write_text("\n".join(results))
    log(f"\nResults saved to: {results_path}")
    log("=== E2E Test Complete ===")
    return results

if __name__ == "__main__":
    asyncio.run(run_e2e())
