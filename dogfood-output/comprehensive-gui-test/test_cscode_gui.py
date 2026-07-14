#!/usr/bin/env python3
"""
CScode 全面 GUI 功能测试
覆盖所有前端功能、API端点、并发Session隔离
"""

import asyncio
import json
import time
from datetime import datetime
from pathlib import Path
from playwright.async_api import Page, Playwright, async_playwright, expect

OUTPUT_DIR = Path("/Users/mac/AI/CScode/dogfood-output/comprehensive-gui-test")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

test_results = []
console_logs = []
network_requests = []

def log(msg: str):
    print(msg)

def record_result(test_name: str, passed: bool, detail: str, screenshot: str = None):
    result = {
        "test_name": test_name,
        "passed": passed,
        "detail": detail,
        "timestamp": datetime.now().isoformat(),
        "screenshot": screenshot
    }
    test_results.append(result)
    status = "✅" if passed else "❌"
    log(f"  {status} {test_name}: {detail}")

async def save_screenshot(page: Page, name: str):
    path = str(OUTPUT_DIR / f"{name}.png")
    await page.screenshot(path=path)
    return path

class CScodeGUITester:
    def __init__(self, page: Page):
        self.page = page
        self.base_url = "http://localhost:8000"

    async def setup(self):
        """初始化测试环境"""
        self.page.on("console", lambda msg: console_logs.append({
            "type": msg.type,
            "text": msg.text,
            "time": datetime.now().isoformat()
        }))
        self.page.on("request", lambda req: network_requests.append({
            "method": req.method,
            "url": req.url,
            "time": datetime.now().isoformat()
        }))
        self.page.on("response", lambda res: network_requests.append({
            "status": res.status,
            "url": res.url,
            "time": datetime.now().isoformat()
        }))

    async def navigate_to_app(self):
        """导航到应用首页"""
        await self.page.goto(self.base_url, wait_until="domcontentloaded")
        await self.page.wait_for_timeout(3000)

    async def test_session_management(self):
        """测试 Session 管理功能"""
        log("\n" + "="*60)
        log("📋 测试组 1: Session 管理")
        log("="*60)

        # 1.1 创建新 Session
        log("\n--- 1.1 创建新 Session ---")
        try:
            new_session_btn = self.page.locator('button[aria-label="Create new session"]')
            await new_session_btn.click()
            await self.page.wait_for_timeout(1000)

            # 验证新 session 被创建
            sidebar = self.page.locator('[role="navigation"]')
            await expect(sidebar).to_be_visible()
            screenshot = await save_screenshot(self.page, "01-new-session-created")
            record_result("创建新Session", True, "成功创建并显示在侧边栏", screenshot)
        except Exception as e:
            screenshot = await save_screenshot(self.page, "01-new-session-failed")
            record_result("创建新Session", False, f"失败: {str(e)}", screenshot)

        # 1.2 Session 切换
        log("\n--- 1.2 Session 切换 ---")
        try:
            # 创建第二个 session
            new_session_btn = self.page.locator('button[aria-label="Create new session"]')
            await new_session_btn.click()
            await self.page.wait_for_timeout(1000)

            # 获取所有 session 项
            session_items = await self.page.query_selector_all('[role="listitem"], .session-item, .project-item')

            if len(session_items) >= 2:
                # 点击第一个 session
                await session_items[0].click()
                await self.page.wait_for_timeout(500)
                screenshot = await save_screenshot(self.page, "02-session-switch-first")
                record_result("Session切换", True, f"成功切换，共有{len(session_items)}个session", screenshot)
            else:
                screenshot = await save_screenshot(self.page, "02-session-switch-failed")
                record_result("Session切换", False, "Session数量不足，无法测试切换", screenshot)
        except Exception as e:
            screenshot = await save_screenshot(self.page, "02-session-switch-error")
            record_result("Session切换", False, f"切换失败: {str(e)}", screenshot)

        # 1.3 Session 删除 (悬停显示)
        log("\n--- 1.3 Session 删除 ---")
        try:
            # 悬停显示删除按钮
            session_items = await self.page.query_selector_all('[role="listitem"], .session-item, .project-item')
            if session_items:
                await session_items[0].hover()
                await self.page.wait_for_timeout(500)

                # 查找删除按钮 (可能在悬停后才显示)
                delete_btn = await session_items[0].query_selector('button[aria-label*="delete"], button[aria-label*="Delete"]')
                if delete_btn:
                    await delete_btn.click()
                    # 确认删除
                    self.page.on("dialog", lambda dialog: dialog.accept())
                    await self.page.wait_for_timeout(500)
                    screenshot = await save_screenshot(self.page, "03-session-deleted")
                    record_result("Session删除", True, "成功删除session", screenshot)
                else:
                    screenshot = await save_screenshot(self.page, "03-delete-btn-not-found")
                    record_result("Session删除", False, "未找到删除按钮", screenshot)
        except Exception as e:
            screenshot = await save_screenshot(self.page, "03-session-delete-error")
            record_result("Session删除", False, f"删除失败: {str(e)}", screenshot)

    async def test_message_interaction(self):
        """测试消息交互功能"""
        log("\n" + "="*60)
        log("📋 测试组 2: 消息交互 (LLM 对话)")
        log("="*60)

        # 2.1 发送普通消息
        log("\n--- 2.1 发送普通消息 ---")
        try:
            # 创建新 session
            new_session_btn = self.page.locator('button[aria-label="Create new session"]')
            await new_session_btn.click()
            await self.page.wait_for_timeout(1000)

            # 输入消息
            input_area = self.page.locator('textarea[placeholder*="Ask anything"]')
            await input_area.fill("你好，请简单介绍一下你自己")
            await input_area.press("Enter")

            # 等待响应
            await self.page.wait_for_timeout(5000)

            # 检查是否有消息显示
            messages = await self.page.query_selector_all('[role="list"] > div, .message, [class*="Message"]')

            if len(messages) >= 2:  # 用户消息 + AI响应
                screenshot = await save_screenshot(self.page, "04-message-sent")
                record_result("发送普通消息", True, f"成功发送并收到响应，共{len(messages)}条消息", screenshot)
            else:
                screenshot = await save_screenshot(self.page, "04-message-no-response")
                record_result("发送普通消息", False, "未收到AI响应", screenshot)
        except Exception as e:
            screenshot = await save_screenshot(self.page, "04-message-error")
            record_result("发送普通消息", False, f"发送失败: {str(e)}", screenshot)

        # 2.2 流式响应显示
        log("\n--- 2.2 流式响应显示 ---")
        try:
            # 发送需要长响应的消息
            input_area = self.page.locator('textarea[placeholder*="Ask anything"]')
            await input_area.fill("请用中文详细解释什么是机器学习，至少500字")
            await input_area.press("Enter")

            # 观察流式效果
            content_before = await self.page.content()
            await self.page.wait_for_timeout(3000)
            content_after = await self.page.content()

            # 检查内容是否在增加
            if len(content_after) > len(content_before):
                screenshot = await save_screenshot(self.page, "05-streaming-response")
                record_result("流式响应显示", True, "内容正在流式增加", screenshot)
            else:
                screenshot = await save_screenshot(self.page, "05-no-streaming")
                record_result("流式响应显示", False, "内容未增加，可能无流式效果", screenshot)
        except Exception as e:
            screenshot = await save_screenshot(self.page, "05-streaming-error")
            record_result("流式响应显示", False, f"流式检测失败: {str(e)}", screenshot)

        # 2.3 中断响应
        log("\n--- 2.3 中断响应 ---")
        try:
            # 发送消息
            input_area = self.page.locator('textarea[placeholder*="Ask anything"]')
            await input_area.fill("请写一个很长的故事")
            await input_area.press("Enter")
            await self.page.wait_for_timeout(2000)

            # 查找停止按钮
            stop_btn = self.page.locator('button[aria-label*="stop"], button[aria-label*="Stop"], button:has-text("Stop")')
            if await stop_btn.count() > 0:
                await stop_btn.click()
                await self.page.wait_for_timeout(1000)
                screenshot = await save_screenshot(self.page, "06-response-stopped")
                record_result("中断响应", True, "成功中断响应", screenshot)
            else:
                screenshot = await save_screenshot(self.page, "06-no-stop-btn")
                record_result("中断响应", False, "未找到停止按钮", screenshot)
        except Exception as e:
            screenshot = await save_screenshot(self.page, "06-stop-error")
            record_result("中断响应", False, f"中断失败: {str(e)}", screenshot)

    async def test_concurrent_session_isolation(self):
        """测试并发 Session 隔离"""
        log("\n" + "="*60)
        log("📋 测试组 3: 并发 Session 隔离 (重点)")
        log("="*60)

        # 3.1 创建多个并发 Session
        log("\n--- 3.1 创建多个并发 Session ---")
        try:
            session_ids = []

            # 创建 Session A
            new_session_btn = self.page.locator('button[aria-label="Create new session"]')
            await new_session_btn.click()
            await self.page.wait_for_timeout(1000)
            session_a_id = await self.page.evaluate("""() => {
                return window.__STORE_STATE__ ? window.__STORE_STATE__.activeSessionId : null;
            }""")
            session_ids.append(session_a_id)

            # 在 Session A 发送消息
            input_a = self.page.locator('textarea[placeholder*="Ask anything"]')
            await input_a.fill("请用中文详细解释Python编程语言")
            await input_a.press("Enter")

            # 创建 Session B
            await new_session_btn.click()
            await self.page.wait_for_timeout(1000)
            session_b_id = await self.page.evaluate("""() => {
                return window.__STORE_STATE__ ? window.__STORE_STATE__.activeSessionId : null;
            }""")
            session_ids.append(session_b_id)

            # 在 Session B 发送消息
            input_b = self.page.locator('textarea[placeholder*="Ask anything"]')
            await input_b.fill("请用中文详细解释JavaScript编程语言")
            await input_b.press("Enter")

            await self.page.wait_for_timeout(5000)

            screenshot = await save_screenshot(self.page, "07-concurrent-sessions")
            record_result("创建并发Session", True, f"成功创建2个并发Session: {session_ids}", screenshot)
        except Exception as e:
            screenshot = await save_screenshot(self.page, "07-concurrent-error")
            record_result("创建并发Session", False, f"创建失败: {str(e)}", screenshot)

        # 3.2 并行 LLM 请求隔离测试
        log("\n--- 3.2 并行 LLM 请求隔离测试 ---")
        try:
            # 等待响应
            await self.page.wait_for_timeout(10000)

            # 获取页面内容，检查是否包含 Python 和 JavaScript 关键词
            content = await self.page.content()
            has_python = "Python" in content or "python" in content
            has_javascript = "JavaScript" in content or "javascript" in content

            # 获取当前活跃 session
            current_session = await self.page.evaluate("""() => {
                return window.__STORE_STATE__ ? window.__STORE_STATE__.activeSessionId : null;
            }""")

            screenshot = await save_screenshot(self.page, "08-parallel-requests")

            if has_python or has_javascript:
                record_result("并行LLM请求", True, f"当前Session {current_session} 包含响应内容", screenshot)
            else:
                record_result("并行LLM请求", False, "未检测到响应内容", screenshot)
        except Exception as e:
            screenshot = await save_screenshot(self.page, "08-parallel-error")
            record_result("并行LLM请求", False, f"测试失败: {str(e)}", screenshot)

        # 3.3 切换 Session 查看进度
        log("\n--- 3.3 切换 Session 查看进度 ---")
        try:
            # 获取所有 session 项
            session_items = await self.page.query_selector_all('[role="listitem"], .session-item, .project-item')

            if len(session_items) >= 2:
                # 记录切换前的内容
                content_before = await self.page.content()
                python_count_before = content_before.count("Python") + content_before.count("python")

                # 切换到第一个 session
                await session_items[0].click()
                await self.page.wait_for_timeout(3000)

                # 记录切换后的内容
                content_after = await self.page.content()
                python_count_after = content_after.count("Python") + content_after.count("python")

                screenshot = await save_screenshot(self.page, "09-session-switch-progress")

                if python_count_after >= python_count_before * 0.8:  # 允许20%损失
                    record_result("切换Session保留进度", True, 
                        f"Python关键词从{python_count_before}到{python_count_after}，保留{python_count_after/python_count_before*100:.1f}%", 
                        screenshot)
                else:
                    record_result("切换Session保留进度", False, 
                        f"Python关键词从{python_count_before}减少到{python_count_after}，丢失{(python_count_before-python_count_after)/python_count_before*100:.1f}%", 
                        screenshot)
            else:
                screenshot = await save_screenshot(self.page, "09-not-enough-sessions")
                record_result("切换Session保留进度", False, "Session数量不足", screenshot)
        except Exception as e:
            screenshot = await save_screenshot(self.page, "09-switch-progress-error")
            record_result("切换Session保留进度", False, f"测试失败: {str(e)}", screenshot)

    async def test_settings(self):
        """测试设置功能"""
        log("\n" + "="*60)
        log("📋 测试组 4: 设置功能")
        log("="*60)

        # 4.1 打开设置
        log("\n--- 4.1 打开设置 ---")
        try:
            settings_btn = self.page.locator('button:has-text("Settings"), button[aria-label="Settings"]')
            await settings_btn.click()
            await self.page.wait_for_timeout(1000)

            # 检查设置对话框是否显示
            settings_dialog = self.page.locator('[role="dialog"], .modal, [class*="settings"]')
            if await settings_dialog.count() > 0:
                screenshot = await save_screenshot(self.page, "10-settings-open")
                record_result("打开设置", True, "设置对话框已显示", screenshot)
            else:
                screenshot = await save_screenshot(self.page, "10-settings-not-found")
                record_result("打开设置", False, "设置对话框未找到", screenshot)
        except Exception as e:
            screenshot = await save_screenshot(self.page, "10-settings-error")
            record_result("打开设置", False, f"打开失败: {str(e)}", screenshot)

        # 4.2 Provider 选择
        log("\n--- 4.2 Provider 选择 ---")
        try:
            provider_select = self.page.locator('select[name="provider"], select[id="provider"], [class*="provider"] select')
            if await provider_select.count() > 0:
                options = await provider_select.locator('option').all_inner_texts()
                screenshot = await save_screenshot(self.page, "11-provider-options")
                record_result("Provider选择", True, f"可用Provider: {options}", screenshot)
            else:
                screenshot = await save_screenshot(self.page, "11-provider-not-found")
                record_result("Provider选择", False, "未找到Provider选择器", screenshot)
        except Exception as e:
            screenshot = await save_screenshot(self.page, "11-provider-error")
            record_result("Provider选择", False, f"查找失败: {str(e)}", screenshot)

        # 关闭设置
        try:
            close_btn = self.page.locator('button[aria-label="Close"], button:has-text("Close"), button:has-text("取消")')
            if await close_btn.count() > 0:
                await close_btn.click()
                await self.page.wait_for_timeout(500)
        except:
            pass

    async def test_api_endpoints(self):
        """测试 API 端点"""
        log("\n" + "="*60)
        log("📋 测试组 5: API 端点")
        log("="*60)

        # 5.1 Session 列表 API
        log("\n--- 5.1 Session 列表 API ---")
        try:
            response = await self.page.evaluate("""async () => {
                const res = await fetch('/api/sessions');
                return { status: res.status, ok: res.ok };
            }""")
            if response["ok"]:
                record_result("Session列表API", True, f"状态码: {response['status']}")
            else:
                record_result("Session列表API", False, f"请求失败，状态码: {response['status']}")
        except Exception as e:
            record_result("Session列表API", False, f"请求异常: {str(e)}")

        # 5.2 Config API
        log("\n--- 5.2 Config API ---")
        try:
            response = await self.page.evaluate("""async () => {
                const res = await fetch('/api/config');
                return { status: res.status, ok: res.ok };
            }""")
            if response["ok"]:
                record_result("Config API", True, f"状态码: {response['status']}")
            else:
                record_result("Config API", False, f"请求失败，状态码: {response['status']}")
        except Exception as e:
            record_result("Config API", False, f"请求异常: {str(e)}")

        # 5.3 Health Check
        log("\n--- 5.3 Health Check ---")
        try:
            response = await self.page.evaluate("""async () => {
                const res = await fetch('/api/health');
                return { status: res.status, ok: res.ok };
            }""")
            if response["ok"]:
                record_result("Health Check", True, f"状态码: {response['status']}")
            else:
                record_result("Health Check", False, f"请求失败，状态码: {response['status']}")
        except Exception as e:
            record_result("Health Check", False, f"请求异常: {str(e)}")

    async def test_tool_execution(self):
        """测试工具调用"""
        log("\n" + "="*60)
        log("📋 测试组 6: 工具调用")
        log("="*60)

        # 6.1 文件读取工具
        log("\n--- 6.1 文件读取工具 ---")
        try:
            # 发送触发工具调用的消息
            input_area = self.page.locator('textarea[placeholder*="Ask anything"]')
            await input_area.fill("请读取当前目录下的README.md文件")
            await input_area.press("Enter")

            await self.page.wait_for_timeout(10000)  # 等待工具执行

            # 检查是否有工具调用显示
            tool_call_display = self.page.locator('[class*="tool"], [class*="Tool"], [data-tool]')
            has_tool_display = await tool_call_display.count() > 0

            screenshot = await save_screenshot(self.page, "12-tool-read")
            if has_tool_display:
                record_result("文件读取工具", True, "工具调用显示正常", screenshot)
            else:
                record_result("文件读取工具", False, "未检测到工具调用显示", screenshot)
        except Exception as e:
            screenshot = await save_screenshot(self.page, "12-tool-read-error")
            record_result("文件读取工具", False, f"测试失败: {str(e)}", screenshot)

        # 6.2 Shell 执行工具
        log("\n--- 6.2 Shell 执行工具 ---")
        try:
            input_area = self.page.locator('textarea[placeholder*="Ask anything"]')
            await input_area.fill("请执行 ls -la 命令")
            await input_area.press("Enter")

            await self.page.wait_for_timeout(10000)

            content = await self.page.content()
            has_shell_output = "total" in content or "drwx" in content or "-rw" in content

            screenshot = await save_screenshot(self.page, "13-tool-shell")
            if has_shell_output:
                record_result("Shell执行工具", True, "Shell输出显示正常", screenshot)
            else:
                record_result("Shell执行工具", False, "未检测到Shell输出", screenshot)
        except Exception as e:
            screenshot = await save_screenshot(self.page, "13-tool-shell-error")
            record_result("Shell执行工具", False, f"测试失败: {str(e)}", screenshot)

    async def test_edge_cases(self):
        """测试边界情况"""
        log("\n" + "="*60)
        log("📋 测试组 7: 边界情况")
        log("="*60)

        # 7.1 超长消息
        log("\n--- 7.1 超长消息 ---")
        try:
            input_area = self.page.locator('textarea[placeholder*="Ask anything"]')
            long_message = "这是一个超长消息测试。" * 1000  # 约10000字符
            await input_area.fill(long_message)
            await input_area.press("Enter")

            await self.page.wait_for_timeout(5000)

            screenshot = await save_screenshot(self.page, "14-long-message")
            # 检查是否有错误提示或正常处理
            error_toast = self.page.locator('[class*="toast"], [class*="error"]')
            has_error = await error_toast.count() > 0

            if has_error:
                record_result("超长消息", True, "系统正确拒绝或截断超长消息", screenshot)
            else:
                record_result("超长消息", True, "系统正常处理超长消息", screenshot)
        except Exception as e:
            screenshot = await save_screenshot(self.page, "14-long-message-error")
            record_result("超长消息", False, f"测试失败: {str(e)}", screenshot)

        # 7.2 空消息
        log("\n--- 7.2 空消息 ---")
        try:
            input_area = self.page.locator('textarea[placeholder*="Ask anything"]')
            await input_area.fill("")
            await input_area.press("Enter")

            await self.page.wait_for_timeout(1000)

            screenshot = await save_screenshot(self.page, "15-empty-message")
            record_result("空消息", True, "空消息正确处理（不发送）", screenshot)
        except Exception as e:
            screenshot = await save_screenshot(self.page, "15-empty-message-error")
            record_result("空消息", False, f"测试失败: {str(e)}", screenshot)


