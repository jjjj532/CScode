import asyncio
import json
import os
from datetime import datetime
from playwright.async_api import async_playwright, Page

SCREENSHOT_DIR = "/Users/mac/AI/CScode/dogfood-output/screenshots"
os.makedirs(SCREENSHOT_DIR, exist_ok=True)

issues = []
network_errors = []

def log(msg: str):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

def add_issue(severity: str, title: str, description: str, repro: str = ""):
    issue = {
        "id": f"ISSUE-{len(issues)+1:03d}",
        "severity": severity,
        "title": title,
        "description": description,
        "repro": repro,
    }
    issues.append(issue)
    log(f"  ⚠️  [{severity}] {title}")

async def take_screenshot(page: Page, name: str):
    path = os.path.join(SCREENSHOT_DIR, f"{name}.png")
    await page.screenshot(path=path, full_page=True)
    log(f"  📸 {name}.png")

async def get_toast_text(page: Page) -> str:
    try:
        body = await page.inner_text("body")
        for line in body.split("\n"):
            line = line.strip()
            if line and ("Failed" in line or "错误" in line or "失败" in line or "Error" in line or "success" in line.lower() or "成功" in line):
                if len(line) < 100:
                    return line
    except:
        pass
    return ""

async def test_1_sidebar(page: Page):
    log("\n=== 测试 1: 侧边栏基本功能 ===")
    
    await page.goto("http://localhost:8000/")
    await page.wait_for_load_state("networkidle")
    await take_screenshot(page, "01-home")
    
    # 打开侧边栏
    menu_btn = page.get_by_role("button", name="Toggle menu")
    if await menu_btn.is_visible():
        await menu_btn.click()
        await page.wait_for_timeout(500)
    
    await take_screenshot(page, "02-sidebar-open")
    
    # 检查所有按钮 (用 first 避免 strict mode 问题)
    checks = [
        ("Filter threads", "过滤按钮"),
        ("Sort threads", "排序按钮"),
        ("Refresh sessions", "刷新按钮"),
        ("Create new session", "新建会话按钮"),
    ]
    
    for name, desc in checks:
        try:
            el = page.get_by_role("button", name=name).first
            visible = await el.is_visible()
            log(f"  {'✅' if visible else '❌'} {desc}")
            if not visible:
                add_issue("P2", f"缺少{desc}", f"按钮 '{name}' 不可见")
        except Exception as e:
            log(f"  ❌ {desc}: {e}")
    
    # 测试新建会话
    log("  测试新建会话...")
    new_btn = page.get_by_role("button", name="Create new session").first
    await new_btn.click()
    await page.wait_for_timeout(1000)
    await take_screenshot(page, "03-new-session")
    toast = await get_toast_text(page)
    if toast and ("Fail" in toast or "错误" in toast):
        add_issue("P1", "新建会话失败", toast)
    
    return True

async def test_2_export_delete(page: Page):
    log("\n=== 测试 2: 会话 hover 按钮 (export/delete) ===")
    
    # 找到中文会话
    all_btns = await page.query_selector_all("button")
    chinese_btn = None
    for btn in all_btns:
        try:
            txt = await btn.inner_text()
            if any('\u4e00' <= c <= '\u9fff' for c in txt) and 1 < len(txt.strip()) < 50:
                chinese_btn = btn
                log(f"  中文会话: {txt.strip()[:30]}")
                break
        except:
            continue
    
    if not chinese_btn:
        log("  ⚠️ 未找到中文会话，跳过 export 测试")
        return True
    
    # 找父容器并 hover
    parent = await chinese_btn.evaluate_handle("el => el.closest('[class*=group]') || el.parentElement")
    parent_el = parent.as_element()
    if not parent_el:
        log("  ⚠️ 找不到父容器")
        return True
    
    await parent_el.hover()
    await page.wait_for_timeout(500)
    
    # 找 export 按钮
    download_btn = None
    child_btns = await parent_el.query_selector_all("button")
    for cb in child_btns:
        aria = await cb.get_attribute("aria-label") or ""
        cls = await cb.get_attribute("class") or ""
        if "download" in aria.lower() or "export" in aria.lower() or "download" in cls.lower():
            download_btn = cb
            break
    
    if not download_btn:
        # 用 lucide-download SVG 找
        dl_icon = await parent_el.query_selector(".lucide-download")
        if dl_icon:
            download_btn = await dl_icon.evaluate_handle("el => el.closest('button')")
            download_btn = download_btn.as_element()
    
    log(f"  Export 按钮: {'找到' if download_btn else '未找到'}")
    
    if download_btn:
        log("  点击 Export...")
        try:
            await download_btn.click()
            await page.wait_for_timeout(2000)
            await take_screenshot(page, "04-after-export")
            
            toast = await get_toast_text(page)
            log(f"  Toast: {toast}")
            
            if "Fail" in toast or "失败" in toast:
                add_issue("P1", "导出会话失败", toast,
                          "1. 打开侧边栏\n2. hover 到中文标题会话\n3. 点击 export 按钮")
            elif "success" in toast.lower() or "成功" in toast:
                log("  ✅ 导出成功")
        except Exception as e:
            log(f"  Export 点击异常: {e}")
    
    return True

