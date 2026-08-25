"""Offline providers used by browser tests (LOREFORGE_FAKE_LLM=1).

They make no network call and need no API key. The text fake echoes the concept
back inside a schema-valid bible so an end-to-end run can exercise the whole
generate flow — including hostile concept text, which must survive as literal
characters. The image fake returns a real, tiny PNG so the gallery has something
a browser will actually decode.
"""

from __future__ import annotations

import json
import struct
import zlib
from typing import Any, Dict, List, Tuple

NAME_LIMIT = 60
PALETTE = [
    {"hex": "#2f3a4f", "name": "slate"},
    {"hex": "#c8a165", "name": "brass"},
    {"hex": "#7c9cff", "name": "signal blue"},
    {"hex": "#e6e8ef", "name": "paper"},
]
SITUATIONS = ("greeting", "under pressure", "at rest", "in a fight", "farewell")
FAKE_PNG_SIZE = 64
FAKE_PNG_COLOR = (47, 58, 79)


def concept_of(user: str) -> str:
    """Recover the concept from the prompt built by core.bible.build_prompt."""
    head = user.split("\nArt style:", 1)[0]
    return head.partition("Concept: ")[2].strip() or "unnamed"


def fake_bible(concept: str) -> Dict[str, Any]:
    lines: List[Dict[str, str]] = [
        {"situation": situation, "line": f"[{situation}] {concept}"}
        for situation in SITUATIONS
    ]
    return {
        "name": concept[:NAME_LIMIT],
        "profile": {
            "age": "29",
            "role": "protagonist",
            "body": "lean, road-worn, a hand's width taller than most",
            "traits": ["curious", "stubborn", "quietly funny"],
        },
        "background": f"{concept} — three winters on the road left more debts than stories.",
        "voice": {
            "personality": "wry and watchful, slow to trust",
            "speech": "short sentences, no wasted words",
        },
        "lines": lines,
        "palette": [dict(color) for color in PALETTE],
        "world": f"A world shaped around {concept}: trade routes, thin law, long memory.",
        "master_prompt": (
            f"Character sheet grid for: {concept}. Six labelled sections — full body, "
            "three expressions, held prop, outfit detail. Muted slate and brass palette."
        ),
    }


def _chunk(tag: bytes, data: bytes) -> bytes:
    crc = zlib.crc32(tag + data) & 0xFFFFFFFF
    return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", crc)


def fake_png(size: int = FAKE_PNG_SIZE, color: Tuple[int, int, int] = FAKE_PNG_COLOR) -> bytes:
    """A deterministic solid-colour truecolour PNG, built with the stdlib alone."""
    header = struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0)
    scanline = b"\x00" + bytes(color) * size
    return (
        b"\x89PNG\r\n\x1a\n"
        + _chunk(b"IHDR", header)
        + _chunk(b"IDAT", zlib.compress(scanline * size, 9))
        + _chunk(b"IEND", b"")
    )


class FakeText:
    """Same interface as core.llm.AnthropicText, without the provider."""

    def generate(self, system: str, user: str) -> str:
        return json.dumps(fake_bible(concept_of(user)), ensure_ascii=False)


class FakeImage:
    """Same interface as core.providers.openai_image.OpenAIImage, without the provider."""

    def render(self, prompt: str, size: str = "") -> bytes:
        return fake_png()
