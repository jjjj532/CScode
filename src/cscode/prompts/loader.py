"""PromptTemplateLoader — load and render template files.

Templates use Python's built-in string.Formatter syntax ({variable}).
Loaded templates are cached in memory for performance.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from cscode.utils.logging import get_logger

logger = get_logger(__name__)


class PromptTemplateLoader:
    """Load and render prompt templates from a directory.

    Usage:
        loader = PromptTemplateLoader(directory="src/cscode/prompts")
        prompt = loader.load("default_system", name="CScode")
        # Returns: "You are CScode, an AI-powered coding assistant."
    """

    def __init__(self, directory: str) -> None:
        self._directory = Path(directory)
        if not self._directory.exists():
            msg = f"Prompt templates directory not found: {self._directory}"
            raise FileNotFoundError(msg)
        if not self._directory.is_dir():
            msg = f"Not a directory: {self._directory}"
            raise NotADirectoryError(msg)

        self._cache: dict[str, str] = {}
        logger.debug("PromptTemplateLoader initialized: directory=%s", self._directory)

    @property
    def directory(self) -> Path:
        return self._directory

    def load(self, template_name: str, **variables: Any) -> str:
        """Load and render a template by name (without .txt suffix).

        Args:
            template_name: Template name (e.g. "default_system" → "default_system.txt").
            **variables: Variables to substitute into the template.

        Returns:
            Rendered template string.

        Raises:
            FileNotFoundError: If the template file does not exist.
            KeyError: If a required variable is not provided.
        """
        template = self._get_template(template_name)
        return template.format(**variables)

    def load_or_default(self, template_name: str, default: str, **variables: Any) -> str:
        """Load a template, falling back to default text if not found.

        Args:
            template_name: Template name.
            default: Default text to return if template not found.
            **variables: Variables to substitute.

        Returns:
            Rendered template string, or default if not found.
        """
        try:
            return self.load(template_name, **variables)
        except FileNotFoundError:
            logger.debug("Template not found, using default: template_name=%s", template_name)
            return default

    def list_templates(self) -> list[str]:
        """List all available template names (without .txt suffix)."""
        names: list[str] = []
        for f in sorted(self._directory.iterdir()):
            if f.is_file() and f.suffix == ".txt":
                names.append(f.stem)
        return names

    def clear_cache(self) -> None:
        """Clear the in-memory template cache."""
        self._cache.clear()
        logger.debug("PromptTemplateLoader cache cleared")

    def _get_template(self, name: str) -> str:
        """Get template source from cache or disk.

        Args:
            name: Template name (without .txt suffix).

        Returns:
            Template source string.

        Raises:
            FileNotFoundError: If the template file does not exist.
        """
        if name in self._cache:
            return self._cache[name]

        path = self._directory / f"{name}.txt"
        if not path.exists():
            msg = f"Prompt template not found: {name} (path={path})"
            raise FileNotFoundError(msg)

        content = path.read_text(encoding="utf-8")
        self._cache[name] = content
        logger.debug("Cached template: name=%s size=%d", name, len(content))
        return content