async def test_3_chat_main(page: Page):
    log("\n=== 测试 3: 聊天主界面 ===")
    
    await page.goto("http://localhost:8000/")
    await page.wait_for_load_state("networkidle")
    
    # Plan/Build 切换
    log("  Plan/Build 切换...")
    plan = page.get_by_role("radio", name="Plan")
    build = page.get_by_role("radio", name="Build")
    await plan.click()
    await page.wait_for_timeout(200)
    plan_ok = await plan.is_checked()
    await build.click()
    await page.wait_for_timeout(200)
    build_ok = await build.is_checked()
    log(f"  Plan={plan_ok} Build={build_ok}")
    if not (plan_ok and build_ok):
        add_issue("P2", "Plan/Build 切换异常", f"Plan={plan_ok} Build={build_ok}")
    
    # 输入框 + 发送按钮
    log("  输入框测试...")
    textbox = page.get_by_role("textbox", name="Ask anything or @mention a file...")
    await textbox.fill("测试消息：hello world")
    await page.wait_for_timeout(200)
    send_btn = page.get_by_role("button", name="Send message")
    send_enabled = not await send_btn.is_disabled()
    log(f"  发送按钮可用: {send_enabled}")
    if not send_enabled:
        add_issue("P2", "输入后发送按钮不可用", "输入文字后 Send message 仍 disabled")
    
    await take_screenshot(page, "05-chat-input")
    
    # Attach file 按钮
    log("  Attach file 按钮...")
    attach_btn = page.get_by_role("button", name="Attach file")
    if await attach_btn.is_visible():
        await attach_btn.click()
        await page.wait_for_timeout(500)
        await take_screenshot(page, "06-attach-file")
    
    # Open terminal 按钮
    log("  Open terminal 按钮...")
    term_btn = page.get_by_role("button", name="Open terminal")
    if await term_btn.is_visible():
        await term_btn.click()
        await page.wait_for_timeout(1500)
        await take_screenshot(page, "07-terminal")
        
        # 检查终端是否出现
        body = await page.inner_text("body")
        has_terminal = "terminal" in body.lower() or "xterm" in body.lower()
        log(f"  终端内容: {'有' if has_terminal else '无'}")
    
    return True

