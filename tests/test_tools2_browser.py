"""Unit tests for tools2 BrowserTool (typed v2 API)."""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cscode.tools2.browser import (
    EVIDENCE_DIR,
    BrowserInput,
    BrowserOutput,
    BrowserTool,
    _find_system_chrome,
)

# ---------------------------------------------------------------------------
# _find_system_chrome
# ---------------------------------------------------------------------------


class TestFindSystemChrome:
    def test_returns_none_when_no_chrome(self) -> None:
        with patch("os.path.exists", return_value=False):
            assert _find_system_chrome() is None

    def test_returns_path_when_chrome_found(self) -> None:
        with patch("os.path.exists", side_effect=lambda p: p == "/usr/bin/google-chrome-stable"):
            result = _find_system_chrome()
            assert result == "/usr/bin/google-chrome-stable"


# ---------------------------------------------------------------------------
# BrowserTool properties & schemas
# ---------------------------------------------------------------------------


class TestBrowserToolProperties:
    def test_name_and_description(self) -> None:
        tool = BrowserTool()
        assert tool.name == "browser"
        assert "browser" in tool.description.lower()
        assert "automation" in tool.description.lower()

    def test_input_schema(self) -> None:
        tool = BrowserTool()
        assert tool.input_schema is BrowserInput

    def test_output_schema(self) -> None:
        tool = BrowserTool()
        assert tool.output_schema is BrowserOutput

    def test_to_definition(self) -> None:
        tool = BrowserTool()
        definition = tool.to_definition()
        assert definition.name == "browser"
        assert "type" in definition.input_schema

    def test_browser_input_valid(self) -> None:
        inp = BrowserInput(action="open", url="https://example.com")
        assert inp.action == "open"
        assert inp.url == "https://example.com"
        assert inp.selector is None

    def test_browser_input_defaults(self) -> None:
        inp = BrowserInput(action="close")
        assert inp.task_id == ""
        assert inp.url is None

    def test_browser_output(self) -> None:
        out = BrowserOutput(result="hello")
        assert out.result == "hello"


# ---------------------------------------------------------------------------
# BrowserTool actions (mocked Playwright)
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_page() -> MagicMock:
    page = MagicMock()
    page.title = AsyncMock(return_value="Test Page")
    page.goto = AsyncMock()
    page.click = AsyncMock()
    page.fill = AsyncMock()
    page.press = AsyncMock()
    page.screenshot = AsyncMock()
    page.content = AsyncMock(return_value="<html><body>Content</body></html>")
    page.locator = MagicMock()
    page.locator.return_value.text_content = AsyncMock(return_value="Hello World")
    page.locator.return_value.inner_html = AsyncMock(return_value="<p>Inner</p>")
    page.locator.return_value.scroll_into_view_if_needed = AsyncMock()
    page.wait_for_selector = AsyncMock()
    page.evaluate = AsyncMock()
    page.url = "https://example.com"
    return page


@pytest.fixture
def mock_browser(mock_page: MagicMock) -> MagicMock:
    browser = MagicMock()
    browser.new_page = AsyncMock(return_value=mock_page)
    browser.close = AsyncMock()
    return browser


@pytest.fixture
def mock_pw(mock_browser: MagicMock) -> MagicMock:
    pw = MagicMock()
    pw.chromium.launch = AsyncMock(return_value=mock_browser)
    return pw


@pytest.fixture
def mock_playwright_ctx(mock_pw: MagicMock) -> MagicMock:
    """async_playwright() returns a context-like object; .start() yields the PW instance."""
    ctx = MagicMock()
    ctx.start = AsyncMock(return_value=mock_pw)
    return ctx


@pytest.fixture
def tool() -> BrowserTool:
    return BrowserTool()


def _reset_globals() -> None:
    """Reset BrowserTool module-level state between tests."""
    import cscode.tools2.browser as b

    b._browser = None
    b._page = None


