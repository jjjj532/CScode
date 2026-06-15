from __future__ import annotations

import base64
from dataclasses import dataclass
from pathlib import Path

from cscode.utils.logging import get_logger

logger = get_logger(__name__)

MAX_DIMENSION = 2048
MAX_SIZE_BYTES = 5 * 1024 * 1024

SUPPORTED_MIME_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
}


@dataclass
class ImageAttachment:
    path: str
    mime_type: str
    data_uri: str


def image_to_base64(path: str) -> str | None:
    try:
        p = Path(path)
        if not p.exists():
            return None
        suffix = p.suffix.lower()
        mime = SUPPORTED_MIME_TYPES.get(suffix)
        if mime is None:
            return None
        data = p.read_bytes()
        encoded = base64.b64encode(data).decode("utf-8")
        return f"data:{mime};base64,{encoded}"
    except Exception as e:
        logger.warning("Failed to encode image %s: %s", path, e)
        return None


def resize_image(path: str, max_dim: int = MAX_DIMENSION) -> str | None:
    from PIL import Image

    try:
        img = Image.open(path)
        if max(img.size) <= max_dim:
            return path

        ratio = max_dim / max(img.size)
        new_size = (int(img.width * ratio), int(img.height * ratio))
        resized = img.resize(new_size, Image.Resampling.LANCZOS)

        p = Path(path)
        temp_path = str(p.parent / f".resized_{p.name}")
        resized.save(temp_path, quality=85)
        return temp_path
    except Exception as e:
        logger.warning("Failed to resize image %s: %s", path, e)
        return path


def process_image_file(path: str) -> ImageAttachment | None:
    try:
        p = Path(path)
        if not p.exists():
            logger.warning("Image file not found: %s", path)
            return None

        suffix = p.suffix.lower()
        mime = SUPPORTED_MIME_TYPES.get(suffix)
        if mime is None:
            logger.debug("Unsupported image format: %s", suffix)
            return None

        processed = resize_image(path)

        data_uri = image_to_base64(processed or path)
        if data_uri is None:
            return None

        if processed != path and processed is not None:
            Path(processed).unlink(missing_ok=True)

        return ImageAttachment(
            path=str(p),
            mime_type=mime,
            data_uri=data_uri,
        )
    except Exception as e:
        logger.warning("Failed to process image %s: %s", path, e)
        return None


def is_image_file(path: str) -> bool:
    suffix = Path(path).suffix.lower()
    return suffix in SUPPORTED_MIME_TYPES
