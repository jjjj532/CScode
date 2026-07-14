#!/usr/bin/env python3
"""
Session 切换 Bug 专项测试
验证场景：
1. 创建两个 session，每个都与 LLM 交互
2. 在 LLM 响应过程中切换 session
3. 验证消息是否丢失
4. 记录完整的控制台日志
"""

import asyncio
import json
import re
from datetime import datetime
from pathlib import Path
from playwright.async_api import Page, Playwright, async_playwright


OUTPUT_DIR = Path("/Users/mac/AI/CScode/dogfood-output/session-switch-bug")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

test_results = []
console_logs = []
screenshots = []

def log(msg: str):
    print(msg)

def record_result(test_name: str, passed: bool, detail: str, evidence: dict = None):
    result = {
        "test_name": test_name,
        "passed": passed,
        "detail": detail,
        "evidence": evidence or {},
        "timestamp": datetime.now().isoformat()
    }
    test_results.append(result)
    status = "✅" if passed else "❌"
    log(f"  {status} {test_name}: {detail}")

async def save_screenshot(page: Page, name: str) -> str:
    path = str(OUTPUT_DIR / f"{name}.png")
    await page.screenshot(path=path)
    screenshots.append(name)
    return path

async def get_session_buttons(page: Page):
    buttons = await page.query_selector_all('button')
    session_btns = []
    for btn in buttons:
        text = await btn.inner_text()
        if text == 'New Session':
            session_btns.append(btn)
    return session_btns

async def get_messages(page: Page):
    """获取当前消息列表"""
    try:
        # 获取所有消息元素
        messages = await page.query_selector_all('[role="list"] > div')
        msg_list = []
        for msg in messages:
            text = await msg.inner_text()
            if text.strip():
                msg_list.append(text.strip()[:500])
        return msg_list
    except Exception as e:
        log(f"  ⚠️ 获取消息失败: {e}")
        return []

async def get_message_count(page: Page):
    """获取当前消息数量"""
    try:
        messages = await page.query_selector_all('[role="list"] > div')
        return len(messages)
    except:
        return 0

async def wait_for_thinking(page: Page, timeout: int = 10000):
    """等待 LLM 开始响应（Thinking...状态）"""
    try:
        await page.wait_for_selector('.thinking, [class*="thinking"], [class*="Thinking"]', timeout=timeout)
        return True
    except:
        return False

async def wait_for_response(page: Page, timeout: int = 15000):
    """等待 LLM 响应完成"""
    start = datetime.now()
    while (datetime.now() - start).total_seconds() < timeout / 1000:
        try:
            thinking = await page.query_selector('.thinking, [class*="thinking"], [class*="Thinking"]')
            if not thinking:
                return True
        except:
            pass
        await page.wait_for_timeout(500)
    return False


