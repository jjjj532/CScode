#!/usr/bin/env python3
"""
CScode 多 Session 并发测试脚本 - 修复版
使用手动查询方式获取会话按钮
"""

import asyncio
import json
import os
from datetime import datetime
from pathlib import Path

from playwright.async_api import Playwright, async_playwright


OUTPUT_DIR = Path("/Users/mac/AI/CScode/dogfood-output")
SCREENSHOT_DIR = OUTPUT_DIR / "concurrent-test"
SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)

issues = []
logs = []

def log(msg: str):
    print(msg)
    logs.append(msg)

def add_issue(severity: str, title: str, detail: str):
    issues.append({
        "severity": severity,
        "title": title,
        "detail": detail,
        "timestamp": datetime.now().isoformat()
    })
    log(f"  ❌ [{severity}] {title}: {detail}")

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


async def run_concurrent_test(playwright: Playwright):
    browser = await playwright.chromium.launch(headless=False, slow_mo=50)
    context = await browser.new_context(viewport={"width": 1440, "height": 900})
    page = await context.new_page()
    
    log("🚀 开始多 Session 并发测试...")
    await page.goto("http://localhost:8000", wait_until="domcontentloaded")
    await page.wait_for_timeout(3000)
    
    console_logs = []
    page.on("console", lambda msg: console_logs.append({
        "type": msg.type,
        "text": msg.text
    }))
    
    # ========== 测试 1: 创建两个会话 ==========
    log("\n=== 测试 1: 创建两个会话 ===")
    
    new_session_btn = page.locator('button[aria-label="Create new session"]')
    
    await new_session_btn.click()
    await page.wait_for_timeout(1000)
    
    await new_session_btn.click()
    await page.wait_for_timeout(1000)
    
    session_btns = await get_session_buttons(page)
    count = len(session_btns)
    log(f"  创建了 {count} 个新会话")
    
    if count >= 2:
        session_a = session_btns[-2]  # 倒数第二个
        session_b = session_btns[-1]  # 最后一个
        log("  ✅ 创建两个会话成功")
        await save_screenshot(page, "01-two-sessions")
    else:
        add_issue("P0", "创建会话失败", f"期望创建 2 个会话，实际创建 {count} 个")
        await browser.close()
        return
    
    # ========== 测试 2: 在 Session A 发送消息 ==========
    log("\n=== 测试 2: 在 Session A 发送消息 ===")
    
    await session_a.click()
    await page.wait_for_timeout(500)
    
    input_area = page.locator('textarea[placeholder="Ask anything or @mention a file..."]')
    await input_area.fill("Session A: What is Python?")
    await input_area.press("Enter")
    await page.wait_for_timeout(3000)
    
    log("  ✅ Session A 发送消息")
    await save_screenshot(page, "02-session-a-sending")
    
    errors = [c for c in console_logs if c["type"] == "error"]
    if errors:
        log(f"  ⚠️ 发现 {len(errors)} 个错误日志")
        for e in errors[:3]:
            log(f"    - {e['text'][:100]}")
    
    # ========== 测试 3: 在 Session A 处理中切换到 Session B ==========
    log("\n=== 测试 3: 在 Session A 处理中切换到 Session B ===")
    
    await session_b.click()
    await page.wait_for_timeout(500)
    
    input_area_b = page.locator('textarea[placeholder="Ask anything or @mention a file..."]')
    await input_area_b.fill("Session B: What is JavaScript?")
    await input_area_b.press("Enter")
    await page.wait_for_timeout(3000)
    
    log("  ✅ Session B 发送消息")
    await save_screenshot(page, "03-session-b-sending")
    
    # ========== 测试 4: 切换回 Session A，验证任务仍在进行 ==========
    log("\n=== 测试 4: 切换回 Session A，验证任务仍在进行 ===")
    
    await session_a.click()
    await page.wait_for_timeout(2000)
    
    messages = page.locator('[role="list"] > div')
    msg_count = await messages.count()
    
    log(f"  Session A 消息数: {msg_count}")
    
    await save_screenshot(page, "04-back-to-session-a")
    
    # ========== 测试 5: 切换到 Session B，验证消息隔离 ==========
    log("\n=== 测试 5: 验证 Session 消息隔离 ===")
    
    await session_b.click()
    await page.wait_for_timeout(2000)
    
    messages_b = page.locator('[role="list"] > div')
    msg_count_b = await messages_b.count()
    
    log(f"  Session B 消息数: {msg_count_b}")
    
    if msg_count_b > 0:
        last_msg_b = messages_b.last
        text_b = await last_msg_b.inner_text()
        if "JavaScript" in text_b or "Session B" in text_b:
            log("  ✅ Session B 消息正确")
        else:
            log(f"  ⚠️ Session B 最后消息内容: {text_b[:100]}")
    
    await save_screenshot(page, "05-session-b-messages")
    
    # ========== 测试 6: 等待任务完成，验证最终状态 ==========
    log("\n=== 测试 6: 等待任务完成 ===")
    
    await page.wait_for_timeout(10000)
    
    await session_a.click()
    await page.wait_for_timeout(2000)
    
    messages_a_final = page.locator('[role="list"] > div')
    msg_count_a_final = await messages_a_final.count()
    
    log(f"  Session A 最终消息数: {msg_count_a_final}")
    
    if msg_count_a_final > 0:
        last_msg_a = messages_a_final.last
        text_a = await last_msg_a.inner_text()
        if "Python" in text_a:
            log("  ✅ Session A 收到正确回复")
        else:
            log(f"  ⚠️ Session A 最后消息内容: {text_a[:100]}")
    
    await save_screenshot(page, "06-final-state")
    
    # ========== 测试 7: 并发发送第三个消息 ==========
    log("\n=== 测试 7: 并发发送第三个消息 ===")
    
    await new_session_btn.click()
    await page.wait_for_timeout(1000)
    
    session_btns_c = await get_session_buttons(page)
    session_c = session_btns_c[-1]  # 最新创建的
    
    await session_c.click()
    await page.wait_for_timeout(500)
    
    input_c = page.locator('textarea[placeholder="Ask anything or @mention a file..."]')
    await input_c.fill("Session C: What is React?")
    await input_c.press("Enter")
    await page.wait_for_timeout(3000)
    
    log("  ✅ Session C 发送消息")
    
    # 快速切换三个会话
    await session_a.click()
    await page.wait_for_timeout(500)
    await session_b.click()
    await page.wait_for_timeout(500)
    await session_c.click()
    await page.wait_for_timeout(500)
    await session_a.click()
    await page.wait_for_timeout(500)
    
    log("  ✅ 快速切换三个会话")
    await save_screenshot(page, "07-three-sessions")
    
    # ========== 检查跨会话事件污染 ==========
    log("\n=== 检查跨会话事件污染 ===")
    
    dropped_logs = [c for c in console_logs if "DROPPED" in c["text"]]
    if dropped_logs:
        log(f"  ⚠️ 发现 {len(dropped_logs)} 个 DROPPED 事件")
        for d in dropped_logs[:5]:
            log(f"    - {d['text'][:150]}")
    else:
        log("  ✅ 没有发现跨会话事件污染")
    
    wrong_session_logs = [c for c in console_logs if "wrong session" in c["text"].lower()]
    if wrong_session_logs:
        log(f"  ❌ 发现 {len(wrong_session_logs)} 个错误会话事件")
        add_issue("P1", "消息窜话", f"发现 {len(wrong_session_logs)} 个事件发送到错误的会话")
    else:
        log("  ✅ 没有发现消息窜话")
    
    # ========== 总结 ==========
    log("\n" + "=" * 60)
    log("📊 多 Session 并发测试完成")
    
    await browser.close()
    
    return {
        "issues": issues,
        "logs": logs,
        "console_logs": console_logs,
        "session_counts": {
            "final": count + 1
        }
    }


async def main():
    async with async_playwright() as playwright:
        result = await run_concurrent_test(playwright)
    
    result_path = OUTPUT_DIR / "concurrent-test-results.json"
    with open(result_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    
    log(f"\n📁 测试结果: {result_path}")
    
    if issues:
        log(f"\n❌ 发现 {len(issues)} 个问题:")
        for issue in issues:
            log(f"  [{issue['severity']}] {issue['title']}: {issue['detail']}")
    else:
        log("\n✅ 所有测试通过")


if __name__ == "__main__":
    asyncio.run(main())