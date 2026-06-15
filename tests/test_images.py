from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from cscode.core.images import ImageAttachment, resize_image, image_to_base64, process_image_file


class TestImageAttachment:
    def test_create_attachment(self) -> None:
        att = ImageAttachment(path="/tmp/test.png", mime_type="image/png", data_uri="data:image/png;base64,abc")
        assert att.path == "/tmp/test.png"
        assert att.mime_type == "image/png"
        assert att.data_uri == "data:image/png;base64,abc"


class TestImageProcessing:
    def test_image_to_base64_no_file(self) -> None:
        result = image_to_base64("/nonexistent/file.png")
        assert result is None

    def test_process_nonexistent(self) -> None:
        result = process_image_file("/nonexistent/file.png")
        assert result is None

    def test_process_text_file(self) -> None:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("not an image")
            f.flush()
            result = process_image_file(f.name)
            assert result is None
            Path(f.name).unlink(missing_ok=True)

    def test_process_image_file(self) -> None:
        try:
            from PIL import Image as PILImage
            import io

            img = PILImage.new("RGB", (100, 50), color="red")
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            buf.seek(0)

            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
                f.write(buf.read())
                f.flush()

                result = process_image_file(f.name)
                assert result is not None
                assert result.mime_type == "image/png"
                assert result.data_uri.startswith("data:image/png;base64,")
                assert result.path == f.name

                Path(f.name).unlink(missing_ok=True)
        except ImportError:
            pytest.skip("Pillow not available")
