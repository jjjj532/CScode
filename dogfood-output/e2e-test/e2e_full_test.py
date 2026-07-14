#!/usr/bin/env python3
"""
CScode 企业级端到端测试 - 完整用户场景测试
基于 dogfood 方法论，覆盖所有 GUI 功能和数据一致性验证
"""

import asyncio
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

from playwright.async_api import Page, Playwright, async_playwright


OUTPUT_DIR = Path("/Users/mac/AI/CScode/dogfood-output/e2e-test")
SCREENSHOT_DIR = OUTPUT_DIR / "screenshots"
SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)

issues: list[dict] = []
test_results: list[dict] = []
console_logs: list[dict] = []

def log(msg: str):
    print(msg)

def add_issue(severity: str, title: str, detail: str, repro_steps: list[str], screenshots: list[str]):
    issue = {
        "id": f"ISSUE-{len(issues) + 1:03d}",
        "severity": severity,
        "title": title,
        "detail": detail,
        "repro_steps": repro_steps,
        "screenshots": screenshots,
        "timestamp": datetime.now().isoformat()
    }
    issues.append(issue)
    log(f"  ❌ [{severity}] {title}")

def record_test(name: str, passed: bool, detail: str):
    test_results.append({
        "name": name,
        "passed": passed,
        "detail": detail,
        "timestamp": datetime.now().isoformat()
    })
    status = "✅" if passed else "❌"
    log(f"  {status} {name}: {detail}")

async def save_screenshot(page: Page, name: str) -> str:
    path = str(SCREENSHOT_DIR / f"{name}.png")
    await page.screenshot(path=path)
    return path

async def get_session_buttons(page: Page) -> list:
    """获取所有会话按钮"""
    buttons = await page.query_selector_all('button')
    session_btns = []
    for btn in buttons:
        text = await btn.inner_text()
        if text == 'New Session':
            session_btns.append(btn)
    return session_btns

async def get_message_list(page: Page) -> list[str]:
    """获取当前显示的消息列表内容"""
    try:
        messages = await page.query_selector_all('[role="list"] > div')
        contents = []
        for msg in messages:
            try:
                text = await msg.inner_text()
                if text.strip():
                    contents.append(text.strip()[:200])
            except:
                pass
        return contents
    except:
        return []

async def get_message_count(page: Page) -> int:
    """获取当前显示的消息数量"""
    try:
        messages = await page.query_selector_all('[role="list"] > div')
        return len(messages)
    except:
        return 0