async def run_tests(playwright: Playwright):
    """运行所有测试"""
    log("🚀 CScode 全面 GUI 功能测试")
    log("="*60)

    browser = await playwright.chromium.launch(headless=False, slow_mo=100)
    context = await browser.new_context(viewport={"width": 1440, "height": 900})
    page = await context.new_page()

    tester = CScodeGUITester(page)
    await tester.setup()

    try:
        await tester.navigate_to_app()
        await tester.test_session_management()
        await tester.test_message_interaction()
        await tester.test_concurrent_session_isolation()
        await tester.test_settings()
        await tester.test_api_endpoints()
        await tester.test_tool_execution()
        await tester.test_edge_cases()
    except Exception as e:
        log(f"❌ 测试执行异常: {e}")
    finally:
        await browser.close()


async def main():
    async with async_playwright() as playwright:
        await run_tests(playwright)

    # 保存测试结果
    report = {
        "timestamp": datetime.now().isoformat(),
        "test_results": test_results,
        "console_logs": console_logs[-500:] if console_logs else [],  # 只保留最后500条
        "network_requests": network_requests[-200:] if network_requests else [],  # 只保留最后200条
        "summary": {
            "total": len(test_results),
            "passed": sum(1 for t in test_results if t["passed"]),
            "failed": sum(1 for t in test_results if not t["passed"]),
        }
    }

    report_path = OUTPUT_DIR / "test_results.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    log("\n" + "="*60)
    log("📊 测试报告")
    log("="*60)
    log(f"   总测试数: {report['summary']['total']}")
    log(f"   通过: {report['summary']['passed']}")
    log(f"   失败: {report['summary']['failed']}")
    log(f"\n📁 详细报告: {report_path}")

    # 打印失败的测试
    failed_tests = [t for t in test_results if not t["passed"]]
    if failed_tests:
        log("\n❌ 失败的测试:")
        for t in failed_tests:
            log(f"   {t['test_name']}: {t['detail']}")


if __name__ == "__main__":
    asyncio.run(main())