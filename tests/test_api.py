import json
from pathlib import Path

import pytest

from app import create_app
from core.storage import Storage


@pytest.fixture()
def app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("LOREFORGE_DATA", str(tmp_path / "data"))
    application = create_app()
    application.config.update(TESTING=True)
    return application


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def store(app) -> Storage:
    return app.config["STORAGE"]


def body(res) -> dict:
    return json.loads(res.data)


def make_book(client, concept: str = "Wandering Tea Merchant", **extra) -> str:
    res = client.post("/api/books", json={"concept": concept, **extra})
    assert res.status_code == 201
    return body(res)["data"]["slug"]


def test_env_data_dir_used(app, tmp_path: Path) -> None:
    assert app.config["STORAGE"].root == (tmp_path / "data").resolve()


def test_index_serves_shell(client) -> None:
    res = client.get("/")
    assert res.status_code == 200
    assert b"loreforge" in res.data
    assert "default-src 'self'" in res.headers["Content-Security-Policy"]


def test_list_empty_envelope(client) -> None:
    res = client.get("/api/books")
    assert res.status_code == 200
    assert body(res) == {"ok": True, "data": []}


def test_create_and_get(client) -> None:
    slug = make_book(client, "Wandering Tea Merchant", style="ukiyo-e", density=8, lang="ko")
    assert slug == "wandering-tea-merchant"

    res = client.get(f"/api/books/{slug}")
    assert res.status_code == 200
    data = body(res)["data"]
    assert data["schema"] == 1 and data["status"] == "empty" and data["bible"] is None
    assert data["style"] == "ukiyo-e" and data["density"] == 8 and data["lang"] == "ko"

    listed = body(client.get("/api/books"))["data"]
    assert len(listed) == 1 and listed[0]["slug"] == slug
    assert "bible" not in listed[0]


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"concept": ""},
        {"concept": "   "},
        {"concept": "x" * 4001},
        {"concept": "ok", "density": 7},
        {"concept": "ok", "lang": "jp"},
        {"concept": 12},
    ],
)
def test_create_bad_request(client, payload: dict) -> None:
    res = client.post("/api/books", json=payload)
    assert res.status_code == 400
    assert body(res)["ok"] is False and body(res)["error"]


def test_create_rejects_non_object_body(client) -> None:
    res = client.post("/api/books", json=["nope"])
    assert res.status_code == 400


@pytest.mark.parametrize("slug", ["..", "Upper", "x" * 65, "sp ace"])
def test_bad_slug_is_400(client, slug: str) -> None:
    assert client.get(f"/api/books/{slug}").status_code == 400


def test_path_traversal_rejected(client, tmp_path: Path) -> None:
    # encoded separators never reach the handler (routing 404), plain ones fail slug validation
    for path in ("/api/books/../../etc", "/api/books/a/b", "/api/books/..%2Fx"):
        assert client.get(path).status_code in (400, 404)
    assert client.get("/api/books/..").status_code == 400
    assert client.delete("/api/books/..").status_code == 400
    assert list((tmp_path / "data" / "books").iterdir()) == []


def test_missing_book_404(client) -> None:
    res = client.get("/api/books/ghost")
    assert res.status_code == 404 and body(res) == {"ok": False, "error": "book not found"}
    assert client.delete("/api/books/ghost").status_code == 404


def test_unknown_api_route_and_method(client) -> None:
    assert client.get("/api/nope").status_code == 404
    assert body(client.get("/api/nope"))["ok"] is False
    res = client.put("/api/books")
    assert res.status_code == 405 and body(res)["ok"] is False


def test_patch_bible_conflict_then_merge(client, store: Storage) -> None:
    slug = make_book(client)
    res = client.patch(f"/api/books/{slug}/bible", json={"name": "Rin"})
    assert res.status_code == 409 and body(res)["ok"] is False

    book = store.load_book(slug)
    book["bible"] = {"name": "Rin", "world": "old", "lines": []}
    book["status"] = "draft"
    store.save_book(slug, book)

    res = client.patch(f"/api/books/{slug}/bible", json={"world": "new"})
    assert res.status_code == 200
    bible = body(res)["data"]["bible"]
    assert bible == {"name": "Rin", "world": "new", "lines": []}
    assert store.load_book(slug)["bible"]["world"] == "new"

    assert client.patch(f"/api/books/{slug}/bible", json={}).status_code == 400
    assert client.patch("/api/books/ghost/bible", json={"a": 1}).status_code == 404


def test_delete_moves_to_trash(client, store: Storage) -> None:
    slug = make_book(client)
    res = client.delete(f"/api/books/{slug}")
    assert res.status_code == 200 and body(res)["data"]["slug"] == slug
    assert body(client.get("/api/books"))["data"] == []
    trashed = list(store.trash_dir.iterdir())
    assert len(trashed) == 1 and trashed[0].name.startswith(f"{slug}-")


def test_summary_carries_name_and_palette(client, store: Storage) -> None:
    slug = make_book(client)
    book = store.load_book(slug)
    book["bible"] = {"name": "Rin", "palette": [{"hex": "#112233", "name": "ink"}]}
    book["status"] = "draft"
    store.save_book(slug, book)

    summary = body(client.get("/api/books"))["data"][0]
    assert summary["name"] == "Rin"
    assert summary["palette"] == [{"hex": "#112233", "name": "ink"}]
    assert summary["status"] == "draft"


def test_summary_without_bible_has_empty_hints(client) -> None:
    make_book(client)
    summary = body(client.get("/api/books"))["data"][0]
    assert summary["name"] is None and summary["palette"] is None


def test_dedupe_slugs_via_api(client) -> None:
    assert make_book(client, "Same Name") == "same-name"
    assert make_book(client, "Same Name") == "same-name-2"
