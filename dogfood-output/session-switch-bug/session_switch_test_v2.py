#!/usr/bin/env python3
"""
Session 切换 Bug 专项测试 - 改进版
精确测试流式响应过程中的数据完整性
"""

import asyncio
import json
from datetime import datetime
from pathlib import Path
from playwright.async_api import Page, Playwright, async_playwright


OUTPUT_DIR = Path("/Users/mac/AI/CScode/dogfood-output/session-switch-bug")

test_results = []
console_logs = []

def log(msg: str):
    print(msg)

def record_result(test_name: str, passed: bool, detail: str):
    result = {
        "test_name": test_name,
        "passed": passed,
        "detail": detail,
        "timestamp": datetime.now().isoformat()
    }
    test_results.append(result)
    status = "✅" if passed else "❌"
    log(f"  {status} {test_name}: {detail}")

async def save_screenshot(page: Page, name: str):
    path = str(OUTPUT_DIR / f"{name}.png")
    await page.screenshot(path=path)
    return path

async def get_session_buttons(page: Page):
    buttons = await page.query_selector_all('button')
    session_btns = []
    for btn in buttons:
        text = await btn.inner_text()
        if text == 'New Session':
            session_btns.append(btn)
    return session_btns

async def get_page_text(page: Page):
    """获取页面主要文本内容"""
    content = await page.content()
    return content

async def wait_for_thinking(page: Page, timeout: int = 15000):
    """等待 Thinking 状态出现"""
    try:
        await page.wait_for_selector('[class*="thinking"], [class*="Thinking"]', timeout=timeout)
        return True
    except:
        return False