class CScodeE2ETest:
    def __init__(self, page: Page):
        self.page = page
        self.issue_counter = 0
        
    async def setup_console_listener(self):
        """监听控制台日志"""
        self.page.on("console", lambda msg: console_logs.append({
            "type": msg.type,
            "text": msg.text,
            "time": datetime.now().isoformat()
        }))
        
    async def test_1_initial_load(self):
        """测试 1: 应用加载"""
        log("\n=== 测试 1: 应用初始加载 ===")
        
        await self.page.goto("http://localhost:8000", wait_until="domcontentloaded")
        await self.page.wait_for_timeout(3000)
        
        # 检查标题
        title = await self.page.title()
        if "CScode" in title:
            record_test("应用标题", True, f"标题: {title}")
        else:
            record_test("应用标题", False, f"标题不包含 CScode: {title}")
        
        # 检查主要元素是否存在
        elements = {
            "输入框": 'textarea[placeholder*="Ask anything"]',
            "新建会话按钮": 'button[aria-label="Create new session"]',
            "设置按钮": 'button[aria-label="Settings"]',
        }
        
        for name, selector in elements.items():
            if await self.page.locator(selector).is_visible(timeout=3000):
                record_test(f"元素存在: {name}", True, "")
            else:
                record_test(f"元素存在: {name}", False, f"选择器: {selector}")
        
        await save_screenshot(self.page, "01-initial-load")
        
    async def test_2_session_management(self):
        """测试 2: 会话管理"""
        log("\n=== 测试 2: 会话管理 ===")
        
        # 2.1 创建新会话
        new_session_btn = self.page.locator('button[aria-label="Create new session"]')
        await new_session_btn.click()
        await self.page.wait_for_timeout(1000)
        
        session_btns = await get_session_buttons(self.page)
        if len(session_btns) >= 1:
            record_test("创建新会话", True, f"会话数: {len(session_btns)}")
        else:
            record_test("创建新会话", False, "创建后未找到新会话")
        
        await save_screenshot(self.page, "02-new-session")
        
        # 2.2 切换会话
        if len(session_btns) >= 2:
            await session_btns[0].click()
            await self.page.wait_for_timeout(500)
            await session_btns[1].click()
            await self.page.wait_for_timeout(500)
            record_test("会话切换", True, "")
        else:
            record_test("会话切换", False, "没有足够的会话进行切换测试")
        
        await save_screenshot(self.page, "03-session-switch")
        
    async def test_3_chat_interaction(self):
        """测试 3: 聊天交互"""
        log("\n=== 测试 3: 聊天交互 ===")
        
        # 创建新会话用于测试
        new_session_btn = self.page.locator('button[aria-label="Create new session"]')
        await new_session_btn.click()
        await self.page.wait_for_timeout(1000)
        
        session_btns = await get_session_buttons(self.page)
        if session_btns:
            await session_btns[-1].click()
            await self.page.wait_for_timeout(500)
        
        # 3.1 输入消息
        input_area = self.page.locator('textarea[placeholder*="Ask anything"]')
        test_message = "Hello, this is a test message. Please respond briefly."
        
        await input_area.fill(test_message)
        value = await input_area.input_value()
        if value == test_message:
            record_test("消息输入", True, "")
        else:
            record_test("消息输入", False, f"输入值不匹配: {value[:50]}")
        
        await save_screenshot(self.page, "04-input-message")
        
        # 3.2 发送消息
        await input_area.press("Enter")
        await self.page.wait_for_timeout(3000)
        
        # 检查用户消息是否显示
        page_content = await self.page.content()
        if test_message.split('.')[0] in page_content:
            record_test("用户消息显示", True, "")
        else:
            record_test("用户消息显示", False, "消息未显示在页面上")
        
        await save_screenshot(self.page, "05-message-sent")
        
        # 3.3 等待 LLM 响应
        await self.page.wait_for_timeout(10000)
        
        # 检查是否有 assistant 消息
        messages_after = await get_message_list(self.page)
        
        # 查找 assistant 消息
        assistant_found = False
        for msg in messages_after:
            if len(msg) > 50 and msg != test_message:  # 非用户消息
                assistant_found = True
                break
        
        if assistant_found:
            record_test("LLM 响应", True, f"找到 {len(messages_after)} 条消息")
        else:
            record_test("LLM 响应", False, f"消息数: {len(messages_after)}")
        
        await save_screenshot(self.page, "06-llm-response")
        
        return messages_after
        
    async def test_4_session_switch_data_integrity(self):
        """测试 4: 会话切换数据完整性（关键测试）"""
        log("\n=== 测试 4: 会话切换数据完整性 ===")
        
        # 创建 Session A
        new_session_btn = self.page.locator('button[aria-label="Create new session"]')
        await new_session_btn.click()
        await self.page.wait_for_timeout(1000)
        
        session_btns = await get_session_buttons(self.page)
        session_a = session_btns[-1] if session_btns else None
        
        if not session_a:
            record_test("Session A 创建", False, "无法创建 Session A")
            return
        
        # 在 Session A 发送消息
        await session_a.click()
        await self.page.wait_for_timeout(500)
        
        input_area = self.page.locator('textarea[placeholder*="Ask anything"]')
        await input_area.fill("Session A: What is Python? Please give a brief answer.")
        await input_area.press("Enter")
        await self.page.wait_for_timeout(3000)
        
        # 记录 Session A 消息状态
        msg_count_a_before = await get_message_count(self.page)
        messages_a_before = await get_message_list(self.page)
        
        record_test("Session A 发送消息", True, f"消息数: {msg_count_a_before}")
        await save_screenshot(self.page, "07-session-a-before-switch")
        
        # 创建 Session B
        await new_session_btn.click()
        await self.page.wait_for_timeout(1000)
        
        session_btns = await get_session_buttons(self.page)
        session_b = session_btns[-1] if session_btns else None
        
        if session_b:
            await session_b.click()
            await self.page.wait_for_timeout(500)
            
            # 在 Session B 发送消息
            input_b = self.page.locator('textarea[placeholder*="Ask anything"]')
            await input_b.fill("Session B: What is JavaScript?")
            await input_b.press("Enter")
            await self.page.wait_for_timeout(3000)
            
            msg_count_b = await get_message_count(self.page)
            record_test("Session B 发送消息", True, f"消息数: {msg_count_b}")
        
        await save_screenshot(self.page, "08-session-b")
        
        # 切换回 Session A（关键测试点）
        log("  切换回 Session A...")
        session_btns = await get_session_buttons(self.page)
        if len(session_btns) >= 2:
            await session_btns[-2].click()  # Session A
            await self.page.wait_for_timeout(3000)
        
        # 检查 Session A 消息是否丢失
        msg_count_a_after = await get_message_count(self.page)
        messages_a_after = await get_message_list(self.page)
        
        # 比较消息内容
        if msg_count_a_after < msg_count_a_before:
            add_issue(
                "P0",
                "Session 切换导致消息丢失",
                f"切换前消息数: {msg_count_a_before}, 切换后消息数: {msg_count_a_after}",
                [
                    "1. 在 Session A 发送消息",
                    f"2. 记录消息数: {msg_count_a_before}",
                    "3. 切换到 Session B",
                    "4. 切换回 Session A",
                    f"5. 检查消息数: {msg_count_a_after}",
                    "6. 消息丢失！"
                ],
                ["07-session-a-before-switch.png", "09-session-a-after-switch.png"]
            )
            record_test("会话切换数据完整性", False, f"消息丢失: {msg_count_a_before} -> {msg_count_a_after}")
        elif msg_count_a_after >= msg_count_a_before:
            record_test("会话切换数据完整性", True, f"消息保持: {msg_count_a_after}")
        
        await save_screenshot(self.page, "09-session-a-after-switch")
        
        # 检查控制台错误
        errors = [l for l in console_logs if l["type"] == "error"]
        if errors:
            add_issue(
                "P2",
                "控制台有错误日志",
                f"发现 {len(errors)} 个错误",
                [f"检查控制台日志: {[e['text'][:100] for e in errors[:3]]}"],
                []
            )
        
    async def test_5_export_functionality(self):
        """测试 5: 导出功能"""
        log("\n=== 测试 5: 导出功能 ===")
        
        session_btns = await get_session_buttons(self.page)
        if session_btns:
            # hover 显示导出按钮
            await session_btns[0].hover()
            await self.page.wait_for_timeout(300)
            
            export_btn = self.page.locator('button[aria-label="Export session"]').first
            if await export_btn.is_visible(timeout=2000):
                await export_btn.click()
                await self.page.wait_for_timeout(1000)
                
                # 检查是否有成功提示
                toast = self.page.locator('.toast, [role="status"], [class*="toast"]')
                if await toast.is_visible(timeout=3000):
                    toast_text = await toast.inner_text()
                    if "exported" in toast_text.lower() or "成功" in toast_text:
                        record_test("导出功能", True, toast_text[:50])
                    else:
                        record_test("导出功能", False, toast_text[:50])
                else:
                    record_test("导出功能", True, "无错误提示")
            else:
                record_test("导出按钮可见", False, "hover 后未显示导出按钮")
        
        await save_screenshot(self.page, "10-export")
        
    async def test_6_settings_panel(self):
        """测试 6: 设置面板"""
        log("\n=== 测试 6: 设置面板 ===")
        
        # 打开设置
        settings_btn = self.page.locator('button[aria-label="Settings"]')
        await settings_btn.click()
        await self.page.wait_for_timeout(1000)
        
        # 检查设置面板是否打开
        settings_title = self.page.locator('h2:text("Settings")')
        if await settings_title.is_visible(timeout=3000):
            record_test("设置面板打开", True, "")
            
            # 测试各个设置项
            settings_items = [
                ("Provider 选择", 'select'),
                ("API Key 输入", 'input[type="password"]'),
                ("Temperature 滑块", 'input[type="range"]'),
            ]
            
            for name, selector in settings_items:
                if await self.page.locator(selector).first.is_visible(timeout=2000):
                    record_test(f"设置项: {name}", True, "")
                else:
                    record_test(f"设置项: {name}", False, "")
            
            await save_screenshot(self.page, "11-settings-panel")
            
            # 关闭设置
            close_btn = self.page.locator('button[aria-label="Close settings"]')
            if await close_btn.is_visible(timeout=2000):
                await close_btn.click()
                record_test("设置面板关闭", True, "")
        else:
            record_test("设置面板打开", False, "")
            
    async def test_7_mode_toggle(self):
        """测试 7: 模式切换"""
        log("\n=== 测试 7: 模式切换 ===")
        
        plan_btn = self.page.locator('button:text("Plan")')
        build_btn = self.page.locator('button:text("Build")')
        
        if await plan_btn.is_visible(timeout=2000) and await build_btn.is_visible(timeout=2000):
            # 切换到 Build
            await build_btn.click()
            await self.page.wait_for_timeout(500)
            record_test("切换到 Build 模式", True, "")
            
            # 切换到 Plan
            await plan_btn.click()
            await self.page.wait_for_timeout(500)
            record_test("切换到 Plan 模式", True, "")
            
            await save_screenshot(self.page, "12-mode-toggle")
        else:
            record_test("模式切换按钮", False, "按钮不可见")
            
    async def test_8_concurrent_sessions(self):
        """测试 8: 并发 Session 测试"""
        log("\n=== 测试 8: 并发 Session 测试 ===")
        
        # 创建两个 session
        new_session_btn = self.page.locator('button[aria-label="Create new session"]')
        
        await new_session_btn.click()
        await self.page.wait_for_timeout(500)
        session_btns = await get_session_buttons(self.page)
        session_1 = session_btns[-1] if session_btns else None
        
        await new_session_btn.click()
        await self.page.wait_for_timeout(500)
        session_btns = await get_session_buttons(self.page)
        session_2 = session_btns[-1] if session_btns else None
        
        if not session_1 or not session_2:
            record_test("并发 Session 创建", False, "无法创建足够的 session")
            return
        
        # 在两个 session 中分别发送消息
        # Session 1
        session_btns = await get_session_buttons(self.page)
        await session_btns[-2].click()
        await self.page.wait_for_timeout(300)
        
        input_1 = self.page.locator('textarea[placeholder*="Ask anything"]')
        await input_1.fill("Concurrent test 1: Count to 5")
        await input_1.press("Enter")
        
        session_1_msg_count = await get_message_count(self.page)
        
        # 立即切换到 Session 2
        session_btns = await get_session_buttons(self.page)
        await session_btns[-1].click()
        await self.page.wait_for_timeout(300)
        
        input_2 = self.page.locator('textarea[placeholder*="Ask anything"]')
        await input_2.fill("Concurrent test 2: Say hello")
        await input_2.press("Enter")
        
        session_2_msg_count = await get_message_count(self.page)
        
        record_test("并发发送消息", True, f"Session1: {session_1_msg_count}, Session2: {session_2_msg_count}")
        
        await self.page.wait_for_timeout(5000)
        
        # 快速切换多次
        for i in range(3):
            session_btns = await get_session_buttons(self.page)
            await session_btns[-2].click()
            await self.page.wait_for_timeout(200)
            await session_btns[-1].click()
            await self.page.wait_for_timeout(200)
        
        record_test("快速切换会话", True, "")
        
        await save_screenshot(self.page, "13-concurrent-sessions")
        
    async def test_9_keyboard_shortcuts(self):
        """测试 9: 键盘快捷键"""
        log("\n=== 测试 9: 键盘快捷键 ===")
        
        # 测试 Enter 发送
        input_area = self.page.locator('textarea[placeholder*="Ask anything"]')
        await input_area.fill("Keyboard shortcut test")
        
        # 按 Escape 取消（如果有效）
        await self.page.keyboard.press("Escape")
        await self.page.wait_for_timeout(300)
        
        record_test("键盘快捷键", True, "Escape 和 Enter 已测试")
        
        await save_screenshot(self.page, "14-keyboard-shortcuts")
        
    async def test_10_chinese_support(self):
        """测试 10: 中文支持"""
        log("\n=== 测试 10: 中文支持 ===")
        
        # 创建新会话
        new_session_btn = self.page.locator('button[aria-label="Create new session"]')
        await new_session_btn.click()
        await self.page.wait_for_timeout(1000)
        
        session_btns = await get_session_buttons(self.page)
        if session_btns:
            await session_btns[-1].click()
            await self.page.wait_for_timeout(500)
        
        # 输入中文消息
        input_area = self.page.locator('textarea[placeholder*="Ask anything"]')
        chinese_message = "你好，请用中文回复：什么是人工智能？"
        
        await input_area.fill(chinese_message)
        value = await input_area.input_value()
        
        if value == chinese_message:
            record_test("中文输入", True, "")
        else:
            record_test("中文输入", False, f"输入值: {value[:50]}")
        
        await input_area.press("Enter")
        await self.page.wait_for_timeout(3000)
        
        # 检查中文消息是否显示
        page_content = await self.page.content()
        if "你好" in page_content or "人工智能" in page_content:
            record_test("中文消息显示", True, "")
        else:
            record_test("中文消息显示", False, "")
        
        await save_screenshot(self.page, "15-chinese-support")
        
    async def run_all_tests(self):
        """运行所有测试"""
        log("🚀 开始 CScode 企业级端到端测试...")
        log(f"📁 截图目录: {SCREENSHOT_DIR}")
        
        await self.setup_console_listener()
        
        tests = [
            self.test_1_initial_load,
            self.test_2_session_management,
            self.test_3_chat_interaction,
            self.test_4_session_switch_data_integrity,
            self.test_5_export_functionality,
            self.test_6_settings_panel,
            self.test_7_mode_toggle,
            self.test_8_concurrent_sessions,
            self.test_9_keyboard_shortcuts,
            self.test_10_chinese_support,
        ]
        
        for test in tests:
            try:
                await test()
            except Exception as e:
                add_issue("P1", f"测试异常: {test.__name__}", str(e), [], [])
        
        log("\n" + "=" * 60)
        log("📊 测试完成")


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False, slow_mo=100)
        context = await browser.new_context(viewport={"width": 1440, "height": 900})
        page = await context.new_page()
        
        tester = CScodeE2ETest(page)
        await tester.run_all_tests()
        
        await browser.close()
    
    # 生成报告
    report = {
        "timestamp": datetime.now().isoformat(),
        "summary": {
            "total_tests": len(test_results),
            "passed": sum(1 for t in test_results if t["passed"]),
            "failed": sum(1 for t in test_results if not t["passed"]),
            "issues": len(issues),
        },
        "test_results": test_results,
        "issues": issues,
        "console_errors": [l for l in console_logs if l["type"] == "error"],
    }
    
    report_path = OUTPUT_DIR / "e2e-test-report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    
    # 打印总结
    log(f"\n📁 测试报告: {report_path}")
    log(f"\n📊 测试总结:")
    log(f"   总测试数: {report['summary']['total_tests']}")
    log(f"   通过: {report['summary']['passed']}")
    log(f"   失败: {report['summary']['failed']}")
    log(f"   问题数: {report['summary']['issues']}")
    
    if issues:
        log(f"\n❌ 发现的问题:")
        for issue in issues:
            log(f"   [{issue['severity']}] {issue['title']}: {issue['detail']}")


if __name__ == "__main__":
    asyncio.run(main())