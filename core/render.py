"""Board rendering: prompt derivation, one call per kind, board[] upsert.

Every kind is an independent call. A kind that fails is reported and skipped;
the others still land. When nothing lands at all the book file is not rewritten,
so a total failure leaves the last good state byte for byte.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List

from .images import IMAGE_KINDS, is_png, write_image
from .providers import NoProvider, ProviderError
from .storage import BibleMissing, Storage, utcnow

DEFAULT_KINDS = ("board",)
SIZES = {"board": "1536x1024", "solo": "1024x1536"}
SOLO_INSTRUCTION = (
    "\n\nOverride the board layout described above: render ONE single full-body "
    "character render instead — the character head to toe, centred, on a plain "
    "neutral background. No panels, no grid, no labels, no text. Keep the same "
    "character design, outfit and palette."
)


def normalise_kinds(value: Any) -> List[str]:
    """Accept a kinds list from a request body; default to the board alone."""
    if value is None:
        return list(DEFAULT_KINDS)
    if not isinstance(value, list):
        raise ValueError("kinds must be an array")
    kinds: List[str] = []
    for kind in value:
        if kind not in IMAGE_KINDS:
            raise ValueError(f"unknown image kind: {kind!r}")
        if kind not in kinds:
            kinds.append(kind)
    if not kinds:
        raise ValueError("kinds must not be empty")
    return kinds


def prompt_for(kind: str, bible: Dict[str, Any]) -> str:
    """The board uses the master prompt as written; solo derives from it."""
    master = bible.get("master_prompt")
    if not isinstance(master, str) or not master.strip():
        raise ValueError("bible has no master_prompt to render")
    master = master.strip()
    return master if kind == "board" else master + SOLO_INSTRUCTION


def _call(provider: Any, kind: str, bible: Dict[str, Any]) -> bytes:
    data = provider.render(prompt_for(kind, bible), SIZES[kind])
    if not is_png(data):
        raise ProviderError(f"{kind}: provider did not return a PNG")
    return data


def _saver(rendered: List[str], stamp: str) -> Callable[[Dict[str, Any]], None]:
    """Upsert one entry per rendered kind; status only ever moves forward."""

    def apply(book: Dict[str, Any]) -> None:
        board = [
            entry
            for entry in book.get("board") or []
            if isinstance(entry, dict) and entry.get("kind") not in rendered
        ]
        board.extend(
            {"file": f"{kind}.png", "kind": kind, "rendered_at": stamp}
            for kind in rendered
        )
        book["board"] = board
        if any(entry.get("kind") == "board" for entry in board):
            book["status"] = "rendered"

    return apply


def render_book(
    store: Storage, provider: Any, slug: str, kinds: List[str]
) -> Dict[str, Any]:
    """Render the requested kinds. Partial success is a success with `failed` set."""
    book = store.load_book(slug)
    bible = book.get("bible")
    if not isinstance(bible, dict):
        raise BibleMissing(slug)
    rendered: List[str] = []
    failed: List[Dict[str, Any]] = []
    for kind in kinds:
        try:
            data = _call(provider, kind, bible)
        except NoProvider:
            raise
        except ProviderError as err:
            failed.append({"kind": kind, "error": str(err), "retryable": err.retryable})
            continue
        except Exception as err:  # an adapter defect must not corrupt the book
            failed.append(
                {"kind": kind, "error": f"{type(err).__name__}: {err}", "retryable": False}
            )
            continue
        write_image(store.book_dir(slug), kind, data)
        rendered.append(kind)
    if rendered:
        book = store.mutate_book(slug, _saver(rendered, utcnow()))
    return {"rendered": rendered, "failed": failed, "book": book}
