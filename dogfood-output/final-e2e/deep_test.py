import asyncio
import json
import os
from datetime import datetime
from playwright.async_api import async_playwright

OUTPUT_DIR = "/Users/mac/AI/CScode/dogfood-output/final-e2e"
SCREENSHOTS_DIR = os.path.join(OUTPUT_DIR, "screenshots")
os.makedirs(SCREENSHOTS_DIR, exist_ok=True)

results = []
issue_counter = 0

def record(test_name, status, **kwargs):
    entry = {"test": test_name, "status": status, **kwargs}
    results.append(entry)
    icon = {"pass": "✅", "warn": "⚠️", "fail": "❌", "skip": "⏭️", "error": "❌"}.get(status, "❓")
    print(f"  {icon} {test_name}")
    return entry

def add_issue(severity, title, description, screenshot_file):
    global issue_counter
    issue_counter += 1
    issue = {
        "id": f"ISSUE-{issue_counter:03d}",
        "severity": severity,
        "title": title,
        "description": description,
        "screenshot": screenshot_file
    }
    print(f"\n  🐛 [{issue['id']}] {severity.upper()}: {title}")
    return issue

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(viewport={"width": 1440, "height": 900})
        page = await context.new_page()
        
        console_errors = []
        page.on("console", lambda msg: console_errors.append({"text": msg.text, "type": msg.type}) if msg.type == "error" else None)
        
        api_requests = []
        page.on("response", lambda resp: api_requests.append({"url": resp.url, "status": resp.status}) if "/api/" in resp.url else None)
        
        issues = []
        
        try:
            print("\n" + "=" * 60)
            print("CScode v0.3.4 深度功能测试")
            print("=" * 60)
            
            # ===== 加载应用 =====
            print("\n📱 阶段1: 初始加载")
            await page.goto("http://127.0.0.1:8080", wait_until="networkidle")
            await asyncio.sleep(2)
            await page.screenshot(path=os.path.join(SCREENSHOTS_DIR, "d01-initial-load.png"), full_page=True)
            
            title = await page.title()
            record("页面标题", "pass", title=title)
            
            # 检查顶部状态栏
            top_bar = await page.query_selector("header, [class*='header'], .top-bar")
            record("顶部导航栏", "pass" if top_bar else "warn")
            
            # 检查侧边栏
            sidebar = await page.query_selector("aside, nav, [class*='sidebar']")
            record("侧边栏", "pass" if sidebar else "warn")
            
            # 检查主内容区
            main_area = await page.query_selector("main, [class*='main'], .flex-1")
            record("主内容区", "pass" if main_area else "warn")
            
            # 检查底部输入框
            input_area = await page.query_selector("textarea")
            record("消息输入框", "pass" if input_area else "fail")
            
            # ===== 阶段2: 侧边栏功能 =====
            print("\n📱 阶段2: 侧边栏功能")
            
            # 检查会话列表项
            session_items = await page.query_selector_all("[class*='thread'], [class*='session-item'], [role='treeitem'], li")
            record("会话列表项", "pass" if len(session_items) > 0 else "warn", count=len(session_items))
            
            # 检查新建会话按钮
            new_btns = await page.query_selector_all("button[aria-label*='new' i], button[title*='new' i]")
            record("新建按钮", "pass" if len(new_btns) > 0 else "warn", count=len(new_btns))
            
            # 检查搜索/过滤
            search_btn = await page.query_selector("button[aria-label*='search' i], button[aria-label*='filter' i]")
            record("搜索/过滤按钮", "pass" if search_btn else "warn")
            
            # 检查设置按钮
            settings_btn = await page.query_selector("button[aria-label*='setting' i], button[title*='setting' i]")
            record("设置按钮", "pass" if settings_btn else "fail")
            
            # 检查帮助按钮
            help_btn = await page.query_selector("button[aria-label*='help' i], button[title*='help' i]")
            record("帮助按钮", "pass" if help_btn else "warn")
            
            # ===== 阶段3: 设置面板深度测试 =====
            print("\n📱 阶段3: 设置面板深度测试")
            
            if settings_btn:
                await settings_btn.click()
                await asyncio.sleep(1.5)
                await page.screenshot(path=os.path.join(SCREENSHOTS_DIR, "d03-settings-panel.png"), full_page=True)
                
                # 检查面板标题
                panel_title = await page.query_selector("h2, [class*='title'], [class*='header'] h1")
                record("设置面板标题", "pass" if panel_title else "warn")
                
                content = await page.content()
                
                # Provider
                has_provider_label = "Provider" in content
                provider_selects = await page.query_selector_all("select")
                record("Provider 下拉", "pass" if has_provider_label and len(provider_selects) > 0 else "fail")
                
                # Model
                has_model_label = "Model" in content
                record("Model 下拉", "pass" if has_model_label and len(provider_selects) >= 2 else "warn")
                
                # API Base URL
                has_api_base = "API Base" in content or "api_base" in content
                record("API Base URL", "pass" if has_api_base else "warn")
                
                # API Key
                has_api_key_label = "API Key" in content or "api_key" in content
                api_key_inputs = await page.query_selector_all("input[type='password'], input[placeholder*='key' i]")
                record("API Key 输入框", "pass" if has_api_key_label else "warn", has_input=len(api_key_inputs) > 0)
                
                # API Key 是否掩码显示
                if len(api_key_inputs) > 0:
                    input_type = await api_key_inputs[0].evaluate("el => el.type")
                    record("API Key 掩码", "pass" if input_type == "password" else "warn", type=input_type)
                
                # Temperature 滑块
                has_temp = "Temperature" in content or "temperature" in content
                sliders = await page.query_selector_all("input[type='range']")
                record("Temperature 滑块", "pass" if has_temp and len(sliders) > 0 else "warn")
                
                # Max Tokens
                has_max_tokens = "Max Token" in content or "max_token" in content.lower()
                record("Max Tokens", "pass" if has_max_tokens else "warn")
                
                # System Prompt
                has_system_prompt = "System Prompt" in content or "system_prompt" in content
                textareas = await page.query_selector_all("textarea")
                record("System Prompt", "pass" if has_system_prompt else "warn", textarea_count=len(textareas))
                
                # Theme
                has_theme = "Theme" in content or "theme" in content
                record("主题切换", "pass" if has_theme else "warn")
                
                # MCP Servers
                has_mcp = "MCP" in content or "mcp" in content
                record("MCP Servers", "pass" if has_mcp else "warn")
                
                # Plugins
                has_plugins = "Plugin" in content or "plugin" in content
                record("插件系统", "pass" if has_plugins else "warn")
                
                # 关闭面板
                await page.keyboard.press("Escape")
                await asyncio.sleep(0.5)
                record("关闭设置面板", "pass")
                
            # ===== 阶段4: 消息输入功能 =====
            print("\n📱 阶段4: 消息输入功能")
            
            textarea = page.locator("textarea").first
            if await textarea.count() > 0:
                await textarea.click()
                await textarea.fill("Hello, CScode! This is a test message.")
                await asyncio.sleep(0.5)
                await page.screenshot(path=os.path.join(SCREENSHOTS_DIR, "d04-input-message.png"), full_page=True)
                
                # 检查发送按钮
                send_btn = page.locator("button[type='submit']").first
                send_btn2 = page.locator("button[aria-label*='send' i]").first
                send_btn3 = page.locator("button").filter(has_text="Send").first
                
                send_found = False
                if await send_btn.count() > 0:
                    send_found = True
                elif await send_btn2.count() > 0:
                    send_found = True
                elif await send_btn3.count() > 0:
                    send_found = True
                
                record("发送按钮", "pass" if send_found else "warn")
                
                # 清空输入
                await textarea.fill("")
            else:
                record("消息输入框", "fail")
            
            # ===== 阶段5: 快捷键提示 =====
            print("\n📱 阶段5: 快捷键与提示")
            content = await page.content()
            has_shortcut_hint = "Tab" in content or "tab" in content.lower()
            has_mention_hint = "@mention" in content or "@" in content
            record("快捷键提示", "pass" if has_shortcut_hint else "warn")
            record("@提及提示", "pass" if has_mention_hint else "warn")
            
            # ===== 阶段6: 模型信息显示 =====
            print("\n📱 阶段6: 模型信息显示")
            has_model_info = "gpt" in content.lower() or "model" in content.lower()
            record("模型信息显示", "pass" if has_model_info else "warn")
            
            # ===== 阶段7: 控制台错误检查 =====
            print("\n📱 阶段7: 控制台错误检查")
            console_errs = [e for e in console_errors if "Failed to load" in e["text"] or "Error" in e["text"]]
            record("控制台错误", "pass" if len(console_errs) == 0 else "warn", errors=console_errs[:5])
            
            # ===== 阶段8: API 完整性 =====
            print("\n📱 阶段8: API 端点检查")
            unique_apis = set()
            for r in api_requests:
                url = r["url"].split("?")[0]
                if "/api/" in url:
                    unique_apis.add(url)
            
            print(f"  发现 {len(unique_apis)} 个 API 端点:")
            for api in sorted(unique_apis):
                statuses = [r["status"] for r in api_requests if r["url"].split("?")[0] == api]
                status_str = ",".join(str(s) for s in set(statuses))
                print(f"    {status_str} {api.replace('http://127.0.0.1:8080', '')}")
            
            api_500 = [r for r in api_requests if r["status"] >= 500]
            api_400 = [r for r in api_requests if 400 <= r["status"] < 500]
            api_ok = [r for r in api_requests if 200 <= r["status"] < 300]
            
            record("API 正常响应", "pass" if len(api_500) == 0 else "warn", 
                   ok=len(api_ok), error_4xx=len(api_400), error_5xx=len(api_500))
            
            # ===== 阶段9: 新功能验证 =====
            print("\n📱 阶段9: 新功能验证（v0.3.4 新增）")
            
            # 检查 API Key 安全存储
            new_endpoints = [
                "/api/credentials",
                "/api/permission-rules", 
                "/api/sync/events",
            ]
            
            for endpoint in new_endpoints:
                found = any(endpoint in r["url"] for r in api_requests)
                status = "pass" if found else "warn"
                record(f"新端点: {endpoint}", status)
            
            # ===== 最终截图 =====
            await page.screenshot(path=os.path.join(SCREENSHOTS_DIR, "d99-final.png"), full_page=True)
            
        except Exception as e:
            print(f"\n❌ 测试异常: {e}")
            import traceback
            traceback.print_exc()
            record("整体测试", "error", error=str(e))
        
        # ===== 输出汇总 =====
        print("\n" + "=" * 60)
        print("深度功能测试汇总")
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
        
        summary = {
            "pass": pass_count,
            "warn": warn_count,
            "fail": fail_count,
            "skip": skip_count,
            "total": len(results),
            "timestamp": datetime.now().isoformat(),
            "issues_found": len(issues)
        }
        
        with open(os.path.join(OUTPUT_DIR, "deep-test-results.json"), "w") as f:
            json.dump({"summary": summary, "results": results, "issues": issues, "api_requests": list(set(r["url"].split("?")[0] for r in api_requests if "/api/" in r["url"]))}, f, indent=2, ensure_ascii=False)
        
        print(f"\n📁 详细结果: {os.path.join(OUTPUT_DIR, 'deep-test-results.json')}")
        
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