async def run_session_switch_test(playwright: Playwright):
    log("🚀 Session 切换 Bug 专项测试")
    
    browser = await playwright.chromium.launch(headless=False, slow_mo=50)
    context = await browser.new_context(viewport={"width": 1440, "height": 900})
    page = await context.new_page()
    
    # 收集控制台日志
    page.on("console", lambda msg: console_logs.append({
        "type": msg.type,
        "text": msg.text,
        "time": datetime.now().isoformat()
    }))
    
    # 打开应用
    await page.goto("http://localhost:8000", wait_until="domcontentloaded")
    await page.wait_for_timeout(3000)
    
    # ============================================
    # 测试 1: 创建 Session A
    # ============================================
    log("\n=== 测试 1: 创建 Session A ===")
    
    new_session_btn = page.locator('button[aria-label="Create new session"]')
    await new_session_btn.click()
    await page.wait_for_timeout(1000)
    
    session_btns = await get_session_buttons(page)
    if session_btns:
        session_a = session_btns[-1]
        record_result("创建 Session A", True, f"会话数: {len(session_btns)}")
    else:
        record_result("创建 Session A", False, "无法创建会话")
        await browser.close()
        return
    
    await save_screenshot(page, "01-create-session-a")
    
    # ============================================
    # 测试 2: 在 Session A 发送消息，等待 LLM 响应
    # ============================================
    log("\n=== 测试 2: 在 Session A 发送消息 ===")
    
    await session_a.click()
    await page.wait_for_timeout(500)
    
    input_area = page.locator('textarea[placeholder*="Ask anything"]')
    msg_a = "Session A: What is Python programming language? Please give a detailed answer about its features and applications."
    await input_area.fill(msg_a)
    await input_area.press("Enter")
    
    log("  等待 LLM 开始响应...")
    await wait_for_thinking(page, 10000)
    await page.wait_for_timeout(3000)  # 等待部分响应
    
    # 记录切换前的消息状态
    msg_count_before = await get_message_count(page)
    messages_before = await get_messages(page)
    
    log(f"  Session A 切换前消息数: {msg_count_before}")
    for i, m in enumerate(messages_before):
        log(f"    消息{i+1}: {m[:100]}")
    
    record_result("Session A 发送消息", True, f"消息数: {msg_count_before}")
    await save_screenshot(page, "02-session-a-thinking")
    
    # ============================================
    # 测试 3: 创建 Session B，发送消息
    # ============================================
    log("\n=== 测试 3: 创建 Session B ===")
    
    await new_session_btn.click()
    await page.wait_for_timeout(1000)
    
    session_btns = await get_session_buttons(page)
    if session_btns:
        session_b = session_btns[-1]
        record_result("创建 Session B", True, f"会话数: {len(session_btns)}")
    else:
        record_result("创建 Session B", False, "无法创建会话")
        await browser.close()
        return
    
    await session_b.click()
    await page.wait_for_timeout(500)
    
    input_b = page.locator('textarea[placeholder*="Ask anything"]')
    msg_b = "Session B: What is JavaScript? Please explain its history and uses."
    await input_b.fill(msg_b)
    await input_b.press("Enter")
    
    await wait_for_thinking(page, 10000)
    await page.wait_for_timeout(2000)
    
    record_result("Session B 发送消息", True, "")
    await save_screenshot(page, "03-session-b-thinking")
    
    # ============================================
    # 测试 4: 切换回 Session A（关键测试点）
    # ============================================
    log("\n=== 测试 4: 切换回 Session A（关键测试点）===")
    log("  ⚠️ 此时 Session A 的 LLM 流可能仍在后台运行")
    
    session_btns = await get_session_buttons(page)
    if len(session_btns) >= 2:
        await session_btns[-2].click()  # Session A
        await page.wait_for_timeout(3000)  # 等待 fetch 完成
    
    # 记录切换后的消息状态
    msg_count_after = await get_message_count(page)
    messages_after = await get_messages(page)
    
    log(f"  Session A 切换后消息数: {msg_count_after}")
    for i, m in enumerate(messages_after):
        log(f"    消息{i+1}: {m[:100]}")
    
    await save_screenshot(page, "04-back-to-session-a")
    
    # 关键验证：消息是否丢失
    if msg_count_after < msg_count_before:
        record_result("会话切换数据完整性", False, 
            f"消息丢失: 切换前 {msg_count_before} 条 -> 切换后 {msg_count_after} 条")
        
        # 详细分析
        log("\n  📊 消息对比分析:")
        log(f"    切换前消息数: {msg_count_before}")
        log(f"    切换后消息数: {msg_count_after}")
        log(f"    丢失消息数: {msg_count_before - msg_count_after}")
        
        if messages_before:
            log("    切换前消息:")
            for i, m in enumerate(messages_before):
                log(f"      [{i+1}] {m[:150]}")
        
        if messages_after:
            log("    切换后消息:")
            for i, m in enumerate(messages_after):
                log(f"      [{i+1}] {m[:150]}")
    else:
        record_result("会话切换数据完整性", True, 
            f"消息保持: {msg_count_after} 条")
    
    # ============================================
    # 测试 5: 等待响应完成后再次检查
    # ============================================
    log("\n=== 测试 5: 等待响应完成 ===")
    
    await page.wait_for_timeout(10000)
    
    msg_count_final = await get_message_count(page)
    messages_final = await get_messages(page)
    
    log(f"  Session A 最终消息数: {msg_count_final}")
    for i, m in enumerate(messages_final):
        log(f"    消息{i+1}: {m[:100]}")
    
    await save_screenshot(page, "05-final-state")
    
    # ============================================
    # 测试 6: 多次切换验证
    # ============================================
    log("\n=== 测试 6: 多次快速切换 ===")
    
    session_btns = await get_session_buttons(page)
    if len(session_btns) >= 2:
        for i in range(3):
            await session_btns[-2].click()  # Session A
            await page.wait_for_timeout(500)
            await session_btns[-1].click()  # Session B
            await page.wait_for_timeout(500)
        
        # 最后切换回 Session A
        await session_btns[-2].click()
        await page.wait_for_timeout(2000)
        
        msg_count_after_switch = await get_message_count(page)
        
        if msg_count_after_switch > 0:
            record_result("多次切换后消息存在", True, f"消息数: {msg_count_after_switch}")
        else:
            record_result("多次切换后消息存在", False, "消息数为 0")
        
        await save_screenshot(page, "06-after-multiple-switches")
    
    # ============================================
    # 分析控制台日志
    # ============================================
    log("\n=== 分析控制台日志 ===")
    
    # 1. 查找 setMessages 调用
    setmsgs_logs = [l for l in console_logs if "setMessages" in l["text"]]
    log(f"  setMessages 调用次数: {len(setmsgs_logs)}")
    for l in setmsgs_logs[:15]:
        log(f"    [{l['type']}] {l['text'][:200]}")
    
    # 2. 查找 applyEvent 调用
    apply_logs = [l for l in console_logs if "applyEvent" in l["text"]]
    log(f"  applyEvent 调用次数: {len(apply_logs)}")
    
    # 3. 查找 VERSION CHANGED
    version_logs = [l for l in console_logs if "VERSION CHANGED" in l["text"]]
    log(f"  VERSION CHANGED 次数: {len(version_logs)}")
    for l in version_logs[:5]:
        log(f"    {l['text']}")
    
    # 4. 查找错误日志
    error_logs = [l for l in console_logs if l["type"] == "error"]
    log(f"  错误日志次数: {len(error_logs)}")
    for l in error_logs[:5]:
        log(f"    [{l['type']}] {l['text'][:200]}")
    
    # 5. 查找 DROPPED
    dropped_logs = [l for l in console_logs if "DROPPED" in l["text"]]
    log(f"  DROPPED 事件次数: {len(dropped_logs)}")
    
    # 6. 查找 stream 相关
    stream_logs = [l for l in console_logs if "stream" in l["text"].lower()]
    log(f"  stream 相关日志次数: {len(stream_logs)}")
    for l in stream_logs[:5]:
        log(f"    [{l['type']}] {l['text'][:200]}")
    
    # 7. 查找 fetch 相关
    fetch_logs = [l for l in console_logs if "fetch" in l["text"].lower()]
    log(f"  fetch 相关日志次数: {len(fetch_logs)}")
    for l in fetch_logs[:5]:
        log(f"    [{l['type']}] {l['text'][:200]}")
    
    # ============================================
    # 关闭浏览器
    # ============================================
    await browser.close()


async def main():
    async with async_playwright() as playwright:
        await run_session_switch_test(playwright)
    
    # 保存测试结果
    report = {
        "timestamp": datetime.now().isoformat(),
        "test_results": test_results,
        "console_logs": console_logs,
        "screenshots": screenshots,
        "summary": {
            "total": len(test_results),
            "passed": sum(1 for t in test_results if t["passed"]),
            "failed": sum(1 for t in test_results if not t["passed"]),
        }
    }
    
    report_path = OUTPUT_DIR / "session-switch-test-results.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    
    # 打印总结
    log("\n" + "=" * 60)
    log("📊 Session 切换 Bug 测试完成")
    log(f"   测试数: {report['summary']['total']}")
    log(f"   通过: {report['summary']['passed']}")
    log(f"   失败: {report['summary']['failed']}")
    log(f"\n📁 测试报告: {report_path}")
    
    # 打印失败的测试
    failed_tests = [t for t in test_results if not t["passed"]]
    if failed_tests:
        log("\n❌ 失败的测试:")
        for t in failed_tests:
            log(f"   {t['test_name']}: {t['detail']}")


if __name__ == "__main__":
    asyncio.run(main())