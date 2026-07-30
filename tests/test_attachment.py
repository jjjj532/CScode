from __future__ import annotations

import tempfile
from pathlib import Path

from cscode.core.attachment import IMAGE_EXTENSIONS, TEXT_EXTENSIONS, Attachment


class TestAttachment:
    def test_minimal_construction(self) -> None:
        att = Attachment(path="/tmp/f.txt", name="f.txt", content="hello", size=5)
        assert att.path == "/tmp/f.txt"
        assert att.name == "f.txt"
        assert att.content == "hello"
        assert att.size == 5
        assert att.mime_type == "text/plain"  # default

    def test_default_is_text(self) -> None:
        att = Attachment(path="/tmp/f.txt", name="f.txt", content="x", size=1)
        assert att.is_text
        assert not att.is_image

    def test_post_init_infers_mime_from_text_extension(self) -> None:
        """__post_init__ should infer Python MIME from .py extension."""
        att = Attachment(path="/tmp/script.py", name="script.py", content="print(1)", size=7)
        assert att.mime_type == "text/x-python"

    def test_post_init_infers_mime_from_image_extension(self) -> None:
        """__post_init__ should detect .png as image and set MIME."""
        att = Attachment(path="/tmp/img.png", name="img.png", content="x", size=1)
        assert att.is_image
        assert not att.is_text
        assert att.mime_type == "image/png"

    def test_post_init_explicit_mime_preserved(self) -> None:
        """If mime_type is explicitly set, __post_init__ should not override."""
        att = Attachment(
            path="/tmp/f.py", name="f.py", content="x", size=1,
            mime_type="application/octet-stream",
        )
        assert att.mime_type == "application/octet-stream"

    def test_post_init_image_mime_from_webp(self) -> None:
        att = Attachment(path="/tmp/img.webp", name="img.webp", content="x", size=1)
        assert att.is_image
        assert att.mime_type == "image/webp"

    def test_post_init_jpg_detected_as_image(self) -> None:
        att = Attachment(path="/tmp/photo.jpg", name="photo.jpg", content="x", size=1)
        assert att.is_image
        assert att.mime_type == "image/jpeg"

    def test_post_init_svg_is_image(self) -> None:
        att = Attachment(path="/tmp/icon.svg", name="icon.svg", content="x", size=1)
        assert att.is_image
        # SVG is in IMAGE_EXTENSIONS
        assert att.mime_type == "image/svg+xml" or "svg" in att.mime_type

    def test_is_text_for_image(self) -> None:
        att = Attachment(path="/tmp/img.png", name="img.png", content="x", size=1)
        assert att.is_image
        assert not att.is_text

    def test_base64_content_default_none(self) -> None:
        att = Attachment(path="/tmp/f.txt", name="f.txt", content="x", size=1)
        assert att.base64_content is None


class TestInferMime:
    def test_python_file(self) -> None:
        assert Attachment._infer_mime("script.py") == "text/x-python"

    def test_typescript_file(self) -> None:
        mime = Attachment._infer_mime("component.tsx")
        assert mime is not None

    def test_markdown_file(self) -> None:
        assert Attachment._infer_mime("readme.md") == "text/markdown"

    def test_json_file(self) -> None:
        assert Attachment._infer_mime("data.json") == "application/json"

    def test_yaml_file(self) -> None:
        assert Attachment._infer_mime("config.yaml") is not None

    def test_css_file(self) -> None:
        mime = Attachment._infer_mime("style.css")
        assert mime == "text/css"

    def test_html_file(self) -> None:
        mime = Attachment._infer_mime("index.html")
        assert mime == "text/html"

    def test_rust_file(self) -> None:
        mime = Attachment._infer_mime("main.rs")
        assert mime is not None
        assert isinstance(mime, str)

    def test_go_file(self) -> None:
        mime = Attachment._infer_mime("main.go")
        assert mime is not None
        assert isinstance(mime, str)

    def test_png_image(self) -> None:
        mime = Attachment._infer_mime("image.png")
        assert mime == "image/png"

    def test_jpg_image(self) -> None:
        mime = Attachment._infer_mime("photo.jpg")
        assert mime == "image/jpeg"

    def test_webp_image(self) -> None:
        mime = Attachment._infer_mime("img.webp")
        assert mime == "image/webp"

    def test_unknown_extension(self) -> None:
        """Unknown extension should return None (no MIME guess)."""
        mime = Attachment._infer_mime("file.xyzabc")
        assert mime is None

    def test_no_extension(self) -> None:
        mime = Attachment._infer_mime("Makefile")
        assert mime is None

    def test_svg_file(self) -> None:
        mime = Attachment._infer_mime("icon.svg")
        # SVG is tricky — mimetypes returns image/svg+xml
        assert mime is not None

    def test_all_text_extensions_give_mime(self) -> None:
        """Every extension in TEXT_EXTENSIONS should return a MIME or None."""
        for ext in TEXT_EXTENSIONS:
            mime = Attachment._infer_mime(f"file{ext}")
            # Should not crash for any known extension
            assert mime is None or isinstance(mime, str)

    def test_all_image_extensions_give_mime(self) -> None:
        """Every extension in IMAGE_EXTENSIONS should return a MIME or None."""
        for ext in IMAGE_EXTENSIONS:
            mime = Attachment._infer_mime(f"file{ext}")
            assert mime is None or isinstance(mime, str)


