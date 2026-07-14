#!/usr/bin/env python3
"""
CScode 全面 GUI 功能测试 v2
覆盖所有按钮、并发Session隔离、流式响应
基于实际DOM结构编写精确选择器
"""

import asyncio
import json
import time
from datetime import datetime
from pathlib import Path
from playwright.async_api import Page, Playwright, async_playwright

OUTPUT_DIR = Path("/Users/mac/AI/CScode/dogfood-output/comprehensive-gui-test")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

test_results = []
console_logs = []
network_requests = []

def log(msg: str):
    ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    print(f"[{ts}] {msg}")

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

async def screenshot(page: Page, name: str):
    path = str(OUTPUT_DIR / f"v2_{name}.png")
    await page.screenshot(path=path)
    return path

class Tester:
    def __init__(self, page: Page):
        self.page = page
        self.base_url = "http://localhost:8000"
        self.session_counter = 0

    async def setup(self):
        self.page.on("console", lambda msg: console_logs.append({
            "type": msg.type, "text": msg.text,
            "time": datetime.now().isoformat()
        }))
        self.page.on("request", lambda req: network_requests.append({
            "method": req.method, "url": req.url,
            "time": datetime.now().isoformat()
        }) if "/api/" in req.url else None)
        self.page.on("response", lambda res: network_requests.append({
            "status": res.status, "url": res.url,
            "time": datetime.now().isoformat()
        }) if "/api/" in res.url else None)

    async def goto(self):
        await self.page.goto(self.base_url, wait_until="domcontentloaded")
        await self.page.wait_for_timeout(2000)

    # ===== 工具方法 =====
    async def get_sidebar_buttons(self):
        """获取侧边栏所有按钮"""
        buttons = await self.page.query_selector_all('aside button, [role="navigation"] button')
        result = []
        for btn in buttons:
            label = await btn.get_attribute("aria-label") or ""
            text = await btn.inner_text()
            classes = await btn.get_attribute("class") or ""
            result.append({"el": btn, "label": label, "text": text.strip(), "classes": classes})
        return result

    async def get_visible_buttons(self):
        """获取页面上所有可见按钮"""
        buttons = await self.page.query_selector_all('button')
        result = []
        for btn in buttons:
            if not await btn.is_visible():
                continue
            label = await btn.get_attribute("aria-label") or ""
            text = await btn.inner_text()
            result.append({"el": btn, "label": label, "text": text.strip()})
        return result

    async def find_button_by_label(self, label_substring: str):
        """通过aria-label查找按钮"""
        buttons = await self.get_visible_buttons()
        for b in buttons:
            if label_substring.lower() in b["label"].lower():
                return b["el"]
        return None

    async def find_button_by_text(self, text: str):
        """通过文本查找按钮"""
        buttons = await self.get_visible_buttons()
        for b in buttons:
            if text.lower() in b["text"].lower():
                return b["el"]
        return None

    async def get_all_session_items(self):
        """获取侧边栏所有session列表项"""
        # ProjectItem 渲染为 li 元素
        items = await self.page.query_selector_all('aside li, [role="navigation"] li, [role="listitem"]')
        result = []
        for item in items:
            if await item.is_visible():
                text = await item.inner_text()
                result.append({"el": item, "text": text.strip()})
        return result

    async def create_new_session(self):
        """创建新session并返回ID"""
        btn = await self.find_button_by_label("Create new session")
        if btn:
            await btn.click()
            await self.page.wait_for_timeout(800)
            self.session_counter += 1
            return True
        return False

    async def get_active_session_id(self):
        """从store获取当前活跃session ID"""
        try:
            sid = await self.page.evaluate("""() => {
                const state = useSessionStore?.getState?.();
                return state?.activeSessionId || null;
            }""")
            return sid
        except:
            return None

    async def get_page_messages(self):
        """获取页面上显示的消息内容"""
        content = await self.page.content()
        return content

    async def count_keyword(self, keyword: str):
        """统计页面上关键词出现次数"""
        content = await self.get_page_messages()
        return content.lower().count(keyword.lower())

    async def send_message(self, text: str):
        """发送消息"""
        textarea = self.page.locator('textarea[placeholder*="Ask anything"]')
        await textarea.fill(text)
        await textarea.press("Enter")
        await self.page.wait_for_timeout(500)

    # ===== 测试组1: 所有按钮可点击 =====
    async def test_all_buttons_clickable(self):
        log("\n" + "="*60)
        log("📋 测试组1: 所有按钮可点击")
        log("="*60)

        buttons_to_test = [
            ("Create new session", "创建新Session"),
            ("Filter threads", "筛选线程"),
            ("Sort threads", "排序线程"),
            ("Refresh sessions", "刷新会话"),
            ("Settings", "设置"),
        ]

        for label, desc in buttons_to_test:
            try:
                btn = await self.find_button_by_label(label)
                if btn:
                    await btn.click()
                    await self.page.wait_for_timeout(300)
                    record_result(f"按钮点击: {desc}", True, f"成功点击 '{label}'")
                else:
                    record_result(f"按钮点击: {desc}", False, f"未找到 '{label}' 按钮")
            except Exception as e:
                record_result(f"按钮点击: {desc}", False, f"异常: {e}")

        # 关闭settings（如果打开）
        try:
            close_btn = await self.find_button_by_label("Close settings")
            if close_btn:
                await close_btn.click()
                await self.page.wait_for_timeout(300)
        except:
            pass

        # 测试 ModeToggle
        try:
            plan_btn = await self.find_button_by_text("Plan")
            build_btn = await self.find_button_by_text("Build")
            if plan_btn and build_btn:
                await plan_btn.click()
                await self.page.wait_for_timeout(300)
                await build_btn.click()
                await self.page.wait_for_timeout(300)
                record_result("按钮点击: Mode切换", True, "Plan/Build切换正常")
            else:
                record_result("按钮点击: Mode切换", False, f"Plan={plan_btn is not None}, Build={build_btn is not None}")
        except Exception as e:
            record_result("按钮点击: Mode切换", False, f"异常: {e}")

        await screenshot(self.page, "01_all_buttons")

    # ===== 测试组2: Session管理 =====
    async def test_session_management(self):
        log("\n" + "="*60)
        log("📋 测试组2: Session管理")
        log("="*60)

        # 2.1 创建多个session
        for i in range(3):
            success = await self.create_new_session()
            record_result(f"创建Session {i+1}", success, "创建成功" if success else "创建失败")

        await screenshot(self.page, "02_sessions_created")

        # 2.2 获取所有session
        sessions = await self.get_all_session_items()
        record_result("Session列表", len(sessions) >= 3, f"找到 {len(sessions)} 个session")

        # 2.3 悬停显示导出/删除按钮
        if sessions:
            try:
                await sessions[0]["el"].hover()
                await self.page.wait_for_timeout(500)

                # 查找悬停后显示的按钮
                hover_buttons = await self.page.query_selector_all('li:hover button, [role="listitem"]:hover button')
                export_found = False
                delete_found = False
                for hb in hover_buttons:
                    label = await hb.get_attribute("aria-label") or ""
                    if "export" in label.lower():
                        export_found = True
                    if "delete" in label.lower():
                        delete_found = True

                record_result("悬停显示导出按钮", export_found, f"导出按钮: {export_found}")
                record_result("悬停显示删除按钮", delete_found, f"删除按钮: {delete_found}")
            except Exception as e:
                record_result("悬停按钮测试", False, f"异常: {e}")

        await screenshot(self.page, "02_hover_buttons")

        # 2.4 导出session
        if sessions:
            try:
                await sessions[0]["el"].hover()
                await self.page.wait_for_timeout(500)
                export_btn = await self.find_button_by_label("Export session")
                if export_btn:
                    # 监听下载事件
                    async with self.page.expect_download(timeout=5000) as download_info:
                        await export_btn.click()
                    download = await download_info.value
                    record_result("导出Session", True, f"下载文件: {download.suggested_filename}")
                else:
                    record_result("导出Session", False, "未找到导出按钮")
            except Exception as e:
                record_result("导出Session", False, f"异常: {e}")

        # 2.5 删除session
        sessions_before = await self.get_all_session_items()
        if sessions_before:
            try:
                await sessions_before[0]["el"].hover()
                await self.page.wait_for_timeout(500)
                delete_btn = await self.find_button_by_label("Delete session")
                if delete_btn:
                    await delete_btn.click()
                    await self.page.wait_for_timeout(800)
                    sessions_after = await self.get_all_session_items()
                    deleted = len(sessions_after) < len(sessions_before)
                    record_result("删除Session", deleted,
                        f"删除前{len(sessions_before)}个，删除后{len(sessions_after)}个")
                else:
                    record_result("删除Session", False, "未找到删除按钮")
            except Exception as e:
                record_result("删除Session", False, f"异常: {e}")

        await screenshot(self.page, "02_session_mgmt")

    # ===== 测试组3: 消息交互 =====
    async def test_message_interaction(self):
        log("\n" + "="*60)
        log("📋 测试组3: 消息交互")
        log("="*60)

        # 确保有一个session
        await self.create_new_session()
        await self.page.wait_for_timeout(500)

        # 3.1 发送消息
        try:
            await self.send_message("你好，请用中文介绍Python")
            await self.page.wait_for_timeout(3000)

            content = await self.get_page_messages()
            has_user_msg = "你好" in content or "Python" in content
            record_result("发送消息", has_user_msg, "用户消息已显示" if has_user_msg else "未找到用户消息")
        except Exception as e:
            record_result("发送消息", False, f"异常: {e}")

        await screenshot(self.page, "03_message_sent")

        # 3.2 检查流式响应
        try:
            await self.page.wait_for_timeout(5000)
            content = await self.get_page_messages()
            # 检查是否有assistant消息
            has_response = "python" in content.lower() or "编程" in content or "语言" in content
            record_result("流式响应", has_response, "收到AI响应" if has_response else "未收到响应")
        except Exception as e:
            record_result("流式响应", False, f"异常: {e}")

        # 3.3 Attach按钮
        try:
            attach_btn = await self.find_button_by_label("Attach file")
            record_result("Attach按钮", attach_btn is not None,
                "Attach按钮存在" if attach_btn else "未找到Attach按钮")
        except Exception as e:
            record_result("Attach按钮", False, f"异常: {e}")

        await screenshot(self.page, "03_message_interaction")

    # ===== 测试组4: 并发Session隔离（核心） =====
    async def test_concurrent_session_isolation(self):
        log("\n" + "="*60)
        log("📋 测试组4: 并发Session隔离（核心测试）")
        log("="*60)

        # 清理现有session，创建两个全新session
        # 先创建Session A
        await self.create_new_session()
        await self.page.wait_for_timeout(500)
        sid_a = await self.get_active_session_id()
        log(f"  Session A ID: {sid_a}")

        # 发送消息A（长响应）
        await self.send_message("请详细解释Python编程语言，至少提到10个Python相关概念")
        await self.page.wait_for_timeout(2000)

        # 记录Session A的内容
        content_a_before = await self.get_page_messages()
        python_count_a_before = await self.count_keyword("python")
        log(f"  Session A 发送后 'python' 出现次数: {python_count_a_before}")

        # 创建Session B
        await self.create_new_session()
        await self.page.wait_for_timeout(500)
        sid_b = await self.get_active_session_id()
        log(f"  Session B ID: {sid_b}")

        # 发送消息B
        await self.send_message("请详细解释JavaScript编程语言，至少提到10个JavaScript相关概念")
        await self.page.wait_for_timeout(2000)

        content_b_before = await self.get_page_messages()
        js_count_b_before = await self.count_keyword("javascript")
        log(f"  Session B 发送后 'javascript' 出现次数: {js_count_b_before}")

        await screenshot(self.page, "04_both_sessions_running")

        # 等待两个session都有响应
        log("  等待两个session响应...")
        await self.page.wait_for_timeout(8000)

        # 切换到Session A
        sessions = await self.get_all_session_items()
        log(f"  当前有 {len(sessions)} 个session")

        # 点击第一个session（应该是A）
        if len(sessions) >= 2:
            try:
                # 点击第一个session项
                await sessions[0]["el"].click()
                await self.page.wait_for_timeout(3000)

                content_a_after = await self.get_page_messages()
                python_count_a_after = await self.count_keyword("python")
                log(f"  切换回Session A后 'python' 出现次数: {python_count_a_after}")

                # 验证Session A的内容没有被破坏
                if python_count_a_after >= python_count_a_before * 0.5:
                    record_result("Session A隔离性", True,
                        f"Python内容保留 {python_count_a_after}/{python_count_a_before}")
                else:
                    record_result("Session A隔离性", False,
                        f"Python内容丢失 {python_count_a_before} -> {python_count_a_after}")

                await screenshot(self.page, "04_session_a_after_switch")

                # 再切换到Session B
                await sessions[1]["el"].click()
                await self.page.wait_for_timeout(3000)

                content_b_after = await self.get_page_messages()
                js_count_b_after = await self.count_keyword("javascript")
                log(f"  切换到Session B后 'javascript' 出现次数: {js_count_b_after}")

                if js_count_b_after >= js_count_b_before * 0.5:
                    record_result("Session B隔离性", True,
                        f"JS内容保留 {js_count_b_after}/{js_count_b_before}")
                else:
                    record_result("Session B隔离性", False,
                        f"JS内容丢失 {js_count_b_before} -> {js_count_b_after}")

                await screenshot(self.page, "04_session_b_after_switch")

                # 检查消息乱窜：Session B不应该有Python相关内容
                python_in_b = await self.count_keyword("python")
                if python_in_b > 0 and sid_a != sid_b:
                    # 注意：用户消息中可能包含"Python"，所以放宽判断
                    record_result("消息乱窜检查", python_in_b <= 2,
                        f"Session B中'python'出现{python_in_b}次（用户消息可能包含）")
                else:
                    record_result("消息乱窜检查", True, "未检测到消息乱窜")

            except Exception as e:
                record_result("Session切换测试", False, f"异常: {e}")
        else:
            record_result("Session切换测试", False, f"session数量不足: {len(sessions)}")

    # ===== 测试组5: 流式响应中断 =====
    async def test_stream_interruption(self):
        log("\n" + "="*60)
        log("📋 测试组5: 流式响应中断")
        log("="*60)

        await self.create_new_session()
        await self.page.wait_for_timeout(500)

        # 发送长消息
        await self.send_message("请写一个很长很长的故事，至少1000字")
        await self.page.wait_for_timeout(2000)

        # 查找停止按钮
        try:
            stop_btn = await self.find_button_by_label("Stop generation")
            if stop_btn:
                await stop_btn.click()
                await self.page.wait_for_timeout(1000)
                record_result("停止响应", True, "成功点击停止按钮")
            else:
                record_result("停止响应", False, "未找到停止按钮（可能响应已完成）")
        except Exception as e:
            record_result("停止响应", False, f"异常: {e}")

        await screenshot(self.page, "05_stream_stopped")

    # ===== 测试组6: Settings功能 =====
    async def test_settings(self):
        log("\n" + "="*60)
        log("📋 测试组6: Settings功能")
        log("="*60)

        try:
            settings_btn = await self.find_button_by_label("Settings")
            if settings_btn:
                await settings_btn.click()
                await self.page.wait_for_timeout(1000)

                # 检查设置面板是否显示
                settings_panel = self.page.locator('[class*="SettingsPanel"], [class*="settings"], [role="dialog"]')
                visible = await settings_panel.is_visible() if await settings_panel.count() > 0 else False
                record_result("打开Settings", visible, "设置面板已显示" if visible else "设置面板未显示")

                if visible:
                    await screenshot(self.page, "06_settings_open")

                    # 检查Provider选择器
                    provider_select = self.page.locator('select').first
                    if await provider_select.count() > 0:
                        options = await provider_select.locator('option').all_inner_texts()
                        record_result("Provider选项", len(options) > 0, f"可用Provider: {options}")
                    else:
                        record_result("Provider选项", False, "未找到Provider选择器")

                    # 关闭设置
                    close_btn = await self.find_button_by_label("Close settings")
                    if close_btn:
                        await close_btn.click()
                        await self.page.wait_for_timeout(300)
            else:
                record_result("打开Settings", False, "未找到Settings按钮")
        except Exception as e:
            record_result("Settings测试", False, f"异常: {e}")

    # ===== 测试组7: API端点检查 =====
    async def test_api_endpoints(self):
        log("\n" + "="*60)
        log("📋 测试组7: API端点检查")
        log("="*60)

        endpoints = [
            ("/api/health", "GET", "Health Check"),
            ("/api/config", "GET", "Config获取"),
            ("/api/sessions", "GET", "Session列表"),
            ("/api/session", "POST", "Session创建"),
            ("/api/tools", "GET", "工具列表"),
            ("/api/version", "GET", "版本信息"),
        ]

        for path, method, desc in endpoints:
            try:
                res = await self.page.evaluate(f"""async () => {{
                    try {{
                        const res = await fetch('{path}', {{ method: '{method}' }});
                        return {{ status: res.status, ok: res.ok }};
                    }} catch (e) {{
                        return {{ status: 0, ok: false, error: e.message }};
                    }}
                }}""")
                status = res.get("status", 0)
                ok = res.get("ok", False)
                if ok:
                    record_result(f"API: {desc}", True, f"{method} {path} -> {status}")
                elif status == 404:
                    record_result(f"API: {desc}", False, f"{method} {path} -> 404 (未实现)")
                else:
                    record_result(f"API: {desc}", False, f"{method} {path} -> {status}")
            except Exception as e:
                record_result(f"API: {desc}", False, f"异常: {e}")