@pytest.mark.asyncio
async def test_action_open(
    tool: BrowserTool,
    mock_playwright_ctx: MagicMock,
    mock_page: MagicMock,
) -> None:
    _reset_globals()
    with patch("playwright.async_api.async_playwright", return_value=mock_playwright_ctx):
        result = await tool.execute(BrowserInput(action="open", url="https://example.com"))

    assert result.success
    assert result.data is not None
    assert "Opened" in result.data.result
    assert "Test Page" in result.data.result
    mock_page.goto.assert_awaited_once_with("https://example.com", wait_until="domcontentloaded", timeout=30000)


@pytest.mark.asyncio
async def test_action_open_adds_https(
    tool: BrowserTool,
    mock_playwright_ctx: MagicMock,
    mock_page: MagicMock,
) -> None:
    _reset_globals()
    with patch("playwright.async_api.async_playwright", return_value=mock_playwright_ctx):
        result = await tool.execute(BrowserInput(action="open", url="example.com"))

    assert result.success
    mock_page.goto.assert_awaited_once_with("https://example.com", wait_until="domcontentloaded", timeout=30000)


@pytest.mark.asyncio
async def test_action_click(
    tool: BrowserTool,
    mock_playwright_ctx: MagicMock,
    mock_page: MagicMock,
) -> None:
    _reset_globals()
    with patch("playwright.async_api.async_playwright", return_value=mock_playwright_ctx):
        # Need to open first to have _browser and _page
        await tool.execute(BrowserInput(action="open", url="https://example.com"))
        result = await tool.execute(BrowserInput(action="click", selector="#btn"))

    assert result.success
    assert result.data is not None
    assert "Clicked" in result.data.result
    mock_page.click.assert_awaited_once_with("#btn", timeout=10000)


@pytest.mark.asyncio
async def test_action_type(
    tool: BrowserTool,
    mock_playwright_ctx: MagicMock,
    mock_page: MagicMock,
) -> None:
    _reset_globals()
    with patch("playwright.async_api.async_playwright", return_value=mock_playwright_ctx):
        await tool.execute(BrowserInput(action="open", url="https://example.com"))
        result = await tool.execute(BrowserInput(action="type", selector="#input", text="hello"))

    assert result.success
    assert result.data is not None
    assert "Typed" in result.data.result
    mock_page.fill.assert_awaited_once_with("#input", "hello")


@pytest.mark.asyncio
async def test_action_press(
    tool: BrowserTool,
    mock_playwright_ctx: MagicMock,
    mock_page: MagicMock,
) -> None:
    _reset_globals()
    with patch("playwright.async_api.async_playwright", return_value=mock_playwright_ctx):
        await tool.execute(BrowserInput(action="open", url="https://example.com"))
        result = await tool.execute(BrowserInput(action="press", key="Enter"))

    assert result.success
    assert result.data is not None
    assert "Pressed" in result.data.result
    mock_page.press.assert_awaited_once_with("body", "Enter")


@pytest.mark.asyncio
async def test_action_screenshot(
    tool: BrowserTool,
    mock_playwright_ctx: MagicMock,
    mock_page: MagicMock,
) -> None:
    _reset_globals()
    with patch("playwright.async_api.async_playwright", return_value=mock_playwright_ctx):
        await tool.execute(BrowserInput(action="open", url="https://example.com"))
        result = await tool.execute(BrowserInput(action="screenshot", task_id="t1"))

    assert result.success
    assert result.data is not None
    assert "Screenshot saved" in result.data.result
    expected_path = os.path.join(EVIDENCE_DIR, "t1_screenshot.png")
    mock_page.screenshot.assert_awaited_once_with(path=expected_path, full_page=True)


