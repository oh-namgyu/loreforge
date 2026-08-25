"""Standalone HTML export: one self-contained dossier file.

No scripts, no external references — the stylesheet is inline and images are
base64 data URIs, so the file opens from `file://` and survives being forwarded
as an attachment. Every dynamic string goes through html.escape, and the only
inline style is a palette swatch colour that matched #RRGGBB first.
"""

from __future__ import annotations

import base64
from html import escape
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .bible import HEX_RE
from .images import IMAGE_KINDS
from .storage import utcnow

CSS = """:root { color-scheme: light; }
* { box-sizing: border-box; }
body { margin: 0; padding: 32px 20px; background: #ffffff; color: #1b1d22;
  font: 15px/1.6 system-ui, -apple-system, "Segoe UI", sans-serif; }
.wrap { max-width: 860px; margin: 0 auto; }
h1 { margin: 0 0 6px; font-size: 26px; }
h2 { margin: 0 0 12px; font-size: 12px; letter-spacing: 0.08em;
  text-transform: uppercase; color: #6b7280; }
p { margin: 0 0 10px; white-space: pre-wrap; }
.meta { display: flex; flex-wrap: wrap; gap: 8px; margin: 12px 0 28px; }
.chip { padding: 3px 10px; border: 1px solid #d8dbe2; border-radius: 999px;
  font-size: 12px; color: #4b5563; }
.section { margin: 0 0 26px; padding-top: 18px; border-top: 1px solid #e4e6eb; }
.pairs { display: grid; grid-template-columns: 150px minmax(0, 1fr); gap: 6px 16px; margin: 0; }
.pairs dt { color: #6b7280; font-size: 13px; }
.pairs dd { margin: 0; }
table { width: 100%; border-collapse: collapse; }
th, td { padding: 8px; text-align: left; vertical-align: top;
  border-bottom: 1px solid #e4e6eb; }
th { font-size: 12px; letter-spacing: 0.06em; text-transform: uppercase; color: #6b7280; }
.palette { display: flex; flex-wrap: wrap; gap: 14px; }
.color { font-size: 12px; color: #4b5563; text-align: center; }
.swatch { width: 72px; height: 46px; border: 1px solid #d8dbe2; border-radius: 6px; }
.hex { display: block; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
pre { margin: 0; padding: 14px; border: 1px solid #e4e6eb; border-radius: 8px;
  background: #f6f7f9; white-space: pre-wrap; word-break: break-word;
  font: 13px/1.5 ui-monospace, SFMono-Regular, Menlo, monospace; }
figure { margin: 0 0 18px; }
img { display: block; max-width: 100%; height: auto; border: 1px solid #e4e6eb;
  border-radius: 8px; }
figcaption { margin-top: 6px; font-size: 12px; color: #6b7280; }
.foot { margin-top: 28px; padding-top: 14px; border-top: 1px solid #e4e6eb;
  font-size: 12px; color: #9099a8; }
@media print { body { padding: 0; } .section { break-inside: avoid; } }"""


def esc(value: Any) -> str:
    return escape("" if value is None else str(value), quote=True)


def _section(title: str, inner: str) -> str:
    return f'<section class="section"><h2>{esc(title)}</h2>{inner}</section>' if inner else ""


def _prose(title: str, text: Any) -> str:
    return _section(title, f"<p>{esc(text)}</p>" if str(text or "").strip() else "")


def _pairs(title: str, items: Iterable[Tuple[str, Any]]) -> str:
    rows = "".join(
        f"<dt>{esc(key)}</dt><dd>{esc(value)}</dd>"
        for key, value in items
        if str(value or "").strip()
    )
    return _section(title, f'<dl class="pairs">{rows}</dl>' if rows else "")


