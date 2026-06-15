import pytest
from cscode.tools.browser import BrowserTool


@pytest.fixture
def browser_tool():
    return BrowserTool()


def test_browser_tool_properties(browser_tool):
    """Test browser tool basic properties"""
    assert browser_tool.name == "browser"
    assert "browser" in browser_tool.description.lower() or "automation" in browser_tool.description.lower()


def test_browser_supported_actions(browser_tool):
    """Test all supported browser actions are defined"""
    params = browser_tool.parameters
    params_str = str(params)
    assert "open" in params_str
    assert "click" in params_str
    assert "screenshot" in params_str
    assert "get_html" in params_str


@pytest.mark.asyncio
async def test_playwright_integration():
    """Integration test - only run if playwright is installed"""
    try:
        from playwright.async_api import async_playwright
        
        pw = await async_playwright().start()
        browser = await pw.chromium.launch(headless=True)
        page = await browser.new_page()
        
        await page.goto('https://voice.styoai.com')
        title = await page.title()
        
        await browser.close()
        
        assert "智转" in title or "voice" in title.lower()
    except ImportError:
        pytest.skip("playwright not installed")