class TestFromPath:
    def test_reads_file_content(self) -> None:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("print('hello')")
            tmp = f.name

        try:
            att = Attachment.from_path(tmp)
            assert att.content == "print('hello')"
            assert att.size == 14
            assert att.name == Path(tmp).name
            assert att.mime_type == "text/x-python"
        finally:
            Path(tmp).unlink(missing_ok=True)

    def test_reads_file_as_text(self) -> None:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("Hello, World!")
            tmp = f.name

        try:
            att = Attachment.from_path(tmp)
            assert att.content == "Hello, World!"
            assert att.size == 13
        finally:
            Path(tmp).unlink(missing_ok=True)

    def test_explicit_content_passed(self) -> None:
        """If content is explicitly provided, from_path should not read the file."""
        att = Attachment.from_path("/nonexistent/file.py", content="explicit")
        assert att.content == "explicit"
        assert att.size == 8

    def test_from_path_detects_image_by_extension(self) -> None:
        """from_path should set is_image based on extension even without reading."""
        att = Attachment.from_path("/tmp/photo.png", content="fake_png_data")
        assert att.is_image
        assert not att.is_text
        assert att.mime_type == "image/png"

    def test_from_path_text_file_not_image(self) -> None:
        att = Attachment.from_path("/tmp/doc.txt", content="text")
        assert not att.is_image
        assert att.is_text

    def test_from_path_unknown_extension_defaults_to_text(self) -> None:
        """Files with unknown extensions should still be treated as text."""
        att = Attachment.from_path("/tmp/file.xyzabc", content="data")
        assert not att.is_image
        assert att.is_text

    def test_from_path_resolves_absolute_path(self) -> None:
        att = Attachment.from_path("/tmp/test.py", content="x")
        assert att.path.startswith("/")


class TestEdgeCases:
    def test_empty_content(self) -> None:
        att = Attachment(path="/tmp/empty.txt", name="empty.txt", content="", size=0)
        assert att.content == ""
        assert att.size == 0
        assert not att.is_image
        assert att.is_text

    def test_unicode_content(self) -> None:
        content = "你好世界 👋"
        att = Attachment(path="/tmp/hello.txt", name="hello.txt", content=content, size=len(content))
        assert att.content == content

    def test_long_path(self) -> None:
        long_path = "/a/" + "/".join("x" * 10 for _ in range(10)) + "/file.txt"
        att = Attachment(path=long_path, name="file.txt", content="x", size=1)
        assert att.name == "file.txt"

    def test_post_init_jpeg_variants(self) -> None:
        for ext in (".jpeg", ".jpg", ".jpe"):
            name = f"photo{ext}"
            att = Attachment(path=f"/tmp/{name}", name=name, content="x", size=1)
            assert att.is_image
            assert att.mime_type.startswith("image/jpeg") or att.mime_type.startswith("image/jpe")
