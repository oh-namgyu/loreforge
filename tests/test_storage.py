import json
import threading
import time
from pathlib import Path

import pytest

from core.storage import BibleMissing, BookNotFound, Storage, StorageError, slugify


@pytest.fixture()
def store(tmp_path: Path) -> Storage:
    return Storage(tmp_path / "data")


def test_roundtrip(store: Storage) -> None:
    book = store.create_book("A Lonely Lighthouse Keeper", style="noir", density=8)
    assert book["slug"] == "a-lonely-lighthouse-keeper"
    assert book["status"] == "empty" and book["bible"] is None
    assert book["schema"] == 1 and book["density"] == 8 and book["lang"] == "en"

    loaded = store.load_book(book["slug"])
    assert loaded["concept"] == "A Lonely Lighthouse Keeper"
    assert [s["slug"] for s in store.list_books()] == [book["slug"]]


def test_slug_dedupe_and_fallback(store: Storage) -> None:
    first = store.create_book("Same Concept")
    second = store.create_book("Same Concept")
    third = store.create_book("Same Concept")
    assert [first["slug"], second["slug"], third["slug"]] == [
        "same-concept",
        "same-concept-2",
        "same-concept-3",
    ]
    assert slugify("....") == "book"
    assert store.create_book("!!!")["slug"] == "book"


@pytest.mark.parametrize("bad", ["../x", "a/b", "Uppercase", "x" * 65, "", "a b", ".."])
def test_slug_rejected(store: Storage, bad: str) -> None:
    with pytest.raises(ValueError):
        store.book_dir(bad)
    with pytest.raises(ValueError):
        store.load_book(bad)


def test_create_validation(store: Storage) -> None:
    for kwargs in (
        {"concept": ""},
        {"concept": "x" * 4001},
        {"concept": 5},
        {"concept": "ok", "density": 7},
        {"concept": "ok", "lang": "fr"},
    ):
        with pytest.raises(ValueError):
            store.create_book(**kwargs)


def test_atomic_write_leaves_no_tmp_and_rotates_bak(store: Storage) -> None:
    book = store.create_book("Rotate Me")
    slug = book["slug"]
    book["bible"] = {"name": "First"}
    store.save_book(slug, book)
    book["bible"] = {"name": "Second"}
    store.save_book(slug, book)

    folder = store.book_dir(slug)
    assert not list(folder.glob("*.tmp"))
    assert json.loads((folder / "book.json").read_text())["bible"]["name"] == "Second"
    assert json.loads((folder / "book.json.bak").read_text())["bible"]["name"] == "First"


def test_corrupted_book_recovers_from_bak(store: Storage) -> None:
    book = store.create_book("Corrupt Me")
    slug = book["slug"]
    book["bible"] = {"name": "Good"}
    store.save_book(slug, book)
    store.save_book(slug, book)  # ensure a .bak exists

    (store.book_dir(slug) / "book.json").write_text("{not json", encoding="utf-8")
    recovered = store.load_book(slug)
    assert recovered["recovered"] is True
    assert recovered["bible"]["name"] == "Good"
    assert store.list_books()[0]["recovered"] is True

    # a rewrite drops the transient recovered flag from disk
    store.save_book(slug, recovered)
    on_disk = json.loads((store.book_dir(slug) / "book.json").read_text())
    assert "recovered" not in on_disk


def test_corrupted_without_backup_raises(store: Storage) -> None:
    slug = store.create_book("No Backup")["slug"]
    (store.book_dir(slug) / "book.json").write_text("]]]", encoding="utf-8")
    with pytest.raises(StorageError):
        store.load_book(slug)


def test_missing_book(store: Storage) -> None:
    with pytest.raises(BookNotFound):
        store.load_book("ghost")


def test_update_bible_requires_bible(store: Storage) -> None:
    slug = store.create_book("Needs Bible")["slug"]
    with pytest.raises(BibleMissing):
        store.update_bible(slug, {"name": "X"})

    book = store.load_book(slug)
    book["bible"] = {"name": "X", "world": "old"}
    store.save_book(slug, book)
    merged = store.update_bible(slug, {"world": "new"})
    assert merged["bible"] == {"name": "X", "world": "new"}


def test_concurrent_writes_serialize(store: Storage) -> None:
    slug = store.create_book("Race")["slug"]
    book = store.load_book(slug)
    book["bible"] = {"name": "base", "counter": 0}
    store.save_book(slug, book)

    errors: list[Exception] = []

    def bump(field: str, times: int) -> None:
        try:
            for i in range(times):
                store.update_bible(slug, {field: i, "counter": i})
        except Exception as exc:  # pragma: no cover - surfaced via assert
            errors.append(exc)

    threads = [
        threading.Thread(target=bump, args=("alpha", 40)),
        threading.Thread(target=bump, args=("beta", 40)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert not errors
    final = store.load_book(slug)
    assert "recovered" not in final  # file never corrupt
    assert final["bible"]["alpha"] == 39 and final["bible"]["beta"] == 39
    assert final["bible"]["name"] == "base"


def test_delete_moves_to_trash_and_purge_expires(store: Storage) -> None:
    slug = store.create_book("Trash Me")["slug"]
    name = store.delete_book(slug)
    assert not store.book_dir(slug).exists()
    assert (store.trash_dir / name).is_dir()
    with pytest.raises(BookNotFound):
        store.delete_book(slug)

    old = store.trash_dir / f"stale-{int(time.time()) - 8 * 86400}"
    old.mkdir()
    (old / "book.json").write_text("{}", encoding="utf-8")

    assert store.purge_trash(days=7) == 1
    assert not old.exists()
    assert (store.trash_dir / name).is_dir()

    assert store.purge_trash(days=0) == 1
    assert not (store.trash_dir / name).exists()
