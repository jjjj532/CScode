"""Tests for Prompt Template system — P0-7.

Tests PromptTemplateLoader with temporary template directories.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from cscode.prompts.loader import PromptTemplateLoader

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def template_dir(tmp_path: Path) -> Path:
    """Create a temporary directory with some template files."""
    d = tmp_path / "templates"
    d.mkdir()

    # Default system prompt
    (d / "default_system.txt").write_text(
        "You are {name}, an AI-powered coding assistant."
    )

    # LSP prompt
    (d / "lsp.txt").write_text(
        "You have LSP tools available: {tools}."
    )

    # Multi-line template with multiple variables
    (d / "complex.txt").write_text(
        "System: {system}\n"
        "User: {user}\n"
        "Provider: {provider}\n"
    )

    return d


# ---------------------------------------------------------------------------
# Registration / Basics
# ---------------------------------------------------------------------------

class TestPromptTemplateLoaderBasics:
    def test_init_with_directory(self, template_dir: Path) -> None:
        loader = PromptTemplateLoader(directory=str(template_dir))
        assert loader.directory == template_dir

    def test_init_directory_not_exists(self, tmp_path: Path) -> None:
        fake_dir = tmp_path / "does-not-exist"
        with pytest.raises(FileNotFoundError, match="not found"):
            PromptTemplateLoader(directory=str(fake_dir))


# ---------------------------------------------------------------------------
# Template Loading
# ---------------------------------------------------------------------------

class TestPromptTemplateLoading:
    def test_load_existing_template(self, template_dir: Path) -> None:
        loader = PromptTemplateLoader(directory=str(template_dir))
        content = loader.load("default_system", name="CScode")
        assert "AI-powered coding assistant" in content
        assert "{name}" not in content

    def test_load_with_variables(self, template_dir: Path) -> None:
        loader = PromptTemplateLoader(directory=str(template_dir))
        content = loader.load("default_system", name="CScode")
        assert "You are CScode" in content
        assert "{name}" not in content

    def test_load_missing_variable_raises(self, template_dir: Path) -> None:
        """Loading with missing variable should raise KeyError."""
        loader = PromptTemplateLoader(directory=str(template_dir))
        with pytest.raises(KeyError, match="name"):
            loader.load("default_system")

    def test_load_with_multiple_variables(self, template_dir: Path) -> None:
        loader = PromptTemplateLoader(directory=str(template_dir))
        content = loader.load("complex", system="helpful", user="hi", provider="openai")
        assert "System: helpful" in content
        assert "User: hi" in content
        assert "Provider: openai" in content

    def test_load_nonexistent_template(self, template_dir: Path) -> None:
        loader = PromptTemplateLoader(directory=str(template_dir))
        with pytest.raises(FileNotFoundError, match="not found"):
            loader.load("nonexistent_template")

    def test_load_with_default_fallback(self, template_dir: Path) -> None:
        """load_or_default returns default text when template not found."""
        loader = PromptTemplateLoader(directory=str(template_dir))
        fallback = "default text"
        content = loader.load_or_default("nonexistent_template", default=fallback)
        assert content == fallback

    def test_load_or_default_returns_template(self, template_dir: Path) -> None:
        """load_or_default returns template content when found."""
        loader = PromptTemplateLoader(directory=str(template_dir))
        content = loader.load_or_default("default_system", default="fallback", name="Test")
        assert "You are Test" in content
        assert content != "fallback"


# ---------------------------------------------------------------------------
# Caching
# ---------------------------------------------------------------------------

class TestPromptTemplateCaching:
    def test_cache_hits(self, template_dir: Path) -> None:
        loader = PromptTemplateLoader(directory=str(template_dir))
        # First call loads from disk
        content1 = loader.load("default_system", name="First")
        assert "You are First" in content1

        # Second call should use cache (modify file to prove it)
        (template_dir / "default_system.txt").write_text("MODIFIED: {name}")
        content2 = loader.load("default_system", name="Second")
        # Should still be the original cached content since the template text is cached
        assert "You are" in content2
        assert "MODIFIED" not in content2

    def test_cache_clear(self, template_dir: Path) -> None:
        loader = PromptTemplateLoader(directory=str(template_dir))
        content1 = loader.load("default_system", name="First")
        assert "You are First" in content1

        # Clear cache
        loader.clear_cache()

        # Modify file
        (template_dir / "default_system.txt").write_text("NEW: {name}")

        content2 = loader.load("default_system", name="Second")
        assert "NEW: Second" in content2


# ---------------------------------------------------------------------------
# Template listing
# ---------------------------------------------------------------------------

class TestPromptTemplateListing:
    def test_list_templates(self, template_dir: Path) -> None:
        loader = PromptTemplateLoader(directory=str(template_dir))
        names = loader.list_templates()
        assert "default_system" in names
        assert "lsp" in names
        assert "complex" in names
        assert len(names) == 3

    def test_list_templates_empty(self, tmp_path: Path) -> None:
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()
        loader = PromptTemplateLoader(directory=str(empty_dir))
        assert loader.list_templates() == []


# ---------------------------------------------------------------------------
# Integration: use with AgentV2 (optional, will be added when agent is modified)
# ---------------------------------------------------------------------------

class TestPromptTemplateIntegration:
    async def test_default_system_prompt_format(self, template_dir: Path) -> None:
        """The default system prompt should be a valid agent prompt."""
        loader = PromptTemplateLoader(directory=str(template_dir))
        prompt = loader.load("default_system", name="CScode")
        assert prompt
        assert len(prompt) > 10
        assert "{name}" not in prompt

    async def test_lsp_prompt(self, template_dir: Path) -> None:
        loader = PromptTemplateLoader(directory=str(template_dir))
        prompt = loader.load("lsp", tools="hover, definition, completion")
        assert "hover" in prompt
        assert "{tools}" not in prompt


class TestPromptTemplateLoaderDefaultDir:
    """Test that PromptTemplateLoader can find the built-in prompts directory."""

    def test_default_directory_exists(self) -> None:
        """The default prompts directory should exist in the package."""
        prompts_dir = Path(__file__).parent.parent / "src" / "cscode" / "prompts"
        assert prompts_dir.exists(), (
            f"Default prompts directory not found: {prompts_dir}\n"
            "Create src/cscode/prompts/ with template files before this test passes"
        )