async def test_4_settings(page: Page):
    log("\n=== 测试 4: 设置页面 ===")
    
    await page.goto("http://localhost:8000/")
    await page.wait_for_load_state("networkidle")
    
    menu_btn = page.get_by_role("button", name="Toggle menu")
    if await menu_btn.is_visible():
        await menu_btn.click()
        await page.wait_for_timeout(500)
    
    # 用 aria-label 精确找 Settings
    settings_btn = page.locator("button[aria-label='Settings']")
    if await settings_btn.count() == 0:
        settings_btn = page.get_by_role("button", name="Settings").last
    
    if await settings_btn.is_visible():
        log("  打开设置页面...")
        await settings_btn.click()
        await page.wait_for_timeout(2000)
        await page.wait_for_load_state("networkidle")
        await take_screenshot(page, "08-settings")
        
        body = await page.inner_text("body")
        keywords = ["API Key", "Model", "Provider", "Save"]
        found = [k for k in keywords if k in body]
        log(f"  设置项: {found}")
        
        # 测试保存
        save_btns = await page.query_selector_all("button")
        save_btn = None
        for btn in save_btns:
            txt = await btn.inner_text()
            if "Save" in txt:
                save_btn = btn
                break
        
        if save_btn:
            log("  点击保存...")
            await save_btn.click()
            await page.wait_for_timeout(1500)
            await take_screenshot(page, "09-after-save")
            
            toast = await get_toast_text(page)
            if toast and ("Fail" in toast or "错误" in toast):
                add_issue("P2", "保存设置失败", toast)
            elif toast:
                log(f"  保存结果: {toast}")
    else:
        add_issue("P2", "找不到 Settings 按钮", "")
    
    return True

async def test_5_help(page: Page):
    log("\n=== 测试 5: 帮助页面 ===")
    
    await page.goto("http://localhost:8000/")
    await page.wait_for_load_state("networkidle")
    
    menu_btn = page.get_by_role("button", name="Toggle menu")
    if await menu_btn.is_visible():
        await menu_btn.click()
        await page.wait_for_timeout(500)
    
    help_btn = page.locator("button[aria-label='Help']")
    if await help_btn.count() == 0:
        log("  ⚠️ 找不到 Help 按钮 (aria-label)")
        return True
    
    log("  打开帮助页面...")
    await help_btn.first.click()
    await page.wait_for_timeout(2000)
    await page.wait_for_load_state("networkidle")
    await take_screenshot(page, "10-help")
    
    body = await page.inner_text("body")
    log(f"  帮助页文字长度: {len(body)}")
    
    return True

async def test_6_filter_sort_refresh(page: Page):
    log("\n=== 测试 6: 过滤/排序/刷新 ===")
    
    await page.goto("http://localhost:8000/")
    await page.wait_for_load_state("networkidle")
    
    menu_btn = page.get_by_role("button", name="Toggle menu")
    if await menu_btn.is_visible():
        await menu_btn.click()
        await page.wait_for_timeout(500)
    
    for btn_name, desc in [
        ("Filter threads", "Filter"),
        ("Sort threads", "Sort"),
        ("Refresh sessions", "Refresh"),
    ]:
        btn = page.get_by_role("button", name=btn_name).first
        if await btn.is_visible():
            log(f"  点击 {desc}...")
            try:
                await btn.click()
                await page.wait_for_timeout(800)
            except Exception as e:
                log(f"  {desc} 点击异常: {e}")
    
    await take_screenshot(page, "11-filter-sort-refresh")
    return True

async def test_7_concurrent(page: Page):
    log("\n=== 测试 7: 多会话创建与切换 ===")
    
    await page.goto("http://localhost:8000/")
    await page.wait_for_load_state("networkidle")
    
    menu_btn = page.get_by_role("button", name="Toggle menu")
    if await menu_btn.is_visible():
        await menu_btn.click()
        await page.wait_for_timeout(500)
    
    new_btn = page.get_by_role("button", name="Create new session").first
    
    # 创建 3 个会话
    for i in range(3):
        log(f"  创建会话 {i+1}...")
        await new_btn.click()
        await page.wait_for_timeout(600)
    
    await take_screenshot(page, "12-multi-sessions")
    
    # 数 New Session 数量
    all_btns = await page.query_selector_all("button")
    new_count = 0
    for b in all_btns:
        txt = await b.inner_text() or ""
        if "New Session" in txt:
            new_count += 1
    log(f"  New Session 数量: {new_count}")
    
    return True