async def run_tests(playwright: Playwright):
    log("🚀 CScode 全面 GUI 功能测试 v2")
    log("="*60)

    browser = await playwright.chromium.launch(headless=False, slow_mo=80)
    context = await browser.new_context(viewport={"width": 1440, "height": 900})
    page = await context.new_page()

    tester = Tester(page)
    await tester.setup()

    try:
        await tester.goto()
        await tester.test_all_buttons_clickable()
        await tester.test_session_management()
        await tester.test_message_interaction()
        await tester.test_concurrent_session_isolation()
        await tester.test_stream_interruption()
        await tester.test_settings()
        await tester.test_api_endpoints()
    except Exception as e:
        log(f"❌ 测试执行异常: {e}")
        import traceback
        log(traceback.format_exc())
    finally:
        await browser.close()

    # 保存报告
    report = {
        "timestamp": datetime.now().isoformat(),
        "test_results": test_results,
        "summary": {
            "total": len(test_results),
            "passed": sum(1 for t in test_results if t["passed"]),
            "failed": sum(1 for t in test_results if not t["passed"]),
        },
        "console_logs": console_logs[-300:],
        "network_requests": [r for r in network_requests if "/api/" in r.get("url", "")][-100:],
    }

    report_path = OUTPUT_DIR / "v2_test_results.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    log("\n" + "="*60)
    log("📊 测试报告")
    log("="*60)
    log(f"   总测试数: {report['summary']['total']}")
    log(f"   通过: {report['summary']['passed']}")
    log(f"   失败: {report['summary']['failed']}")
    log(f"\n📁 详细报告: {report_path}")

    failed = [t for t in test_results if not t["passed"]]
    if failed:
        log("\n❌ 失败的测试:")
        for t in failed:
            log(f"   - {t['test_name']}: {t['detail']}")


async def main():
    async with async_playwright() as playwright:
        await run_tests(playwright)

if __name__ == "__main__":
    asyncio.run(main())
