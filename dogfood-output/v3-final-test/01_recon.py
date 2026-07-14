#!/usr/bin/env python3
"""
Phase 1: DOM Reconnaissance
Extract all real DOM selectors, button labels, and UI structure
"""
import asyncio
import json
from pathlib import Path
from playwright.async_api import async_playwright

OUTPUT_DIR = Path("/Users/mac/AI/CScode/dogfood-output/v3-final-test")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1440, "height": 900})

        await page.goto("http://localhost:8000", wait_until="domcontentloaded")
        await page.wait_for_timeout(3000)

        # 1. Get all buttons
        buttons = await page.evaluate("""() => {
            const btns = Array.from(document.querySelectorAll('button'));
            return btns.map(b => ({
                tag: b.tagName,
                text: b.innerText.trim(),
                ariaLabel: b.getAttribute('aria-label') || '',
                className: b.className || '',
                title: b.getAttribute('title') || '',
                visible: b.offsetParent !== null
            })).filter(b => b.visible);
        }""")

        print("=== ALL VISIBLE BUTTONS ===")
        for i, b in enumerate(buttons):
            print(f"  [{i}] text='{b['text']}' aria-label='{b['ariaLabel']}' class='{b['className'][:80]}'")

        # 2. Get sidebar structure
        sidebar = await page.evaluate("""() => {
            const aside = document.querySelector('aside, [role="navigation"]');
            if (!aside) return null;
            const items = Array.from(aside.querySelectorAll('li, [role="listitem"], .session-item, .project-item'));
            return {
                tag: aside.tagName,
                className: aside.className,
                itemCount: items.length,
                items: items.slice(0, 10).map(i => ({
                    tag: i.tagName,
                    text: i.innerText.trim().slice(0, 50),
                    className: i.className.slice(0, 60),
                    role: i.getAttribute('role') || ''
                }))
            };
        }""")

        print("\n=== SIDEBAR STRUCTURE ===")
        if sidebar:
            print(f"  Tag: {sidebar['tag']}")
            print(f"  Class: {sidebar['className'][:100]}")
            print(f"  Item count: {sidebar['itemCount']}")
            for i, item in enumerate(sidebar['items']):
                print(f"    [{i}] {item['tag']} text='{item['text']}' class='{item['className'][:60]}'")

        # 3. Get main content structure
        main_content = await page.evaluate("""() => {
            const main = document.querySelector('main, .main-content, [role="main"]');
            if (!main) return null;
            return {
                tag: main.tagName,
                className: main.className,
                hasTextarea: !!main.querySelector('textarea'),
                textareaCount: main.querySelectorAll('textarea').length,
                messageCount: main.querySelectorAll('[role="list"] > div, .message, [class*="Message"]').length
            };
        }""")

        print("\n=== MAIN CONTENT STRUCTURE ===")
        if main_content:
            print(f"  Tag: {main_content['tag']}")
            print(f"  Class: {main_content['className'][:100]}")
            print(f"  Textarea count: {main_content['textareaCount']}")
            print(f"  Message count: {main_content['messageCount']}")

        # 4. Check window.__STORE_STATE__
        store_state = await page.evaluate("""() => {
            return {
                hasStore: typeof window.__STORE_STATE__ !== 'undefined',
                hasSessionStore: typeof window.useSessionStore !== 'undefined',
                hasConfigStore: typeof window.useConfigStore !== 'undefined',
                keys: Object.keys(window).filter(k => k.toLowerCase().includes('store'))
            };
        }""")

        print("\n=== WINDOW STORE STATE ===")
        print(f"  __STORE_STATE__: {store_state['hasStore']}")
        print(f"  useSessionStore: {store_state['hasSessionStore']}")
        print(f"  useConfigStore: {store_state['hasConfigStore']}")
        print(f"  Store-related keys: {store_state['keys']}")

        # 5. Get all console logs
        console_logs = []
        page.on("console", lambda msg: console_logs.append({"type": msg.type, "text": msg.text}))

        # 6. Click settings to check settings panel
        print("\n=== SETTINGS PANEL ===")
        try:
            settings_btn = page.locator('button[aria-label="Settings"]')
            if await settings_btn.count() > 0:
                await settings_btn.click()
                await page.wait_for_timeout(1000)

                settings_info = await page.evaluate("""() => {
                    const dialog = document.querySelector('[role="dialog"], .modal, [class*="Settings"]');
                    if (!dialog) return null;
                    const inputs = Array.from(dialog.querySelectorAll('input, select, textarea'));
                    return {
                        tag: dialog.tagName,
                        className: dialog.className.slice(0, 80),
                        inputCount: inputs.length,
                        inputs: inputs.slice(0, 10).map(i => ({
                            type: i.type || i.tagName,
                            name: i.name || '',
                            placeholder: i.placeholder || '',
                            id: i.id || ''
                        }))
                    };
                }""")

                if settings_info:
                    print(f"  Tag: {settings_info['tag']}")
                    print(f"  Class: {settings_info['className']}")
                    print(f"  Input count: {settings_info['inputCount']}")
                    for i, inp in enumerate(settings_info['inputs']):
                        print(f"    [{i}] {inp['type']} name='{inp['name']}' placeholder='{inp['placeholder']}'")
        except Exception as e:
            print(f"  Error: {e}")

        # Save screenshot
        await page.screenshot(path=str(OUTPUT_DIR / "00_recon.png"), full_page=True)

        await browser.close()

        # Save recon data
        recon_data = {
            "buttons": buttons,
            "sidebar": sidebar,
            "main_content": main_content,
            "store_state": store_state,
        }
        with open(OUTPUT_DIR / "recon_data.json", "w") as f:
            json.dump(recon_data, f, indent=2)

        print(f"\n✅ Recon data saved to {OUTPUT_DIR / 'recon_data.json'}")


if __name__ == "__main__":
    asyncio.run(main())