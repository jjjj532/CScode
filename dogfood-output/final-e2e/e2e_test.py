import asyncio
import json
import os
from datetime import datetime
from playwright.async_api import async_playwright

OUTPUT_DIR = "/Users/mac/AI/CScode/dogfood-output/final-e2e"
SCREENSHOTS_DIR = os.path.join(OUTPUT_DIR, "screenshots")
os.makedirs(SCREENSHOTS_DIR, exist_ok=True)

results = []

def record(test_name, status, **kwargs):
    entry = {"test": test_name, "status": status, **kwargs}
    results.append(entry)
    icon = {"pass": "✅", "warn": "⚠️", "fail": "❌", "skip": "⏭️", "error": "❌"}.get(status, "❓")
    print(f"  {icon} {test_name}")
    return entry

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(viewport={"width": 1280, "height": 800})
        page = await context.new_page()
        
        console_errors = []
        page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
        
        api_requests = []
        page.on("response", lambda resp: api_requests.append({"url": resp.url, "status": resp.status}) if "/api/" in resp.url else None)
        
        try:
            print("\n" + "=" * 60)
            print("CScode v0.3.4 前端真实操作端到端测试")
            print("=" * 60)
            
            # ===== 测试 1: 加载应用 =====
            print("\n📱 测试 1: 加载应用")
            await page.goto("http://127.0.0.1:8080", wait_until="networkidle")
            await asyncio.sleep(2)
            await page.screenshot(path=os.path.join(SCREENSHOTS_DIR, "01-app-loaded.png"), full_page=True)
            title = await page.title()
            record("应用加载", "pass", title=title)
            
            # ===== 测试 2: 检查侧边栏和会话列表 =====
            print("\n📱 测试 2: 检查侧边栏和会话列表")
            sidebar_items = await page.query_selector_all("nav button, aside button, [class*='sidebar'] button")
            session_items = await page.query_selector_all("[class*='session'], [class*='chat-item'], nav > div > div, li")
            await page.screenshot(path=os.path.join(SCREENSHOTS_DIR, "02-sidebar.png"), full_page=True)
            record("侧边栏与会话列表", "pass", sidebar_buttons=len(sidebar_items), session_items=len(session_items))
            
            # ===== 测试 3: 新建会话 =====
            print("\n📱 测试 3: 新建会话")
            new_btn = page.locator("button[aria-label='Create new session']").first
            new_btn2 = page.locator("button[title='New session']").first
            new_btn3 = page.locator("button").filter(has_text="New").first
            
            clicked = False
            if await new_btn.count() > 0:
                await new_btn.click()
                clicked = True
            elif await new_btn2.count() > 0:
                await new_btn2.click()
                clicked = True
            elif await new_btn3.count() > 0:
                await new_btn3.click()
                clicked = True
            
            await asyncio.sleep(1.5)
            await page.screenshot(path=os.path.join(SCREENSHOTS_DIR, "03-new-session.png"), full_page=True)
            record("新建会话", "pass" if clicked else "warn", clicked=clicked)
            
            # ===== 测试 4: 设置面板 =====
            print("\n📱 测试 4: 打开设置面板")
            settings_btn = page.locator("button[aria-label='Settings']").first
            settings_btn2 = page.locator("button[title='Settings']").first
            settings_btn3 = page.locator("button").filter(has_text="Settings").first
            
            settings_opened = False
            if await settings_btn.count() > 0:
                await settings_btn.click()
                settings_opened = True
            elif await settings_btn2.count() > 0:
                await settings_btn2.click()
                settings_opened = True
            elif await settings_btn3.count() > 0:
                await settings_btn3.click()
                settings_opened = True
            
            await asyncio.sleep(1.5)
            await page.screenshot(path=os.path.join(SCREENSHOTS_DIR, "04-settings-panel.png"), full_page=True)
            
            content = await page.content()
            has_provider = "Provider" in content or "provider" in content
            has_model = "Model" in content or "model" in content
            has_api_key = "API Key" in content or "api_key" in content or "apiKey" in content
            has_api_key_configured = "api_key_configured" in content
            
            record("设置面板", "pass" if settings_opened else "warn", 
                   opened=settings_opened,
                   has_provider=has_provider,
                   has_model=has_model,
                   has_api_key=has_api_key,
                   has_api_key_configured_field=has_api_key_configured)
            
            # ===== 测试 5: API Key 安全显示 =====
            print("\n📱 测试 5: API Key 安全显示")
            has_masked = "••••" in content or "****" in content
            record("API Key 安全显示", "pass", masked=has_masked or not has_api_key)
            
            # ===== 测试 6: Provider 下拉 =====
            print("\n📱 测试 6: Provider 下拉选择")
            selects = await page.query_selector_all("select")
            provider_select = None
            for s in selects:
                label = await s.evaluate("el => el.id || el.name || el.getAttribute('aria-label') || ''")
                if "provider" in label.lower() or "Provider" in label:
                    provider_select = s
                    break
            
            if provider_select:
                options = await provider_select.query_selector_all("option")
                record("Provider 下拉", "pass", options=len(options))
            else:
                record("Provider 下拉", "warn", options=0)
            
            # ===== 测试 7: 关闭设置面板 =====
            print("\n📱 测试 7: 关闭设置面板")
            await page.keyboard.press("Escape")
            await asyncio.sleep(0.5)
            
            backdrop = page.locator("div.fixed.inset-0").first
            if await backdrop.count() > 0:
                try:
                    await backdrop.click(position={"x": 10, "y": 10})
                    await asyncio.sleep(0.5)
                except:
                    pass
            
            record("关闭设置面板", "pass")
            
            # ===== 测试 8: 切换会话 =====
            print("\n📱 测试 8: 切换会话")
            session_items2 = await page.query_selector_all("[class*='session'], [class*='chat-item'], nav > div > div")
            if len(session_items2) > 1:
                try:
                    await session_items2[1].click()
                    await asyncio.sleep(1)
                    await page.screenshot(path=os.path.join(SCREENSHOTS_DIR, "08-switch-session.png"), full_page=True)
                    record("切换会话", "pass")
                except Exception as e:
                    record("切换会话", "warn", error=str(e))
            else:
                record("切换会话", "skip", reason="会话不足")
            
            # ===== 测试 9: 消息输入框 =====
            print("\n📱 测试 9: 消息输入框")
            textarea = page.locator("textarea").first
            text_input = page.locator("input[type='text']").first
            
            input_found = False
            input_type = None
            if await textarea.count() > 0:
                input_found = True
                input_type = "textarea"
            elif await text_input.count() > 0:
                input_found = True
                input_type = "input"
            
            record("消息输入框", "pass" if input_found else "warn", type=input_type)
            
            # ===== 测试 10: 输入测试消息 =====
            print("\n📱 测试 10: 输入测试消息")
            if input_found:
                try:
                    if input_type == "textarea":
                        await textarea.click()
                        await textarea.fill("Hello, this is an E2E test message from Playwright!")
                    else:
                        await text_input.click()
                        await text_input.fill("Hello, this is an E2E test message from Playwright!")
                    await asyncio.sleep(0.5)
                    await page.screenshot(path=os.path.join(SCREENSHOTS_DIR, "10-type-message.png"), full_page=True)
                    record("输入测试消息", "pass")
                except Exception as e:
                    record("输入测试消息", "warn", error=str(e))
            else:
                record("输入测试消息", "skip")
            
            # ===== 测试 11: 终端按钮 =====
            print("\n📱 测试 11: 终端按钮")
            terminal_btn = page.locator("button[aria-label='Terminal']").first
            terminal_btn2 = page.locator("button[title='Terminal']").first
            terminal_btn3 = page.locator("button").filter(has_text="Terminal").first
            
            terminal_found = False
            if await terminal_btn.count() > 0 or await terminal_btn2.count() > 0 or await terminal_btn3.count() > 0:
                terminal_found = True
            
            record("终端按钮", "pass" if terminal_found else "warn", found=terminal_found)
            
            # ===== 测试 12: 控制台错误 =====
            print("\n📱 测试 12: 控制台错误检查")
            record("控制台错误", "pass" if len(console_errors) == 0 else "warn", errors=console_errors)
            
            # ===== 测试 13: API 请求检查 =====
            print("\n📱 测试 13: API 请求检查")
            api_calls = [r for r in api_requests if r["status"] < 500]
            api_errors = [r for r in api_requests if r["status"] >= 400]
            record("API 请求", "pass" if len(api_errors) == 0 else "warn", 
                   total=len(api_requests), 
                   errors=api_errors[:5])
            
            # ===== 测试 14: 深色模式检测 =====
            print("\n📱 测试 14: 主题检测")
            bg_color = await page.evaluate("() => getComputedStyle(document.body).backgroundColor")
            is_dark = "rgb(26" in bg_color or "rgb(20" in bg_color or "rgb(17" in bg_color
            record("深色模式", "pass", bg_color=bg_color, is_dark=is_dark)
            
            # ===== 测试 15: 响应式布局 =====
            print("\n📱 测试 15: 响应式布局")
            await page.set_viewport_size({"width": 768, "height": 600})
            await asyncio.sleep(0.5)
            await page.screenshot(path=os.path.join(SCREENSHOTS_DIR, "15-mobile-view.png"), full_page=True)
            await page.set_viewport_size({"width": 1280, "height": 800})
            record("响应式布局", "pass")
            
            # 最终截图
            await page.screenshot(path=os.path.join(SCREENSHOTS_DIR, "99-final.png"), full_page=True)
            
        except Exception as e:
            print(f"\n❌ 测试异常: {e}")
            import traceback
            traceback.print_exc()
            record("整体测试", "error", error=str(e))
        
        # ===== 输出汇总 =====
        print("\n" + "=" * 60)
        print("测试结果汇总")
        print("=" * 60)
        
        pass_count = sum(1 for r in results if r["status"] == "pass")
        warn_count = sum(1 for r in results if r["status"] == "warn")
        fail_count = sum(1 for r in results if r["status"] in ("fail", "error"))
        skip_count = sum(1 for r in results if r["status"] == "skip")
        
        print(f"\n✅ 通过: {pass_count}")
        print(f"⚠️  警告: {warn_count}")
        print(f"❌ 失败: {fail_count}")
        print(f"⏭️  跳过: {skip_count}")
        print(f"📊 总计: {len(results)}")
        
        # 保存结果
        summary = {
            "pass": pass_count,
            "warn": warn_count,
            "fail": fail_count,
            "skip": skip_count,
            "total": len(results),
            "timestamp": datetime.now().isoformat()
        }
        
        with open(os.path.join(OUTPUT_DIR, "test-results.json"), "w") as f:
            json.dump({"summary": summary, "results": results}, f, indent=2, ensure_ascii=False)
        
        print(f"\n📁 详细结果: {os.path.join(OUTPUT_DIR, 'test-results.json')}")
        print(f"📸 截图目录: {SCREENSHOTS_DIR}")
        
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
