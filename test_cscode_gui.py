"""CScode GUI Comprehensive Test Script"""
from playwright.sync_api import sync_playwright
import json
import time

def test_cscode_gui():
    errors = []
    screenshots = []

    with sync_playwright() as p:
        # Launch browser
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1280, "height": 720})
        page = context.new_page()

        # Enable console logging
        console_logs = []
        def handle_console(msg):
            console_logs.append(f"[{msg.type}] {msg.text}")
        page.on("console", handle_console)

        # Track network requests
        network_requests = []
        def handle_request(request):
            network_requests.append({"url": request.url, "method": request.method})
        page.on("request", handle_request)

        try:
            # Test 1: Navigate to app
            print("=" * 60)
            print("Test 1: Navigate to app")
            page.goto('http://localhost:5173')
            page.wait_for_load_state('networkidle')
            page.screenshot(path='/tmp/cscode_test_01_initial.png', full_page=True)
            screenshots.append('/tmp/cscode_test_01_initial.png')
            print(f"Page title: {page.title()}")

            # Check if main elements are visible
            main_visible = page.locator('main, [role="main"], #main, .main').count() > 0
            print(f"Main content area visible: {main_visible}")

            # Test 2: Check sidebar
            print("\n" + "=" * 60)
            print("Test 2: Check sidebar")
            sidebar_selectors = ['aside', '[role="navigation"]', '.sidebar', '#sidebar']
            sidebar_found = False
            for sel in sidebar_selectors:
                if page.locator(sel).count() > 0:
                    print(f"Sidebar found: {sel}")
                    sidebar_found = True
                    break
            if not sidebar_found:
                errors.append("Sidebar not found")

            # Test 3: Find and click new chat button
            print("\n" + "=" * 60)
            print("Test 3: Test new chat button")
            new_chat_selectors = [
                'button:has-text("New"), button:has-text("新对话"), button:has-text("Chat")',
                '[aria-label*="new"], [aria-label*="chat"]',
                'button:has(svg)'
            ]
            new_chat_found = False
            for sel in new_chat_selectors:
                buttons = page.locator(sel).all()
                if buttons:
                    print(f"Found {len(buttons)} elements matching '{sel}'")
                    new_chat_found = True
                    break

            # Test 4: Find input box
            print("\n" + "=" * 60)
            print("Test 4: Find input box")
            input_selectors = ['input[type="text"]', 'textarea', '[contenteditable="true"]']
            input_found = False
            for sel in input_selectors:
                inputs = page.locator(sel).all()
                if inputs:
                    print(f"Found {len(inputs)} input(s): {sel}")
                    input_found = True
                    # Try to type
                    try:
                        inputs[0].fill("Hello, please introduce yourself")
                        print("Successfully typed in input")
                        break
                    except Exception as e:
                        print(f"Failed to type: {e}")

            if not input_found:
                errors.append("Input box not found")

            # Test 5: Find send button
            print("\n" + "=" * 60)
            print("Test 5: Find send button")
            send_selectors = [
                'button[type="submit"]',
                'button:has-text("Send"), button:has-text("发送")',
                '[aria-label*="send"], [aria-label*="Send"]'
            ]
            send_button = None
            for sel in send_selectors:
                buttons = page.locator(sel).all()
                if buttons:
                    print(f"Found {len(buttons)} button(s) matching '{sel}'")
                    send_button = buttons[0]
                    break

            # Test 6: Send a message
            if send_button:
                print("\n" + "=" * 60)
                print("Test 6: Send message")
                try:
                    send_button.click()
                    print("Clicked send button")
                    page.wait_for_timeout(3000)
                    page.screenshot(path='/tmp/cscode_test_06_after_send.png', full_page=True)
                    screenshots.append('/tmp/cscode_test_06_after_send.png')

                    # Wait for response
                    page.wait_for_timeout(10000)

                    # Check for new content
                    page.screenshot(path='/tmp/cscode_test_06_response.png', full_page=True)
                    screenshots.append('/tmp/cscode_test_06_response.png')

                    # Check console for errors
                    error_logs = [l for l in console_logs if 'error' in l.lower()]
                    if error_logs:
                        print(f"\nConsole errors ({len(error_logs)}):")
                        for log in error_logs[:5]:
                            print(f"  {log}")
                except Exception as e:
                    errors.append(f"Failed to send message: {e}")

            # Test 7: Check API calls
            print("\n" + "=" * 60)
            print("Test 7: Check API calls")
            api_requests = [r for r in network_requests if '/api/' in r['url']]
            print(f"Total API requests: {len(api_requests)}")
            for req in api_requests[:10]:
                print(f"  {req['method']} {req['url']}")

            # Test 8: Test settings button
            print("\n" + "=" * 60)
            print("Test 8: Test settings")
            settings_selectors = [
                'button:has-text("Settings"), button:has-text("设置")',
                '[aria-label*="setting"], [aria-label*="Setting"]',
                'button:has-text("⚙")'
            ]
            for sel in settings_selectors:
                buttons = page.locator(sel).all()
                if buttons:
                    print(f"Found settings button: {sel}")
                    try:
                        buttons[0].click()
                        page.wait_for_timeout(1000)
                        page.screenshot(path='/tmp/cscode_test_08_settings.png', full_page=True)
                        screenshots.append('/tmp/cscode_test_08_settings.png')
                        break
                    except Exception as e:
                        print(f"Failed to click settings: {e}")

            # Test 9: Test theme toggle
            print("\n" + "=" * 60)
            print("Test 9: Test theme toggle")
            theme_selectors = [
                'button:has-text("Theme"), button:has-text("主题")',
                '[aria-label*="theme"], [aria-label*="Theme"]'
            ]
            for sel in theme_selectors:
                buttons = page.locator(sel).all()
                if buttons:
                    print(f"Found theme button: {sel}")
                    break

            # Test 10: Check for mobile view
            print("\n" + "=" * 60)
            print("Test 10: Test mobile view")
            page.set_viewport_size({"width": 375, "height": 812})
            page.wait_for_timeout(500)
            page.screenshot(path='/tmp/cscode_test_10_mobile.png', full_page=True)
            screenshots.append('/tmp/cscode_test_10_mobile.png')
            page.set_viewport_size({"width": 1280, "height": 720})

        except Exception as e:
            errors.append(f"Test exception: {e}")
            page.screenshot(path='/tmp/cscode_test_error.png', full_page=True)
            screenshots.append('/tmp/cscode_test_error.png')

        finally:
            browser.close()

    # Print summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    print(f"Screenshots saved: {len(screenshots)}")
    for s in screenshots:
        print(f"  - {s}")

    print(f"\nConsole logs: {len(console_logs)}")
    error_logs = [l for l in console_logs if 'error' in l.lower()]
    print(f"Error logs: {len(error_logs)}")
    for log in error_logs[:10]:
        print(f"  {log}")

    print(f"\nNetwork requests: {len(network_requests)}")
    print(f"API requests: {len(api_requests)}")

    if errors:
        print(f"\nERRORS ({len(errors)}):")
        for err in errors:
            print(f"  - {err}")
    else:
        print("\nNo critical errors detected!")

    return errors, screenshots

if __name__ == "__main__":
    errors, screenshots = test_cscode_gui()
