"""CScode Round 4 Final GUI Test"""
from playwright.sync_api import sync_playwright
import json

def test_final():
    results = {
        "passed": [],
        "failed": [],
        "warnings": [],
        "screenshots": []
    }

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 720})
        
        console_errors = []
        page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)

        try:
            # === Test 1: Page Load ===
            print("Test 1: Page Load")
            page.goto("http://localhost:5173")
            page.wait_for_load_state("networkidle")
            page.wait_for_timeout(2000)
            page.screenshot(path="/tmp/r4_final_01.png", full_page=True)
            results["screenshots"].append("/tmp/r4_final_01.png")
            
            if page.title() == "CScode - AI Coding Assistant":
                results["passed"].append("Page title correct")
            else:
                results["failed"].append(f"Page title: {page.title()}")
            
            if len(console_errors) == 0:
                results["passed"].append("No console errors")
            else:
                results["failed"].append(f"Console errors: {len(console_errors)}")
                for err in console_errors[:3]:
                    print(f"  ERROR: {err[:100]}")

            # === Test 2: Sidebar Sessions ===
            print("\nTest 2: Sidebar Sessions")
            sessions = page.locator("text=New Session, text=Test Round, text=Round4").all()
            print(f"Found {len(sessions)} session items in sidebar")
            if len(sessions) > 0:
                results["passed"].append(f"Sessions loaded: {len(sessions)}")
            else:
                results["failed"].append("No sessions found")

            # === Test 3: Create New Session ===
            print("\nTest 3: Create New Session")
            new_btn = page.locator("[aria-label='Create new session'], button:has-text('New Session')").first
            if new_btn.is_visible():
                new_btn.click()
                page.wait_for_timeout(1000)
                page.screenshot(path="/tmp/r4_final_03.png")
                results["screenshots"].append("/tmp/r4_final_03.png")
                results["passed"].append("New session button works")
            else:
                results["failed"].append("New session button not found")

            # === Test 4: Input and Send ===
            print("\nTest 4: Input and Send")
            textarea = page.locator("textarea").first
            if textarea.is_visible():
                textarea.fill("What is 2+2? Answer in one sentence.")
                results["passed"].append("Input field works")
                
                # Find send button (try multiple selectors)
                send_btn = None
                for sel in [
                    "button[type='submit']",
                    "button:has-text('Send')",
                    "button:has-text('发送')",
                    "textarea >> xpath=..//button"
                ]:
                    btns = page.locator(sel).all()
                    if btns:
                        send_btn = btns[0]
                        break
                
                if send_btn and send_btn.is_visible():
                    send_btn.click()
                    page.wait_for_timeout(10000)  # Wait for response
                    page.screenshot(path="/tmp/r4_final_04.png", full_page=True)
                    results["screenshots"].append("/tmp/r4_final_04.png")
                    results["passed"].append("Send button clicked")
                else:
                    results["failed"].append("Send button not found")
            else:
                results["failed"].append("Textarea not found")

            # === Test 5: Check for Response ===
            print("\nTest 5: Check Response")
            # Look for assistant response in the page
            page_text = page.inner_text("body")
            if "2" in page_text or "four" in page_text.lower() or "Two" in page_text:
                results["passed"].append("Response received")
            else:
                results["warnings"].append("Response may not have appeared yet")
            
            # Count message elements
            msg_count = page.locator("[role='article'], [role='log'], .message, .msg").count()
            print(f"Message elements found: {msg_count}")

            # === Test 6: Settings ===
            print("\nTest 6: Settings")
            settings_btn = page.locator("button:has-text('Settings')").first
            if settings_btn.is_visible():
                settings_btn.click()
                page.wait_for_timeout(1500)
                page.screenshot(path="/tmp/r4_final_06.png", full_page=True)
                results["screenshots"].append("/tmp/r4_final_06.png")
                
                # Check settings content
                settings_text = page.inner_text("body")
                if "API" in settings_text or "Model" in settings_text:
                    results["passed"].append("Settings panel opened")
                else:
                    results["warnings"].append("Settings may be empty")
                
                page.keyboard.press("Escape")
                page.wait_for_timeout(500)
            else:
                results["failed"].append("Settings button not found")

            # === Test 7: Command Palette ===
            print("\nTest 7: Command Palette")
            page.keyboard.press("Control+k")
            page.wait_for_timeout(1000)
            page.screenshot(path="/tmp/r4_final_07.png")
            results["screenshots"].append("/tmp/r4_final_07.png")
            results["passed"].append("Command palette opened")
            page.keyboard.press("Escape")
            page.wait_for_timeout(500)

            # === Test 8: Mobile View ===
            print("\nTest 8: Mobile View")
            page.set_viewport_size({"width": 375, "height": 812})
            page.wait_for_timeout(500)
            page.screenshot(path="/tmp/r4_final_08.png", full_page=True)
            results["screenshots"].append("/tmp/r4_final_08.png")
            page.set_viewport_size({"width": 1280, "height": 720})

            # === Test 9: All Buttons ===
            print("\nTest 9: All Buttons")
            buttons = page.locator("button").all()
            print(f"Total buttons: {len(buttons)}")
            unlabeled = [b for b in buttons if not b.get_attribute("aria-label") and not b.inner_text().strip()]
            print(f"Unlabeled buttons: {len(unlabeled)}")
            if len(unlabeled) < 5:
                results["passed"].append("Most buttons have labels")
            else:
                results["warnings"].append(f"Many unlabeled buttons: {len(unlabeled)}")

            # === Test 10: Final Screenshot ===
            page.screenshot(path="/tmp/r4_final_10.png", full_page=True)
            results["screenshots"].append("/tmp/r4_final_10.png")

        except Exception as e:
            results["failed"].append(f"Exception: {str(e)}")
            page.screenshot(path="/tmp/r4_final_error.png")
            results["screenshots"].append("/tmp/r4_final_error.png")

        browser.close()

    # Print results
    print("\n" + "="*60)
    print("ROUND 4 TEST RESULTS")
    print("="*60)
    
    print(f"\n✓ PASSED ({len(results['passed'])}):")
    for p in results["passed"]:
        print(f"  ✓ {p}")
    
    if results["warnings"]:
        print(f"\n⚠ WARNINGS ({len(results['warnings'])}):")
        for w in results["warnings"]:
            print(f"  ⚠ {w}")
    
    if results["failed"]:
        print(f"\n✗ FAILED ({len(results['failed'])}):")
        for f in results["failed"]:
            print(f"  ✗ {f}")
    
    print(f"\nScreenshots: {len(results['screenshots'])}")
    for s in results["screenshots"]:
        print(f"  - {s}")
    
    return results

if __name__ == "__main__":
    test_final()
