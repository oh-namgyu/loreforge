"""Standalone export: escaping, embedded images, zero external references."""

import json
import re
from pathlib import Path

import pytest

from app import create_app
from core.export import render_export
from core.fake_llm import FakeImage, fake_bible, fake_png
from core.storage import Storage

CONCEPT = "Wandering Tea Merchant"
HOSTILE = '<script>alert(1)</script> & "quoted" <img onerror=x>'
EXTERNAL_REF = re.compile(r"https?://|//[a-z0-9.-]+\.[a-z]{2,}", re.IGNORECASE)


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("LOREFORGE_DATA", str(tmp_path / "data"))
    monkeypatch.setenv("LOREFORGE_FAKE_LLM", "1")
    app = create_app(image=FakeImage())
    app.config.update(TESTING=True)
    return app.test_client()


def body(res) -> dict:
    return json.loads(res.data)


def seeded(client, concept: str = CONCEPT, **overrides) -> str:
    slug = body(client.post("/api/books", json={"concept": concept}))["data"]["slug"]
    store: Storage = client.application.config["STORAGE"]
    book = store.load_book(slug)
    book["bible"] = {**fake_bible(concept), **overrides}
    book["status"] = "draft"
    store.save_book(slug, book)
    return slug


def document(client, slug: str) -> str:
    res = client.get(f"/api/books/{slug}/export")
    assert res.status_code == 200
    return res.get_data(as_text=True)


def test_export_headers_and_shape(client) -> None:
    slug = seeded(client)
    res = client.get(f"/api/books/{slug}/export")

    assert res.status_code == 200 and res.mimetype == "text/html"
    assert res.headers["Content-Disposition"] == f'attachment; filename="{slug}-lorebook.html"'
    text = res.get_data(as_text=True)
    assert text.startswith("<!doctype html>") and text.rstrip().endswith("</html>")
    for heading in ("Profile", "Background", "Voice", "Signature Lines", "Palette", "World"):
        assert f"<h2>{heading}</h2>" in text


def test_export_carries_every_section_value(client) -> None:
    slug = seeded(client)
    bible = fake_bible(CONCEPT)
    text = document(client, slug)

    assert bible["background"] in text
    assert bible["world"] in text
    assert bible["voice"]["speech"] in text
    assert bible["lines"][0]["line"] in text
    assert bible["master_prompt"] in text
    assert "#2f3a4f" in text and "background-color: #2f3a4f" in text
    assert "<pre>" in text


def test_export_escapes_hostile_strings(client) -> None:
    slug = seeded(client, HOSTILE, name=HOSTILE, background=HOSTILE, master_prompt=HOSTILE)
    text = document(client, slug)

    # every hostile character is present, but only as text: no tag survives
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in text
    assert "&lt;img onerror=x&gt;" in text
    assert "&amp; &quot;quoted&quot;" in text
    assert "<script" not in text.lower() and "<img onerror" not in text


def test_export_has_no_external_references(client) -> None:
    slug = seeded(client)
    client.post(f"/api/books/{slug}/render", json={"kinds": ["board", "solo"]})
    text = document(client, slug)

    assert EXTERNAL_REF.search(text) is None
    assert "<link" not in text and "<script" not in text.lower()
    assert 'src="data:image/png;base64,' in text


def test_export_embeds_rendered_images_only(client) -> None:
    slug = seeded(client)
    assert document(client, slug).count("data:image/png;base64,") == 0

    client.post(f"/api/books/{slug}/render", json={"kinds": ["board"]})
    text = document(client, slug)
    assert text.count("data:image/png;base64,") == 1
    assert "<h2>Board</h2>" in text
    assert "<figcaption>board</figcaption>" in text


def test_export_needs_a_bible(client) -> None:
    slug = body(client.post("/api/books", json={"concept": "No bible yet"}))["data"]["slug"]
    assert client.get(f"/api/books/{slug}/export").status_code == 409
    assert client.get("/api/books/ghost/export").status_code == 404
    assert client.get("/api/books/../export").status_code in (400, 404)


def test_render_export_skips_broken_palette_and_lines() -> None:
    book = {
        "slug": "partial",
        "concept": "c",
        "bible": {
            "name": "Rin",
            "palette": [{"hex": "red; background:url(x)", "name": "bad"}, "junk"],
            "lines": ["junk", {"situation": "s", "line": "l"}],
            "master_prompt": "prompt",
        },
    }
    text = render_export(book)
    # a hex that fails #RRGGBB never reaches a style attribute, only the caption
    assert "background-color" not in text
    assert "red; background:url(x)" in text and 'style="' not in text
    assert "<td>s</td><td>l</td>" in text
    assert "junk" not in text


def test_render_export_takes_images_as_bytes() -> None:
    book = {"slug": "solo-only", "bible": fake_bible(CONCEPT)}
    text = render_export(book, {"solo": fake_png()})
    assert text.count("data:image/png;base64,") == 1
    assert "<figcaption>solo</figcaption>" in text