async def run_test(playwright: Playwright):
    log("🚀 Session 切换 Bug 专项测试 - 改进版")
    
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
    # 步骤 1: 创建 Session A，发送长消息
    # ============================================
    log("\n=== 步骤 1: 创建 Session A ===")
    
    new_session_btn = page.locator('button[aria-label="Create new session"]')
    await new_session_btn.click()
    await page.wait_for_timeout(1000)
    
    session_btns = await get_session_buttons(page)
    session_a = session_btns[-1] if session_btns else None
    
    if not session_a:
        record_result("创建 Session A", False, "无法创建会话")
        await browser.close()
        return
    
    await session_a.click()
    await page.wait_for_timeout(500)
    
    # 发送长消息，确保 LLM 需要较长时间响应
    input_area = page.locator('textarea[placeholder*="Ask anything"]')
    long_message = "Please write a very detailed explanation about Python programming language, including its history, key features, data types, control structures, object-oriented programming, popular libraries like NumPy and Pandas, and real-world applications. Make this answer at least 500 words long."
    await input_area.fill(long_message)
    await input_area.press("Enter")
    
    # 等待 Thinking 状态
    await wait_for_thinking(page, 10000)
    await page.wait_for_timeout(5000)  # 等待部分响应
    
    # 记录切换前页面内容
    content_before = await get_page_text(page)
    python_count_before = content_before.count("Python") + content_before.count("python")
    log(f"  Session A 切换前 'Python' 出现次数: {python_count_before}")
    
    await save_screenshot(page, "01-session-a-thinking")
    
    # ============================================
    # 步骤 2: 创建 Session B，发送消息
    # ============================================
    log("\n=== 步骤 2: 创建 Session B ===")
    
    await new_session_btn.click()
    await page.wait_for_timeout(1000)
    
    session_btns = await get_session_buttons(page)
    session_b = session_btns[-1] if session_btns else None
    
    if session_b:
        await session_b.click()
        await page.wait_for_timeout(500)
        
        input_b = page.locator('textarea[placeholder*="Ask anything"]')
        await input_b.fill("What is JavaScript?")
        await input_b.press("Enter")
        
        await wait_for_thinking(page, 10000)
        await page.wait_for_timeout(3000)
    
    await save_screenshot(page, "02-session-b-thinking")
    
    # ============================================
    # 步骤 3: 切换回 Session A（关键测试）
    # ============================================
    log("\n=== 步骤 3: 切换回 Session A（关键测试）===")
    
    session_btns = await get_session_buttons(page)
    if len(session_btns) >= 2:
        await session_btns[-2].click()  # Session A
        await page.wait_for_timeout(5000)  # 等待 fetch 和渲染
    
    # 记录切换后页面内容
    content_after = await get_page_text(page)
    python_count_after = content_after.count("Python") + content_after.count("python")
    
    log(f"  Session A 切换后 'Python' 出现次数: {python_count_after}")
    
    await save_screenshot(page, "03-back-to-session-a")
    
    # ============================================
    # 验证数据完整性
    # ============================================
    log("\n=== 验证数据完整性 ===")
    
    # 检查 Python 内容是否丢失
    if python_count_after < python_count_before:
        record_result("会话切换数据完整性", False, 
            f"'Python' 出现次数减少: {python_count_before} -> {python_count_after}")
        
        # 详细分析
        log("\n  📊 详细分析:")
        log(f"    切换前 'Python' 出现: {python_count_before} 次")
        log(f"    切换后 'Python' 出现: {python_count_after} 次")
        log(f"    减少: {python_count_before - python_count_after} 次")
        
        # 检查页面是否有 LLM 响应内容
        if "programming language" in content_after:
            log("    ✅ 页面仍包含 Python 介绍内容")
        else:
            log("    ❌ 页面缺少 Python 介绍内容")
            
    else:
        record_result("会话切换数据完整性", True, 
            f"'Python' 出现次数保持: {python_count_after} 次")
    
    # ============================================
    # 等待响应完成
    # ============================================
    log("\n=== 步骤 4: 等待响应完成 ===")
    await page.wait_for_timeout(15000)
    
    content_final = await get_page_text(page)
    python_count_final = content_final.count("Python") + content_final.count("python")
    log(f"  Session A 最终 'Python' 出现次数: {python_count_final}")
    
    await save_screenshot(page, "04-final-state")
    
    # ============================================
    # 分析控制台日志
    # ============================================
    log("\n=== 分析控制台日志 ===")
    
    # 查找 setMessages 调用
    setmsgs_logs = [l for l in console_logs if "setMessages" in l["text"]]
    log(f"  setMessages 调用次数: {len(setmsgs_logs)}")
    for l in setmsgs_logs[:10]:
        log(f"    {l['text'][:200]}")
    
    # 查找错误日志
    error_logs = [l for l in console_logs if l["type"] == "error"]
    log(f"  错误日志次数: {len(error_logs)}")
    for l in error_logs[:5]:
        log(f"    [{l['type']}] {l['text'][:200]}")
    
    # 查找 applyEvent
    apply_logs = [l for l in console_logs if "applyEvent" in l["text"]]
    log(f"  applyEvent 调用次数: {len(apply_logs)}")
    
    # 查找 VERSION CHANGED
    version_logs = [l for l in console_logs if "VERSION CHANGED" in l["text"]]
    log(f"  VERSION CHANGED 次数: {len(version_logs)}")
    
    # 查找 stream
    stream_logs = [l for l in console_logs if "stream" in l["text"].lower()]
    log(f"  stream 相关日志次数: {len(stream_logs)}")
    for l in stream_logs[:5]:
        log(f"    {l['text'][:200]}")
    
    await browser.close()


async def main():
    async with async_playwright() as playwright:
        await run_test(playwright)
    
    # 保存测试结果
    report = {
        "timestamp": datetime.now().isoformat(),
        "test_results": test_results,
        "console_logs": console_logs,
        "summary": {
            "total": len(test_results),
            "passed": sum(1 for t in test_results if t["passed"]),
            "failed": sum(1 for t in test_results if not t["passed"]),
        }
    }
    
    report_path = OUTPUT_DIR / "session-switch-test-results-v2.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    
    log("\n" + "=" * 60)
    log("📊 Session 切换 Bug 测试完成")
    log(f"   测试数: {report['summary']['total']}")
    log(f"   通过: {report['summary']['passed']}")
    log(f"   失败: {report['summary']['failed']}")
    log(f"\n📁 测试报告: {report_path}")
    
    failed_tests = [t for t in test_results if not t["passed"]]
    if failed_tests:
        log("\n❌ 失败的测试:")
        for t in failed_tests:
            log(f"   {t['test_name']}: {t['detail']}")


if __name__ == "__main__":
    asyncio.run(main())