def _profile(bible: Dict[str, Any]) -> str:
    profile = bible.get("profile") if isinstance(bible.get("profile"), dict) else {}
    traits = profile.get("traits")
    items: List[Tuple[str, Any]] = [
        ("Age", profile.get("age")),
        ("Role", profile.get("role")),
        ("Body", profile.get("body")),
        ("Traits", ", ".join(str(t) for t in traits) if isinstance(traits, list) else ""),
    ]
    return _pairs("Profile", items)


def _voice(bible: Dict[str, Any]) -> str:
    voice = bible.get("voice") if isinstance(bible.get("voice"), dict) else {}
    return _pairs("Voice", [("Personality", voice.get("personality")), ("Speech", voice.get("speech"))])


def _lines(bible: Dict[str, Any]) -> str:
    rows = "".join(
        f"<tr><td>{esc(item.get('situation'))}</td><td>{esc(item.get('line'))}</td></tr>"
        for item in bible.get("lines") or []
        if isinstance(item, dict)
    )
    if not rows:
        return ""
    head = "<tr><th>Situation</th><th>Line</th></tr>"
    return _section("Signature Lines", f"<table>{head}{rows}</table>")


def _palette(bible: Dict[str, Any]) -> str:
    chips = []
    for color in bible.get("palette") or []:
        if not isinstance(color, dict):
            continue
        hex_value = color.get("hex")
        # the only inline style in the document, and only for a validated colour
        style = (
            f' style="background-color: {esc(hex_value)}"'
            if isinstance(hex_value, str) and HEX_RE.match(hex_value)
            else ""
        )
        chips.append(
            f'<div class="color"><div class="swatch"{style}></div>{esc(color.get("name"))}'
            f'<span class="hex">{esc(hex_value)}</span></div>'
        )
    return _section("Palette", f'<div class="palette">{"".join(chips)}</div>' if chips else "")


def _images(images: Optional[Dict[str, bytes]]) -> str:
    figures = []
    for kind in IMAGE_KINDS:
        data = (images or {}).get(kind)
        if not data:
            continue
        uri = "data:image/png;base64," + base64.b64encode(data).decode("ascii")
        figures.append(
            f'<figure><img src="{uri}" alt="{esc(kind)} render">'
            f"<figcaption>{esc(kind)}</figcaption></figure>"
        )
    return _section("Board", "".join(figures))


def _header(book: Dict[str, Any], bible: Dict[str, Any], generated: str) -> str:
    chips = [
        ("style", book.get("style")),
        ("status", book.get("status")),
        ("sections", book.get("density")),
        ("language", book.get("lang")),
        ("exported", generated),
    ]
    meta = "".join(
        f'<span class="chip">{esc(label)}: {esc(value)}</span>'
        for label, value in chips
        if str(value or "").strip()
    )
    return (
        f"<h1>{esc(bible.get('name') or book.get('slug'))}</h1>"
        f"<p>{esc(book.get('concept'))}</p>"
        f'<div class="meta">{meta}</div>'
    )


def render_export(book: Dict[str, Any], images: Optional[Dict[str, bytes]] = None) -> str:
    """One HTML document for this book. `images` maps kind -> PNG bytes."""
    bible = book.get("bible") if isinstance(book.get("bible"), dict) else {}
    generated = utcnow()
    body = "".join(
        [
            _header(book, bible, generated),
            _profile(bible),
            _prose("Background", bible.get("background")),
            _voice(bible),
            _lines(bible),
            _palette(bible),
            _prose("World", bible.get("world")),
            _section("Master Prompt", f"<pre>{esc(bible.get('master_prompt'))}</pre>"),
            _images(images),
            f'<p class="foot">Exported from loreforge on {esc(generated)}.</p>',
        ]
    )
    title = esc(bible.get("name") or book.get("slug") or "lorebook")
    return (
        '<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>{title} — loreforge</title>\n<style>\n{CSS}\n</style>\n</head>\n"
        f'<body>\n<div class="wrap">{body}</div>\n</body>\n</html>\n'
    )
