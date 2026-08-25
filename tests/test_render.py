"""Render endpoint: partial failure, idempotent upsert, status transitions."""

import json
from pathlib import Path
from typing import List

import pytest

from app import create_app
from core.fake_llm import fake_bible, fake_png
from core.providers import NoProvider, ProviderError
from core.render import SOLO_INSTRUCTION
from core.storage import Storage

CONCEPT = "Wandering Tea Merchant"
SOLO_MARK = SOLO_INSTRUCTION.strip()[:40]


class RecordingImage:
    """Fake provider that logs its calls and fails the kinds it was told to fail."""

    def __init__(self, fail_solo: bool = False, fail_board: bool = False) -> None:
        self.calls: List[tuple] = []
        self.fail_solo = fail_solo
        self.fail_board = fail_board

    def render(self, prompt: str, size: str) -> bytes:
        self.calls.append((prompt, size))
        solo = SOLO_MARK in prompt
        if (solo and self.fail_solo) or (not solo and self.fail_board):
            raise ProviderError("provider said no", retryable=True)
        return fake_png()


def build(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, provider: object):
    monkeypatch.setenv("LOREFORGE_DATA", str(tmp_path / "data"))
    monkeypatch.setenv("LOREFORGE_FAKE_LLM", "1")
    app = create_app(image=provider)
    app.config.update(TESTING=True)
    return app.test_client()


def body(res) -> dict:
    return json.loads(res.data)


def store_of(client) -> Storage:
    return client.application.config["STORAGE"]


def seeded(client, status: str = "draft") -> str:
    """A book with a valid bible in place, ready to render."""
    slug = body(client.post("/api/books", json={"concept": CONCEPT}))["data"]["slug"]
    store = store_of(client)
    book = store.load_book(slug)
    book["bible"] = fake_bible(CONCEPT)
    book["status"] = status
    store.save_book(slug, book)
    return slug