async def test_8_keyboard_shortcuts(page: Page):
    log("\n=== 测试 8: 键盘快捷键 ===")
    
    await page.goto("http://localhost:8000/")
    await page.wait_for_load_state("networkidle")
    
    # 测试 Escape 关闭侧边栏
    log("  测试 ESC 关闭侧边栏...")
    menu_btn = page.get_by_role("button", name="Close menu")
    sidebar_open = await menu_btn.is_visible() if await menu_btn.count() > 0 else False
    
    if sidebar_open:
        await page.keyboard.press("Escape")
        await page.wait_for_timeout(300)
        closed = not await page.get_by_role("button", name="Close menu").is_visible()
        log(f"  ESC 关闭侧边栏: {'成功' if closed else '失败'}")
    
    # 测试 Enter 发送
    log("  测试 Ctrl+Enter/Enter...")
    textbox = page.get_by_role("textbox", name="Ask anything or @mention a file...")
    await textbox.click()
    await textbox.fill("测试快捷键")
    await page.keyboard.press("Enter")
    await page.wait_for_timeout(500)
    
    await take_screenshot(page, "13-keyboard-test")
    return True

async def test_9_share_button(page: Page):
    log("\n=== 测试 9: Share 按钮 ===")
    
    await page.goto("http://localhost:8000/")
    await page.wait_for_load_state("networkidle")
    
    menu_btn = page.get_by_role("button", name="Toggle menu")
    if await menu_btn.is_visible():
        await menu_btn.click()
        await page.wait_for_timeout(500)
    
    # 找 Share 图标按钮
    share_btn = page.locator("button[aria-label='Share']")
    if await share_btn.count() == 0:
        # 试试其他选择器
        all_btns = await page.query_selector_all("button")
        for btn in all_btns:
            aria = await btn.get_attribute("aria-label") or ""
            if "share" in aria.lower():
                share_btn = page.locator(f"button[aria-label='{aria}']")
                break
    
    if await share_btn.count() > 0 and await share_btn.first.is_visible():
        log("  点击 Share 按钮...")
        try:
            await share_btn.first.click()
            await page.wait_for_timeout(1500)
            await take_screenshot(page, "14-share-dialog")
            
            body = await page.inner_text("body")
            has_share = "share" in body.lower() or "共享" in body or "分享" in body
            log(f"  分享对话框: {'出现' if has_share else '未出现'}")
        except Exception as e:
            log(f"  Share 点击异常: {e}")
    else:
        log("  ⚠️ 未找到 Share 按钮")
    
    return True

async def test_10_session_delete(page: Page):
    log("\n=== 测试 10: 会话删除按钮 ===")
    
    await page.goto("http://localhost:8000/")
    await page.wait_for_load_state("networkidle")
    
    menu_btn = page.get_by_role("button", name="Toggle menu")
    if await menu_btn.is_visible():
        await menu_btn.click()
        await page.wait_for_timeout(500)
    
    # 找一个 New Session 来测试删除
    all_btns = await page.query_selector_all("button")
    target_btn = None
    for btn in all_btns:
        txt = await btn.inner_text() or ""
        if txt.strip() == "New Session":
            target_btn = btn
            break
    
    if not target_btn:
        log("  ⚠️ 未找到可删除的会话")
        return True
    
    parent = await target_btn.evaluate_handle("el => el.closest('[class*=group]') || el.parentElement")
    parent_el = parent.as_element()
    if not parent_el:
        return True
    
    await parent_el.hover()
    await page.wait_for_timeout(500)
    
    # 找删除按钮
    delete_btn = None
    dl_icon = await parent_el.query_selector(".lucide-trash-2, .lucide-x")
    if dl_icon:
        delete_handle = await dl_icon.evaluate_handle("el => el.closest('button')")
        delete_btn = delete_handle.as_element()
    
    log(f"  Delete 按钮: {'找到' if delete_btn else '未找到'}")
    
    if delete_btn:
        log("  点击 Delete (不确认)...")
        try:
            await delete_btn.click()
            await page.wait_for_timeout(1000)
            await take_screenshot(page, "15-delete-clicked")
        except Exception as e:
            log(f"  Delete 点击异常: {e}")
    
    return True

