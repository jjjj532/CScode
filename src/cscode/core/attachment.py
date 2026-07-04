"""P0-4: Attachment model — file attachments for messages.

Provides a dataclass-based Attachment model with MIME type inference,
size tracking, and text vs image discrimination.
"""

from __future__ import annotations

import mimetypes
from dataclasses import dataclass
from pathlib import Path

# Known text extensions that mimetypes may map to application/*
TEXT_EXTENSIONS: set[str] = {
    ".py", ".pyi", ".pyx", ".pxd",
    ".ts", ".tsx", ".mts", ".cts",
    ".js", ".jsx", ".mjs", ".cjs",
    ".rs", ".go", ".rb", ".java", ".kt", ".scala",
    ".swift", ".c", ".cpp", ".h", ".hpp",
    ".css", ".scss", ".less",
    ".html", ".htm", ".xhtml",
    ".xml", ".svg", ".json", ".yaml", ".yml", ".toml",
    ".md", ".mdx", ".rst", ".txt",
    ".sh", ".bash", ".zsh", ".fish",
    ".env", ".gitignore", ".dockerignore",
    ".cfg", ".ini", ".conf",
    ".sql", ".graphql", ".proto",
    ".vue", ".svelte", ".astro",
    ".tex", ".bib",
    ".csv", ".tsv",
    ".diff", ".patch",
    ".lock", ".nix",
    ".zig", ".nim", "ex", ".exs",
}

IMAGE_EXTENSIONS: set[str] = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".svg", ".ico"}


@dataclass
class Attachment:
    """A file attached to a message.

    Attributes:
        path: Original file system path (if applicable).
        name: Display name (usually the basename).
        content: File content as string (text files) or base64 (binary).
        size: File size in bytes.
        mime_type: MIME type string, inferred from extension if available.
        is_image: Whether this is an image file.
        base64_content: Base64-encoded content for binary/image files.
    """

    path: str
    name: str
    content: str
    size: int
    mime_type: str = "text/plain"
    is_image: bool = False
    base64_content: str | None = None

    def __post_init__(self) -> None:
        """Infer mime_type from extension if not explicitly provided."""
        if self.mime_type == "text/plain" and not self.is_image:
            inferred = self._infer_mime(self.name)
            if inferred:
                object.__setattr__(self, "mime_type", inferred)
        if not self.is_image:
            ext = Path(self.name).suffix.lower()
            if ext in IMAGE_EXTENSIONS:
                object.__setattr__(self, "is_image", True)
                if self.mime_type == "text/plain":
                    object.__setattr__(self, "mime_type", f"image/{ext[1:]}")

    @staticmethod
    def _infer_mime(filename: str) -> str | None:
        """Infer MIME type from filename extension."""
        ext = Path(filename).suffix.lower()
        if ext in TEXT_EXTENSIONS:
            mime, _ = mimetypes.guess_type(f"a{ext}")
            if mime:
                return mime
            return "text/plain"
        if ext in IMAGE_EXTENSIONS:
            mime, _ = mimetypes.guess_type(f"a{ext}")
            if mime:
                return mime
            return f"image/{ext[1:]}"
        mime, _ = mimetypes.guess_type(filename)
        return mime

    @property
    def is_text(self) -> bool:
        """Check if the attachment is a text file (not an image)."""
        return not self.is_image

    @classmethod
    def from_path(cls, path: str | Path, content: str | None = None) -> Attachment:
        """Create an Attachment from a file path.

        Args:
            path: File system path.
            content: Explicit content (if None, the file is read).

        Returns:
            A new Attachment instance.
        """
        path_obj = Path(path)
        name = path_obj.name
        if content is not None:
            size = len(content)
        else:
            content = path_obj.read_text(encoding="utf-8")
            size = path_obj.stat().st_size
        ext = path_obj.suffix.lower()
        is_img = ext in IMAGE_EXTENSIONS
        return cls(
            path=str(path_obj.resolve()),
            name=name,
            content=content,
            size=size,
            is_image=is_img,
        )
