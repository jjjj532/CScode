#!/usr/bin/env python3
"""
Phase 1: DOM Reconnaissance for packaged CScode desktop app
Target: http://127.0.0.1:8080 (Tauri app backend serving web-dist)
"""
import asyncio
import json
from pathlib import Path
from playwright.async_api import async_playwright

OUTPUT_DIR = Path("/Users/mac/AI/CScode/dogfood-output/v4-final-test")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1440, "height": 900})

        console_logs = []
        page.on("console", lambda msg: console_logs.append({"type": msg.type, "text": msg.text}))

        await page.goto("http://127.0.0.1:8080", wait_until="domcontentloaded")
        await page.wait_for_timeout(3000)

        # 1. Get all visible buttons
        buttons = await page.evaluate("""() => {
            const btns = Array.from(document.querySelectorAll('button'));
            return btns.filter(b => b.offsetParent !== null).map(b => ({
                text: b.innerText.trim(),
                ariaLabel: b.getAttribute('aria-label') || '',
                title: b.getAttribute('title') || '',
                className: b.className || '',
                disabled: b.disabled
            }));
        }""")

        print("=== ALL VISIBLE BUTTONS ===")
        for i, b in enumerate(buttons):
            print(f"  [{i}] text='{b['text']}' aria-label='{b['ariaLabel']}' title='{b['title']}'")

        # 2. Sidebar structure
        sidebar = await page.evaluate("""() => {
            const aside = document.querySelector('aside');
            if (!aside) return null;
            const items = Array.from(aside.querySelectorAll('div, li')).filter(el => {
                const text = el.innerText.trim();
                return text.length > 0 && text.length < 100;
            });
            return {
                className: aside.className,
                itemCount: items.length,
                items: items.slice(0, 15).map(i => ({
                    tag: i.tagName,
                    text: i.innerText.trim().slice(0, 40),
                    className: i.className.slice(0, 60)
                }))
            };
        }""")

        print("\n=== SIDEBAR STRUCTURE ===")
        if sidebar:
            print(f"  Class: {sidebar['className'][:100]}")
            print(f"  Item count: {sidebar['itemCount']}")
            for i, item in enumerate(sidebar['items']):
                print(f"    [{i}] {item['tag']} text='{item['text']}' class='{item['className'][:60]}'")
        else:
            print("  No aside found")

        # 3. Main content / composer
        main = await page.evaluate("""() => {
            const main = document.querySelector('main') || document.querySelector('[role="main"]');
            if (!main) return null;
            return {
                className: main.className,
                textareaCount: main.querySelectorAll('textarea').length,
                textareas: Array.from(main.querySelectorAll('textarea')).map(t => ({
                    placeholder: t.placeholder,
                    className: t.className.slice(0, 60)
                })),
                messageCount: main.querySelectorAll('.message, [class*="Message"]').length
            };
        }""")

        print("\n=== MAIN CONTENT ===")
        if main:
            print(f"  Class: {main['className'][:100]}")
            print(f"  Textarea count: {main['textareaCount']}")
            for i, t in enumerate(main['textareas']):
                print(f"    [{i}] placeholder='{t['placeholder']}'")
            print(f"  Message count: {main['messageCount']}")

        # 4. Window store state
        store_state = await page.evaluate("""() => {
            return {
                hasStore: typeof window.__STORE_STATE__ !== 'undefined',
                storeType: typeof window.__STORE_STATE__,
                keys: Object.keys(window).filter(k => k.toLowerCase().includes('store'))
            };
        }""")

        print("\n=== WINDOW STORE STATE ===")
        print(f"  __STORE_STATE__: {store_state['hasStore']} ({store_state['storeType']})")
        print(f"  Store-related keys: {store_state['keys']}")

        # 5. Open settings to inspect
        print("\n=== SETTINGS PANEL ===")
        try:
            settings_btn = page.locator('button[aria-label="Settings"]')
            if await settings_btn.count() > 0:
                await settings_btn.click()
                await page.wait_for_timeout(1500)

                settings = await page.evaluate("""() => {
                    const panel = document.querySelector('[class*="Settings"], [class*="settings"], aside + div, .fixed.inset-0');
                    if (!panel) return null;
                    const inputs = Array.from(panel.querySelectorAll('input, select, textarea'));
                    return {
                        tag: panel.tagName,
                        className: panel.className.slice(0, 100),
                        inputCount: inputs.length,
                        inputs: inputs.slice(0, 10).map(i => ({
                            type: i.type || i.tagName,
                            name: i.name || '',
                            placeholder: i.placeholder || '',
                            id: i.id || ''
                        }))
                    };
                }""")

                if settings:
                    print(f"  Tag: {settings['tag']}")
                    print(f"  Class: {settings['className']}")
                    print(f"  Input count: {settings['inputCount']}")
                    for i, inp in enumerate(settings['inputs']):
                        print(f"    [{i}] {inp['type']} name='{inp['name']}' placeholder='{inp['placeholder']}'")

                await page.screenshot(path=str(OUTPUT_DIR / "00_recon_settings.png"))
        except Exception as e:
            print(f"  Error: {e}")

        await page.screenshot(path=str(OUTPUT_DIR / "00_recon_main.png"), full_page=True)

        # 6. Console errors
        errors = [l for l in console_logs if l['type'] == 'error']
        print("\n=== CONSOLE ERRORS ===")
        print(f"  Count: {len(errors)}")
        for e in errors[:10]:
            print(f"    {e['text'][:150]}")

        recon_data = {
            "buttons": buttons,
            "sidebar": sidebar,
            "main": main,
            "store_state": store_state,
            "console_errors": errors
        }
        with open(OUTPUT_DIR / "recon_data.json", "w") as f:
            json.dump(recon_data, f, indent=2)

        print(f"\n✅ Recon saved to {OUTPUT_DIR}")

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())