async def test_11_workspace_switch(page: Page):
    log("\n=== 测试 11: 工作区切换 ===")
    
    await page.goto("http://localhost:8000/")
    await page.wait_for_load_state("networkidle")
    
    menu_btn = page.get_by_role("button", name="Toggle menu")
    if await menu_btn.is_visible():
        await menu_btn.click()
        await page.wait_for_timeout(500)
    
    # 找工作区选择器 (顶部项目名)
    workspace_btn = page.locator("button[aria-label='AI-CScode']")
    if await workspace_btn.count() == 0:
        # 试试第一个带 Chevron 的
        all_btns = await page.query_selector_all("button")
        for btn in all_btns:
            txt = await btn.inner_text() or ""
            if "AI-CScode" in txt or "CScode" in txt:
                workspace_btn = page.locator(f"button:nth-of-type({all_btns.index(btn)+1})")
                break
    
    if await workspace_btn.count() > 0:
        log("  点击工作区...")
        try:
            await workspace_btn.first.click()
            await page.wait_for_timeout(1000)
            await take_screenshot(page, "16-workspace-menu")
        except Exception as e:
            log(f"  工作区点击异常: {e}")
    
    return True

async def main():
    log("🚀 开始 CScode 全面 GUI 测试...")
    log(f"📸 截图目录: {SCREENSHOT_DIR}")
    
    console_errors = []
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": 1440, "height": 900},
            locale="zh-CN",
        )
        
        page = await context.new_page()
        
        # 捕获网络错误
        page.on("response", lambda res: network_errors.append(f"{res.status} {res.url}") if res.status >= 400 else None)
        page.on("console", lambda msg: console_errors.append(f"[{msg.type}] {msg.text}") if msg.type == "error" else None)
        page.on("pageerror", lambda err: console_errors.append(f"[pageerror] {err.message}"))
        
        tests = [
            test_1_sidebar,
            test_2_export_delete,
            test_3_chat_main,
            test_4_settings,
            test_5_help,
            test_6_filter_sort_refresh,
            test_7_concurrent,
            test_8_keyboard_shortcuts,
            test_9_share_button,
            test_10_session_delete,
            test_11_workspace_switch,
        ]
        
        passed = 0
        for test in tests:
            try:
                await test(page)
                passed += 1
            except Exception as e:
                log(f"  ❌ {test.__name__} 异常: {e}")
                add_issue("P2", f"{test.__name__} 执行异常", str(e))
        
        await browser.close()
    
    # 报告
    log(f"\n{'='*60}")
    log(f"📊 测试完成: {passed}/{len(tests)} 个测试用例执行")
    log(f"   发现 {len(issues)} 个问题")
    log(f"{'='*60}")
    
    sev_count = {"P0": 0, "P1": 0, "P2": 0, "P3": 0}
    for issue in issues:
        sev_count[issue["severity"]] = sev_count.get(issue["severity"], 0) + 1
    
    for sev in ["P0", "P1", "P2", "P3"]:
        if sev_count.get(sev, 0) > 0:
            log(f"  {sev}: {sev_count[sev]} 个")
    
    if issues:
        log("\n📋 问题列表:")
        for issue in issues:
            log(f"  [{issue['id']}] [{issue['severity']}] {issue['title']}")
    
    if network_errors:
        log(f"\n🌐 网络错误 ({len(network_errors)}):")
        for err in network_errors[:10]:
            log(f"  - {err[:100]}")
    
    if console_errors:
        log(f"\n⚠️  控制台错误 ({len(console_errors)}):")
        for err in console_errors[:10]:
            log(f"  - {err[:120]}")
    
    report = {
        "timestamp": datetime.now().isoformat(),
        "tests_run": passed,
        "total_tests": len(tests),
        "total_issues": len(issues),
        "severity_count": sev_count,
        "issues": issues,
        "network_errors": network_errors,
        "console_errors": console_errors,
    }
    
    report_path = "/Users/mac/AI/CScode/dogfood-output/test-results.json"
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    
    log(f"\n📁 报告: {report_path}")

if __name__ == "__main__":
    asyncio.run(main())