@pytest.mark.asyncio
async def test_action_get_text(
    tool: BrowserTool,
    mock_playwright_ctx: MagicMock,
    mock_page: MagicMock,
) -> None:
    _reset_globals()
    with patch("playwright.async_api.async_playwright", return_value=mock_playwright_ctx):
        await tool.execute(BrowserInput(action="open", url="https://example.com"))
        result = await tool.execute(BrowserInput(action="get_text", selector="h1"))

    assert result.success
    assert result.data is not None
    assert result.data.result == "Hello World"


@pytest.mark.asyncio
async def test_action_get_html(
    tool: BrowserTool,
    mock_playwright_ctx: MagicMock,
    mock_page: MagicMock,
) -> None:
    _reset_globals()
    with patch("playwright.async_api.async_playwright", return_value=mock_playwright_ctx):
        await tool.execute(BrowserInput(action="open", url="https://example.com"))
        result = await tool.execute(BrowserInput(action="get_html"))

    assert result.success
    assert result.data is not None
    assert "Content" in result.data.result


@pytest.mark.asyncio
async def test_action_wait_selector(
    tool: BrowserTool,
    mock_playwright_ctx: MagicMock,
    mock_page: MagicMock,
) -> None:
    _reset_globals()
    with patch("playwright.async_api.async_playwright", return_value=mock_playwright_ctx):
        await tool.execute(BrowserInput(action="open", url="https://example.com"))
        result = await tool.execute(BrowserInput(action="wait", selector=".loaded", seconds=5))

    assert result.success
    assert result.data is not None
    assert "Waited for" in result.data.result
    mock_page.wait_for_selector.assert_awaited_once_with(".loaded", timeout=5000)


@pytest.mark.asyncio
async def test_action_wait_time(
    tool: BrowserTool,
    mock_playwright_ctx: MagicMock,
    mock_page: MagicMock,
) -> None:
    _reset_globals()
    with (
        patch("playwright.async_api.async_playwright", return_value=mock_playwright_ctx),
        patch("cscode.tools2.browser.asyncio.sleep", AsyncMock()) as mock_sleep,
    ):
        await tool.execute(BrowserInput(action="open", url="https://example.com"))
        result = await tool.execute(BrowserInput(action="wait", seconds=3))

    assert result.success
    assert result.data is not None
    assert "Waited 3.0s" in result.data.result
    mock_sleep.assert_awaited_once_with(3)


@pytest.mark.asyncio
async def test_action_scroll_element(
    tool: BrowserTool,
    mock_playwright_ctx: MagicMock,
    mock_page: MagicMock,
) -> None:
    _reset_globals()
    with patch("playwright.async_api.async_playwright", return_value=mock_playwright_ctx):
        await tool.execute(BrowserInput(action="open", url="https://example.com"))
        result = await tool.execute(BrowserInput(action="scroll", selector="#footer"))

    assert result.success
    assert result.data is not None
    assert "Scrolled" in result.data.result
    mock_page.locator.return_value.scroll_into_view_if_needed.assert_awaited_once()


@pytest.mark.asyncio
async def test_action_scroll_bottom(
    tool: BrowserTool,
    mock_playwright_ctx: MagicMock,
    mock_page: MagicMock,
) -> None:
    _reset_globals()
    with patch("playwright.async_api.async_playwright", return_value=mock_playwright_ctx):
        await tool.execute(BrowserInput(action="open", url="https://example.com"))
        result = await tool.execute(BrowserInput(action="scroll"))

    assert result.success
    mock_page.evaluate.assert_awaited_once_with("window.scrollTo(0, document.body.scrollHeight)")


@pytest.mark.asyncio
async def test_action_close(
    tool: BrowserTool,
    mock_playwright_ctx: MagicMock,
    mock_browser: MagicMock,
) -> None:
    _reset_globals()
    with patch("playwright.async_api.async_playwright", return_value=mock_playwright_ctx):
        await tool.execute(BrowserInput(action="open", url="https://example.com"))
        result = await tool.execute(BrowserInput(action="close"))

    assert result.success
    assert result.data is not None
    assert "Browser closed" in result.data.result
    mock_browser.close.assert_awaited_once()

    # Verify globals are cleaned
    import cscode.tools2.browser as b

    assert b._browser is None
    assert b._page is None


