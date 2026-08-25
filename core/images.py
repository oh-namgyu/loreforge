"""Book images on disk: kind whitelist, atomic write, byte reads.

Files live next to book.json as `<kind>.png`. Callers pass a book directory
obtained from Storage.book_dir, which is where slug validation happens.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Dict

IMAGE_KINDS = ("board", "solo")
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def validate_kind(kind: str) -> str:
    if kind not in IMAGE_KINDS:
        raise ValueError("invalid image kind")
    return kind


def image_path(book_dir: Path, kind: str) -> Path:
    return book_dir / f"{validate_kind(kind)}.png"


def is_png(data: object) -> bool:
    return isinstance(data, bytes) and data.startswith(PNG_SIGNATURE)


def write_image(book_dir: Path, kind: str, data: bytes) -> str:
    """Write via tmp + os.replace, the same rule book.json follows."""
    path = image_path(book_dir, kind)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".png.tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)
    return path.name


def read_images(book_dir: Path) -> Dict[str, bytes]:
    """Every rendered image of this book, keyed by kind. Missing kinds are skipped."""
    found: Dict[str, bytes] = {}
    for kind in IMAGE_KINDS:
        path = image_path(book_dir, kind)
        try:
            found[kind] = path.read_bytes()
        except OSError:
            continue
    return found