def test_render_board_only(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    provider = RecordingImage()
    client = build(tmp_path, monkeypatch, provider)
    slug = seeded(client)

    res = client.post(f"/api/books/{slug}/render", json={})
    assert res.status_code == 200 and body(res)["ok"] is True
    data = body(res)["data"]
    assert data["rendered"] == ["board"] and data["failed"] == []
    assert data["book"]["status"] == "rendered"
    entry = data["book"]["board"][0]
    assert entry["file"] == "board.png" and entry["kind"] == "board" and entry["rendered_at"]
    assert len(provider.calls) == 1 and provider.calls[0][1] == "1536x1024"

    book_dir = store_of(client).book_dir(slug)
    assert (book_dir / "board.png").read_bytes() == fake_png()
    assert not (book_dir / "solo.png").exists()


def test_render_board_and_solo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    provider = RecordingImage()
    client = build(tmp_path, monkeypatch, provider)
    slug = seeded(client)

    data = body(client.post(f"/api/books/{slug}/render", json={"kinds": ["board", "solo"]}))["data"]
    assert data["rendered"] == ["board", "solo"] and data["failed"] == []
    assert [entry["kind"] for entry in data["book"]["board"]] == ["board", "solo"]
    assert [call[1] for call in provider.calls] == ["1536x1024", "1024x1536"]
    assert SOLO_MARK in provider.calls[1][0]


def test_partial_failure_keeps_the_good_image(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    client = build(tmp_path, monkeypatch, RecordingImage(fail_solo=True))
    slug = seeded(client)

    res = client.post(f"/api/books/{slug}/render", json={"kinds": ["board", "solo"]})
    assert res.status_code == 200 and body(res)["ok"] is True
    data = body(res)["data"]
    assert data["rendered"] == ["board"]
    assert data["failed"] == [{"kind": "solo", "error": "provider said no", "retryable": True}]
    assert data["book"]["status"] == "rendered"
    assert [entry["kind"] for entry in data["book"]["board"]] == ["board"]

    book_dir = store_of(client).book_dir(slug)
    assert (book_dir / "board.png").is_file() and not (book_dir / "solo.png").exists()


def test_total_failure_leaves_book_json_untouched(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = build(tmp_path, monkeypatch, RecordingImage(fail_board=True, fail_solo=True))
    slug = seeded(client)
    store = store_of(client)
    before = store.book_file(slug).read_bytes()

    res = client.post(f"/api/books/{slug}/render", json={"kinds": ["board", "solo"]})
    assert res.status_code == 200
    data = body(res)["data"]
    assert data["rendered"] == [] and len(data["failed"]) == 2
    assert data["book"]["status"] == "draft" and data["book"]["board"] == []
    assert store.book_file(slug).read_bytes() == before
    assert list(store.book_dir(slug).glob("*.png")) == []


def test_adapter_defect_is_reported_not_raised(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class BrokenImage:
        def render(self, prompt: str, size: str) -> bytes:
            raise RuntimeError("adapter defect")

    client = build(tmp_path, monkeypatch, BrokenImage())
    slug = seeded(client)
    before = store_of(client).book_file(slug).read_bytes()

    data = body(client.post(f"/api/books/{slug}/render"))["data"]
    assert data["failed"] == [
        {"kind": "board", "error": "RuntimeError: adapter defect", "retryable": False}
    ]
    assert store_of(client).book_file(slug).read_bytes() == before


def test_non_png_payload_is_a_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    class TextImage:
        def render(self, prompt: str, size: str) -> bytes:
            return b"not a png"

    client = build(tmp_path, monkeypatch, TextImage())
    slug = seeded(client)
    data = body(client.post(f"/api/books/{slug}/render"))["data"]
    assert data["rendered"] == [] and data["failed"][0]["kind"] == "board"
    assert "PNG" in data["failed"][0]["error"]


def test_no_provider_is_409(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    class NoKeyImage:
        def render(self, prompt: str, size: str) -> bytes:
            raise NoProvider("OPENAI_API_KEY is not set")

    client = build(tmp_path, monkeypatch, NoKeyImage())
    slug = seeded(client)
    res = client.post(f"/api/books/{slug}/render")
    assert res.status_code == 409
    assert body(res) == {"ok": False, "error": "no-image-provider"}
    assert store_of(client).load_book(slug)["board"] == []


def test_render_rejects_missing_bible_unknown_kind_and_ghost(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = build(tmp_path, monkeypatch, RecordingImage())
    empty = body(client.post("/api/books", json={"concept": "No bible yet"}))["data"]["slug"]
    assert client.post(f"/api/books/{empty}/render").status_code == 409

    slug = seeded(client)
    assert client.post(f"/api/books/{slug}/render", json={"kinds": ["mural"]}).status_code == 400
    assert client.post("/api/books/ghost/render").status_code == 404


def test_rerender_upserts_a_single_entry(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    class TintedImage:
        def __init__(self) -> None:
            self.tint = 0

        def render(self, prompt: str, size: str) -> bytes:
            self.tint += 40
            return fake_png(color=(self.tint, 0, 0))

    client = build(tmp_path, monkeypatch, TintedImage())
    slug = seeded(client)
    book_dir = store_of(client).book_dir(slug)

    first = body(client.post(f"/api/books/{slug}/render"))["data"]["book"]
    first_bytes = (book_dir / "board.png").read_bytes()
    second = body(client.post(f"/api/books/{slug}/render"))["data"]["book"]

    assert len(first["board"]) == 1 and len(second["board"]) == 1
    assert second["board"][0]["kind"] == "board"
    assert (book_dir / "board.png").read_bytes() != first_bytes
    assert list(book_dir.glob("*.tmp")) == []


def test_status_only_moves_forward(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    client = build(tmp_path, monkeypatch, RecordingImage())

    # solo alone is not enough to call a book rendered
    slug = seeded(client)
    solo = body(client.post(f"/api/books/{slug}/render", json={"kinds": ["solo"]}))["data"]
    assert solo["book"]["status"] == "draft"

    # the board flips it, and a later solo-only render does not flip it back
    client.post(f"/api/books/{slug}/render", json={"kinds": ["board"]})
    again = body(client.post(f"/api/books/{slug}/render", json={"kinds": ["solo"]}))["data"]
    assert again["book"]["status"] == "rendered"


def test_image_endpoint_serves_and_404s(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    client = build(tmp_path, monkeypatch, RecordingImage())
    slug = seeded(client)

    missing = client.get(f"/api/books/{slug}/image/board")
    assert missing.status_code == 404 and body(missing)["ok"] is False

    client.post(f"/api/books/{slug}/render")
    res = client.get(f"/api/books/{slug}/image/board")
    assert res.status_code == 200
    assert res.mimetype == "image/png" and res.data == fake_png()
    assert client.get(f"/api/books/{slug}/image/solo").status_code == 404


@pytest.mark.parametrize("kind", ["mural", "board.png", "..", "BOARD", "../../book"])
def test_image_kind_whitelist(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    client = build(tmp_path, monkeypatch, RecordingImage())
    slug = seeded(client)
    client.post(f"/api/books/{slug}/render")
    assert client.get(f"/api/books/{slug}/image/{kind}").status_code in (400, 404)
    assert client.get("/api/books/../etc/image/board").status_code in (400, 404)


def test_home_summary_counts_renders(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    client = build(tmp_path, monkeypatch, RecordingImage())
    slug = seeded(client)
    assert body(client.get("/api/books"))["data"][0]["board_count"] == 0
    client.post(f"/api/books/{slug}/render", json={"kinds": ["board", "solo"]})
    assert body(client.get("/api/books"))["data"][0]["board_count"] == 2
