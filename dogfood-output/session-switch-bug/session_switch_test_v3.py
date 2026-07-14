#!/usr/bin/env python3
"""
Session 切换 Bug 专项测试 - 修复版
精确测试流式响应过程中的数据完整性
修复session选择逻辑，确保正确切换
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

async def get_session_items(page: Page):
    items = await page.query_selector_all('[data-testid*="session"], [role="listitem"], .session-item, .project-item')
    return items

async def get_page_text(page: Page):
    content = await page.content()
    return content

async def wait_for_thinking(page: Page, timeout: int = 15000):
    try:
        await page.wait_for_selector('[class*="thinking"], [class*="Thinking"]', timeout=timeout)
        return True
    except:
        return False


async def run_test(playwright: Playwright):
    log("🚀 Session 切换 Bug 专项测试 - 修复版")
    
    browser = await playwright.chromium.launch(headless=False, slow_mo=50)
    context = await browser.new_context(viewport={"width": 1440, "height": 900})
    page = await context.new_page()
    
    page.on("console", lambda msg: console_logs.append({
        "type": msg.type,
        "text": msg.text,
        "time": datetime.now().isoformat()
    }))
    
    await page.goto("http://localhost:8000", wait_until="domcontentloaded")
    await page.wait_for_timeout(3000)
    
    log("\n=== 步骤 1: 创建 Session A，发送长消息 ===")
    
    new_session_btn = page.locator('button[aria-label="Create new session"]')
    await new_session_btn.click()
    await page.wait_for_timeout(1500)
    
    session_a_id = None
    
    try:
        current_state = await page.evaluate("""() => {
            return window.__STORE_STATE__ ? window.__STORE_STATE__.activeSessionId : null;
        }""")
        if current_state:
            session_a_id = current_state
            log(f"  Session A ID: {session_a_id}")
    except:
        pass
    
    input_area = page.locator('textarea[placeholder*="Ask anything"]')
    long_message = "Please write a very detailed explanation about Python programming language, including its history, key features, data types, control structures, object-oriented programming, popular libraries like NumPy and Pandas, and real-world applications. Make this answer at least 500 words long."
    await input_area.fill(long_message)
    await input_area.press("Enter")
    
    await wait_for_thinking(page, 10000)
    await page.wait_for_timeout(8000)
    
    content_before = await get_page_text(page)
    python_count_before = content_before.count("Python") + content_before.count("python")
    log(f"  Session A 切换前 'Python' 出现次数: {python_count_before}")
    
    await save_screenshot(page, "v3-01-session-a-thinking")
    
    log("\n=== 步骤 2: 创建 Session B，发送消息 ===")
    
    await new_session_btn.click()
    await page.wait_for_timeout(1500)
    
    session_b_id = None
    try:
        current_state = await page.evaluate("""() => {
            return window.__STORE_STATE__ ? window.__STORE_STATE__.activeSessionId : null;
        }""")
        if current_state:
            session_b_id = current_state
            log(f"  Session B ID: {session_b_id}")
    except:
        pass
    
    input_b = page.locator('textarea[placeholder*="Ask anything"]')
    await input_b.fill("What is JavaScript?")
    await input_b.press("Enter")
    
    await wait_for_thinking(page, 10000)
    await page.wait_for_timeout(3000)
    
    await save_screenshot(page, "v3-02-session-b-thinking")
    
    log("\n=== 步骤 3: 切换回 Session A（关键测试）===")
    
    if session_a_id:
        log(f"  尝试切换回 Session A: {session_a_id}")
        try:
            await page.evaluate(f"""() => {{
                const items = document.querySelectorAll('[data-testid*="session"], [role="listitem"], .session-item, .project-item');
                for (let item of items) {{
                    if (item.textContent && item.textContent.includes('Python')) {{
                        item.click();
                        return true;
                    }}
                }}
                return false;
            }}""")
        except:
            pass
        
        try:
            session_items = await get_session_items(page)
            if len(session_items) >= 2:
                await session_items[-2].click()
                log(f"  通过列表点击切换到第 {len(session_items)-1} 个session")
        except:
            pass
        
        await page.wait_for_timeout(5000)
    
    content_after = await get_page_text(page)
    python_count_after = content_after.count("Python") + content_after.count("python")
    
    log(f"  Session A 切换后 'Python' 出现次数: {python_count_after}")
    
    await save_screenshot(page, "v3-03-back-to-session-a")
    
    log("\n=== 验证数据完整性 ===")
    
    if python_count_after < python_count_before:
        record_result("会话切换数据完整性", False, 
            f"'Python' 出现次数减少: {python_count_before} -> {python_count_after}")
        
        log("\n  📊 详细分析:")
        log(f"    切换前 'Python' 出现: {python_count_before} 次")
        log(f"    切换后 'Python' 出现: {python_count_after} 次")
        log(f"    减少: {python_count_before - python_count_after} 次")
        
        if "programming language" in content_after:
            log("    ✅ 页面仍包含 Python 介绍内容")
        else:
            log("    ❌ 页面缺少 Python 介绍内容")
            
    else:
        record_result("会话切换数据完整性", True, 
            f"'Python' 出现次数保持: {python_count_after} 次")
    
    log("\n=== 步骤 4: 等待响应完成 ===")
    await page.wait_for_timeout(15000)
    
    content_final = await get_page_text(page)
    python_count_final = content_final.count("Python") + content_final.count("python")
    log(f"  Session A 最终 'Python' 出现次数: {python_count_final}")
    
    await save_screenshot(page, "v3-04-final-state")
    
    log("\n=== 分析控制台日志 ===")
    
    setmsgs_logs = [l for l in console_logs if "setMessages" in l["text"]]
    log(f"  setMessages 调用次数: {len(setmsgs_logs)}")
    for l in setmsgs_logs[:10]:
        log(f"    {l['text'][:200]}")
    
    error_logs = [l for l in console_logs if l["type"] == "error"]
    log(f"  错误日志次数: {len(error_logs)}")
    for l in error_logs[:5]:
        log(f"    [{l['type']}] {l['text'][:200]}")
    
    apply_logs = [l for l in console_logs if "applyEvent" in l["text"]]
    log(f"  applyEvent 调用次数: {len(apply_logs)}")
    
    version_logs = [l for l in console_logs if "VERSION CHANGED" in l["text"]]
    log(f"  VERSION CHANGED 次数: {len(version_logs)}")
    
    stream_logs = [l for l in console_logs if "stream" in l["text"].lower()]
    log(f"  stream 相关日志次数: {len(stream_logs)}")
    for l in stream_logs[:5]:
        log(f"    {l['text'][:200]}")
    
    await browser.close()


async def main():
    async with async_playwright() as playwright:
        await run_test(playwright)
    
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
    
    report_path = OUTPUT_DIR / "session-switch-test-results-v3.json"
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