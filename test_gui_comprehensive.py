"""CScode GUI Comprehensive Test - Round 3"""
from playwright.sync_api import sync_playwright
import json

def test_gui():
    errors = []
    warnings = []
    api_calls = []
    screenshots = []
    console_logs = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 720})

        # Track console logs
        page.on("console", lambda msg: console_logs.append({"type": msg.type, "text": msg.text}))
        # Track network
        page.on("request", lambda req: api_calls.append({"url": req.url, "method": req.method, "status": None}))
        page.on("response", lambda res: None)  # We'll track status separately

        try:
            # === Test 1: Initial Load ===
            print("="*60)
            print("Test 1: Initial Page Load")
            page.goto("http://localhost:5173")
            page.wait_for_load_state("networkidle")
            page.screenshot(path="/tmp/round3_01_initial.png", full_page=True)
            screenshots.append("/tmp/round3_01_initial.png")
            print(f"Title: {page.title()}")

            # Wait a bit for API calls to complete
            page.wait_for_timeout(2000)

            # Check console for errors
            error_logs = [l for l in console_logs if l["type"] == "error"]
            print(f"Console errors after load: {len(error_logs)}")
            for log in error_logs[:5]:
                print(f"  ERROR: {log['text'][:150]}")

            # === Test 2: Check Sidebar ===
            print("\n" + "="*60)
            print("Test 2: Sidebar Elements")
            sidebar = page.locator("aside, [role='navigation'], .sidebar")
            if sidebar.count() > 0:
                print("Sidebar found")
                # Find all buttons in sidebar
                sidebar_buttons = sidebar.locator("button").all()
                print(f"Buttons in sidebar: {len(sidebar_buttons)}")
                for i, btn in enumerate(sidebar_buttons[:10]):
                    text = btn.inner_text().strip()[:50]
                    aria = btn.get_attribute("aria-label") or ""
                    print(f"  [{i}] text='{text}' aria-label='{aria}'")
            else:
                errors.append("Sidebar not found")

            # === Test 3: New Chat Button ===
            print("\n" + "="*60)
            print("Test 3: New Chat Button")
            new_chat_btn = None
            # Try different selectors
            selectors = [
                "button:has-text('New')",
                "button:has-text('新')",
                "[aria-label*='new' i]",
                "[aria-label*='chat' i]",
            ]
            for sel in selectors:
                btns = page.locator(sel).all()
                if btns:
                    new_chat_btn = btns[0]
                    print(f"Found new chat button: {sel}")
                    break

            if new_chat_btn:
                try:
                    new_chat_btn.click()
                    page.wait_for_timeout(1000)
                    page.screenshot(path="/tmp/round3_03_new_chat.png")
                    screenshots.append("/tmp/round3_03_new_chat.png")
                    print("Clicked new chat button")
                except Exception as e:
                    errors.append(f"Failed to click new chat: {e}")
            else:
                errors.append("New chat button not found")

            # === Test 4: Input Box ===
            print("\n" + "="*60)
            print("Test 4: Input Box")
            input_box = None
            input_selectors = ["textarea", "input[type='text']", "[contenteditable='true']"]
            for sel in input_selectors:
                inputs = page.locator(sel).all()
                if inputs:
                    input_box = inputs[0]
                    print(f"Input found: {sel}")
                    break

            if input_box:
                try:
                    input_box.fill("Hello, please introduce yourself in one sentence")
                    print("Typed message in input")
                except Exception as e:
                    errors.append(f"Failed to type: {e}")
            else:
                errors.append("Input box not found")

            # === Test 5: Send Button ===
            print("\n" + "="*60)
            print("Test 5: Send Button")
            send_btn = None
            send_selectors = [
                "button[type='submit']",
                "button:has-text('Send')",
                "button:has-text('发送')",
                "[aria-label*='send' i]",
            ]
            for sel in send_selectors:
                btns = page.locator(sel).all()
                if btns:
                    send_btn = btns[0]
                    print(f"Send button found: {sel}")
                    break

            # Also try finding by icon or position
            if not send_btn and input_box:
                # Try to find button near input
                parent = input_box.locator("xpath=..")
                btns = parent.locator("button").all()
                if btns:
                    send_btn = btns[-1]  # Usually last button is send
                    print("Found send button near input")

            if send_btn and input_box:
                try:
                    send_btn.click()
                    print("Clicked send button")
                    # Wait for response
                    page.wait_for_timeout(8000)
                    page.screenshot(path="/tmp/round3_05_after_send.png", full_page=True)
                    screenshots.append("/tmp/round3_05_after_send.png")
                except Exception as e:
                    errors.append(f"Failed to send: {e}")
            else:
                errors.append("Send button not found")

            # === Test 6: Check for response ===
            print("\n" + "="*60)
            print("Test 6: Chat Response")
            # Look for assistant messages
            assistant_msgs = page.locator("[role='assistant'], .assistant, .bot-message, [data-role='assistant']").all()
            print(f"Assistant messages found: {len(assistant_msgs)}")
            if assistant_msgs:
                last_msg = assistant_msgs[-1]
                text = last_msg.inner_text().strip()[:200]
                print(f"Last message: {text}")

            # Check for user messages
            user_msgs = page.locator("[role='user'], .user, .user-message, [data-role='user']").all()
            print(f"User messages found: {len(user_msgs)}")

            # === Test 7: Settings/Config Button ===
            print("\n" + "="*60)
            print("Test 7: Settings Button")
            settings_btn = None
            settings_selectors = [
                "button:has-text('Settings')",
                "button:has-text('设置')",
                "[aria-label*='setting' i]",
                "[aria-label*='config' i]",
            ]
            for sel in settings_selectors:
                btns = page.locator(sel).all()
                if btns:
                    settings_btn = btns[0]
                    print(f"Settings button found: {sel}")
                    break

            if settings_btn:
                try:
                    settings_btn.click()
                    page.wait_for_timeout(1500)
                    page.screenshot(path="/tmp/round3_07_settings.png", full_page=True)
                    screenshots.append("/tmp/round3_07_settings.png")
                    print("Opened settings")

                    # Try to close settings (ESC or click outside)
                    page.keyboard.press("Escape")
                    page.wait_for_timeout(500)
                except Exception as e:
                    warnings.append(f"Settings interaction failed: {e}")
            else:
                warnings.append("Settings button not found")

            # === Test 8: Theme Toggle ===
            print("\n" + "="*60)
            print("Test 8: Theme Toggle")
            theme_btn = None
            theme_selectors = [
                "button:has-text('Theme')",
                "button:has-text('主题')",
                "[aria-label*='theme' i]",
                "[aria-label*='dark' i]",
                "[aria-label*='light' i]",
            ]
            for sel in theme_selectors:
                btns = page.locator(sel).all()
                if btns:
                    theme_btn = btns[0]
                    print(f"Theme button found: {sel}")
                    break

            if theme_btn:
                try:
                    theme_btn.click()
                    page.wait_for_timeout(500)
                    page.screenshot(path="/tmp/round3_08_theme.png")
                    screenshots.append("/tmp/round3_08_theme.png")
                    print("Toggled theme")
                except Exception as e:
                    warnings.append(f"Theme toggle failed: {e}")
            else:
                warnings.append("Theme button not found")

            # === Test 9: Command Palette ===
            print("\n" + "="*60)
            print("Test 9: Command Palette (Ctrl+K)")
            try:
                page.keyboard.press("Control+k")
                page.wait_for_timeout(1000)
                page.screenshot(path="/tmp/round3_09_command.png", full_page=True)
                screenshots.append("/tmp/round3_09_command.png")
                print("Opened command palette")
                # Close it
                page.keyboard.press("Escape")
                page.wait_for_timeout(500)
            except Exception as e:
                warnings.append(f"Command palette failed: {e}")

            # === Test 10: Mobile Viewport ===
            print("\n" + "="*60)
            print("Test 10: Mobile Viewport (375x812)")
            page.set_viewport_size({"width": 375, "height": 812})
            page.wait_for_timeout(500)
            page.screenshot(path="/tmp/round3_10_mobile.png", full_page=True)
            screenshots.append("/tmp/round3_10_mobile.png")

            # Try hamburger menu on mobile
            hamburger = page.locator("button[aria-label*='menu' i], .hamburger, [aria-label*='navigation' i]").all()
            if hamburger:
                try:
                    hamburger[0].click()
                    page.wait_for_timeout(500)
                    page.screenshot(path="/tmp/round3_10_mobile_menu.png")
                    screenshots.append("/tmp/round3_10_mobile_menu.png")
                    print("Opened mobile menu")
                except Exception as e:
                    warnings.append(f"Mobile menu failed: {e}")
            else:
                warnings.append("Hamburger menu not found on mobile")

            # Reset viewport
            page.set_viewport_size({"width": 1280, "height": 720})

            # === Test 11: Stop Button (during/after chat) ===
            print("\n" + "="*60)
            print("Test 11: Stop Button")
            stop_btn = None
            stop_selectors = [
                "button:has-text('Stop')",
                "button:has-text('停止')",
                "[aria-label*='stop' i]",
            ]
            for sel in stop_selectors:
                btns = page.locator(sel).all()
                if btns:
                    stop_btn = btns[0]
                    print(f"Stop button found: {sel}")
                    break

            if stop_btn:
                print("Stop button is present")
            else:
                print("Stop button not found (may be hidden when not streaming)")

            # === Test 12: Check all interactive elements ===
            print("\n" + "="*60)
            print("Test 12: All Interactive Elements")
            all_buttons = page.locator("button").all()
            print(f"Total buttons on page: {len(all_buttons)}")
            for i, btn in enumerate(all_buttons):
                text = btn.inner_text().strip()[:30]
                aria = btn.get_attribute("aria-label") or ""
                disabled = btn.is_disabled() if btn.is_visible() else "hidden"
                print(f"  [{i}] text='{text}' aria='{aria}' disabled={disabled}")

            all_links = page.locator("a").all()
            print(f"Total links on page: {len(all_links)}")

            all_inputs = page.locator("input, textarea").all()
            print(f"Total inputs on page: {len(all_inputs)}")

            # Final screenshot
            page.screenshot(path="/tmp/round3_final.png", full_page=True)
            screenshots.append("/tmp/round3_final.png")

        except Exception as e:
            errors.append(f"Test exception: {e}")
            page.screenshot(path="/tmp/round3_error.png", full_page=True)
            screenshots.append("/tmp/round3_error.png")

        browser.close()

    # === Summary ===
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)

    print(f"\nScreenshots ({len(screenshots)}):")
    for s in screenshots:
        print(f"  - {s}")

    print(f"\nConsole logs: {len(console_logs)}")
    errors_in_console = [l for l in console_logs if l["type"] == "error"]
    print(f"Console errors: {len(errors_in_console)}")
    for log in errors_in_console[:15]:
        print(f"  [{log['type']}] {log['text'][:200]}")

    print(f"\nAPI calls: {len(api_calls)}")
    api_reqs = [a for a in api_calls if '/api/' in a['url']]
    print(f"API requests: {len(api_reqs)}")
    for req in api_reqs[:15]:
        print(f"  {req['method']} {req['url'][:80]}")

    if errors:
        print(f"\nERRORS ({len(errors)}):")
        for e in errors:
            print(f"  - {e}")
    else:
        print("\nNo critical errors!")

    if warnings:
        print(f"\nWARNINGS ({len(warnings)}):")
        for w in warnings:
            print(f"  - {w}")

    return errors, warnings, screenshots

if __name__ == "__main__":
    test_gui()