@pytest.mark.asyncio
async def test_action_status_running(
    tool: BrowserTool,
    mock_playwright_ctx: MagicMock,
) -> None:
    _reset_globals()
    with patch("playwright.async_api.async_playwright", return_value=mock_playwright_ctx):
        await tool.execute(BrowserInput(action="open", url="https://example.com"))
        result = await tool.execute(BrowserInput(action="status"))

    assert result.success
    assert result.data is not None
    assert "Running" in result.data.result


@pytest.mark.asyncio
async def test_action_status_not_running(tool: BrowserTool) -> None:
    _reset_globals()
    result = await tool.execute(BrowserInput(action="status"))
    assert result.success
    assert result.data is not None
    assert "not running" in result.data.result


# ---------------------------------------------------------------------------
# Error & edge cases
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_click_without_selector_returns_error(tool: BrowserTool) -> None:
    _reset_globals()
    result = await tool.execute(BrowserInput(action="click"))
    assert not result.success
    assert "selector is required" in (result.error or "")


@pytest.mark.asyncio
async def test_type_without_selector_returns_error(tool: BrowserTool) -> None:
    _reset_globals()
    result = await tool.execute(BrowserInput(action="type"))
    assert not result.success
    assert "selector is required" in (result.error or "")


@pytest.mark.asyncio
async def test_get_text_without_selector_returns_error(tool: BrowserTool) -> None:
    _reset_globals()
    result = await tool.execute(BrowserInput(action="get_text"))
    assert not result.success
    assert "selector is required" in (result.error or "")


@pytest.mark.asyncio
async def test_unknown_action(tool: BrowserTool) -> None:
    _reset_globals()
    # Use model_construct to bypass Pydantic Literal validation
    inp = BrowserInput.model_construct(action="unknown_action")
    result = await tool.execute(inp)
    assert not result.success
    assert "Unknown action" in (result.error or "")


@pytest.mark.asyncio
async def test_task_id_passed_through_on_error(tool: BrowserTool) -> None:
    _reset_globals()
    result = await tool.execute(BrowserInput(action="click", task_id="my_task"))
    assert not result.success
    assert result.metadata.get("task_id") == "my_task"


@pytest.mark.asyncio
async def test_task_id_on_success(
    tool: BrowserTool,
    mock_playwright_ctx: MagicMock,
) -> None:
    _reset_globals()
    with patch("playwright.async_api.async_playwright", return_value=mock_playwright_ctx):
        result = await tool.execute(
            BrowserInput(action="open", url="https://example.com", task_id="my_task")
        )

    assert result.success
    assert result.metadata.get("task_id") == "my_task"


@pytest.mark.asyncio
async def test_exception_during_execution_is_caught(tool: BrowserTool) -> None:
    """When execute() propagates an exception, it should be caught and returned as error."""
    _reset_globals()
    # Ensure _page is set but _page.goto raises
    import cscode.tools2.browser as b

    mock_page = MagicMock()
    mock_page.goto = AsyncMock(side_effect=RuntimeError("connection lost"))
    b._browser = MagicMock()
    b._page = mock_page

    result = await tool.execute(BrowserInput(action="open", url="https://example.com"))
    assert not result.success
    assert "connection lost" in (result.error or "")


@pytest.mark.asyncio
async def test_ensure_browser_idempotent(tool: BrowserTool) -> None:
    """Calling _ensure_browser when already running should not launch again."""
    _reset_globals()
    import cscode.tools2.browser as b

    b._browser = MagicMock()

    with patch("playwright.async_api.async_playwright") as mock_async_pw:
        await tool._ensure_browser()

    mock_async_pw.assert_not_called()
