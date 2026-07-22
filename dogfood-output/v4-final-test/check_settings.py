#!/usr/bin/env python3
import asyncio
from pathlib import Path
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1440, "height": 900})
        await page.goto("http://127.0.0.1:8080", wait_until="domcontentloaded")
        await page.wait_for_timeout(2000)
        
        await page.locator('button[aria-label="Settings"]').click()
        await page.wait_for_timeout(1000)
        
        inputs = await page.evaluate("""() => {
            return Array.from(document.querySelectorAll('input, select, textarea')).map(i => ({
                tag: i.tagName,
                type: i.type || '',
                name: i.name || '',
                id: i.id || '',
                ariaLabel: i.getAttribute('aria-label') || '',
                placeholder: i.placeholder || '',
                value: i.value || ''
            }));
        }""")
        
        for i, inp in enumerate(inputs):
            print(f"[{i}] {inp['tag']} type={inp['type']} name={inp['name']} id={inp['id']} aria-label={inp['ariaLabel']} value={inp['value'][:30] if inp['value'] else ''}")
        
        await browser.close()

asyncio.run(main())
