#!/usr/bin/env python3
"""
Session 切换 Bug 验证测试
模拟用户切换 session 时 LLM 反馈被清除的场景
"""

import asyncio
import json
from datetime import datetime
from pathlib import Path
from playwright.async_api import Playwright, async_playwright

OUTPUT_DIR = Path("/Users/mac/AI/CScode/dogfood-output")
SCREENSHOT_DIR = OUTPUT_DIR / "session-switch-bug"
SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)

logs = []

def log(msg: str):
    print(msg)
    logs.append(msg)

async def save_screenshot(page, name: str):
    path = SCREENSHOT_DIR / f"{name}.png"
    await page.screenshot(path=str(path))
    log(f"  📸 {name}.png")

async def get_session_buttons(page):
    """手动获取所有会话按钮"""
    buttons = await page.query_selector_all('button')
    session_btns = []
    for btn in buttons:
        text = await btn.inner_text()
        if text == 'New Session':
            session_btns.append(btn)
    return session_btns

async def run_bug_test(playwright: Playwright):
    browser = await playwright.chromium.launch(headless=False, slow_mo=100)
    context = await browser.new_context(viewport={"width": 1440, "height": 900})
    page = await context.new_page()
    
    # 收集所有控制台日志
    all_logs = []
    page.on("console", lambda msg: all_logs.append({
        "type": msg.type,
        "text": msg.text,
        "time": datetime.now().isoformat()
    }))
    
    log("🚀 开始 Session 切换 Bug 验证测试...")
    await page.goto("http://localhost:8000", wait_until="domcontentloaded")
    await page.wait_for_timeout(3000)
    
    # ========== 步骤 1: 创建 Session A ==========
    log("\n=== 步骤 1: 创建 Session A ===")
    new_session_btn = page.locator('button[aria-label="Create new session"]')
    await new_session_btn.click()
    await page.wait_for_timeout(1000)
    
    session_btns = await get_session_buttons(page)
    session_a = session_btns[-1]
    log(f"  Session A 创建成功")
    await save_screenshot(page, "01-create-session-a")
    
    # ========== 步骤 2: 在 Session A 发送消息 ==========
    log("\n=== 步骤 2: 在 Session A 发送消息 ===")
    await session_a.click()
    await page.wait_for_timeout(500)
    
    input_area = page.locator('textarea[placeholder="Ask anything or @mention a file..."]')
    await input_area.fill("What is Python programming language?")
    await input_area.press("Enter")
    log("  消息已发送，等待 LLM 开始响应...")
    await page.wait_for_timeout(2000)
    await save_screenshot(page, "02-session-a-after-send")
    
    # ========== 步骤 3: 创建 Session B ==========
    log("\n=== 步骤 3: 创建 Session B ===")
    await new_session_btn.click()
    await page.wait_for_timeout(1000)
    
    session_btns = await get_session_buttons(page)
    session_b = session_btns[-1]
    log(f"  Session B 创建成功")
    await save_screenshot(page, "03-create-session-b")
    
    # ========== 步骤 4: 在 Session B 发送消息 ==========
    log("\n=== 步骤 4: 在 Session B 发送消息 ===")
    await session_b.click()
    await page.wait_for_timeout(500)
    
    input_area = page.locator('textarea[placeholder="Ask anything or @mention a file..."]')
    await input_area.fill("What is JavaScript?")
    await input_area.press("Enter")
    log("  消息已发送")
    await page.wait_for_timeout(2000)
    await save_screenshot(page, "04-session-b-after-send")
    
    # ========== 步骤 5: 切换回 Session A（关键步骤）==========
    log("\n=== 步骤 5: 切换回 Session A（关键步骤）===")
    log("  此时 Session A 的 LLM 流可能仍在后台运行...")
    
    await session_a.click()
    await page.wait_for_timeout(3000)  # 等待 fetch 完成
    
    log("  已切换回 Session A")
    await save_screenshot(page, "05-back-to-session-a")
    
    # ========== 步骤 6: 等待一段时间，观察消息状态 ==========
    log("\n=== 步骤 6: 等待并观察 Session A 消息状态 ===")
    await page.wait_for_timeout(5000)
    await save_screenshot(page, "06-session-a-wait-5s")
    
    # ========== 步骤 7: 再次切换到 Session B，然后切回 Session A ==========
    log("\n=== 步骤 7: 再次切换 Session B -> Session A ===")
    await session_b.click()
    await page.wait_for_timeout(3000)
    await save_screenshot(page, "07-switch-to-b")
    
    await session_a.click()
    await page.wait_for_timeout(3000)
    await save_screenshot(page, "08-back-to-a-again")
    
    # ========== 分析日志 ==========
    log("\n=== 分析日志 ===")
    
    # 查找 setMessages 调用
    setmsgs_logs = [l for l in all_logs if "setMessages" in l["text"]]
    log(f"  setMessages 调用次数: {len(setmsgs_logs)}")
    for l in setmsgs_logs[:10]:
        log(f"    [{l['type']}] {l['text'][:150]}")
    
    # 查找 appendMessage 调用
    append_logs = [l for l in all_logs if "appendMessage" in l["text"]]
    log(f"  appendMessage 调用次数: {len(append_logs)}")
    for l in append_logs[:10]:
        log(f"    [{l['type']}] {l['text'][:150]}")
    
    # 查找 applyEvent 调用
    apply_logs = [l for l in all_logs if "applyEvent" in l["text"]]
    log(f"  applyEvent 调用次数: {len(apply_logs)}")
    
    # 查找 VERSION CHANGED
    version_logs = [l for l in all_logs if "VERSION CHANGED" in l["text"]]
    log(f"  VERSION CHANGED 次数: {len(version_logs)}")
    for l in version_logs:
        log(f"    [{l['type']}] {l['text']}")
    
    # 查找 fetch failed
    failed_logs = [l for l in all_logs if "fetch failed" in l["text"]]
    log(f"  fetch failed 次数: {len(failed_logs)}")
    for l in failed_logs:
        log(f"    [{l['type']}] {l['text']}")
    
    # 查找 DROPPED
    dropped_logs = [l for l in all_logs if "DROPPED" in l["text"]]
    log(f"  DROPPED 事件次数: {len(dropped_logs)}")
    
    # 查找 stream ended
    stream_logs = [l for l in all_logs if "stream ended" in l["text"].lower()]
    log(f"  stream ended 次数: {len(stream_logs)}")
    for l in stream_logs:
        log(f"    [{l['type']}] {l['text']}")
    
    await browser.close()
    
    return {
        "logs": logs,
        "all_logs": all_logs,
    }

async def main():
    async with async_playwright() as playwright:
        result = await run_bug_test(playwright)
    
    result_path = OUTPUT_DIR / "session-switch-bug-results.json"
    with open(result_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    
    log(f"\n📁 测试结果: {result_path}")

if __name__ == "__main__":
    asyncio.run(main())
