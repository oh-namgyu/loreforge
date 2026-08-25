"""Filesystem storage for lore books: atomic writes, per-slug locks, trash."""

from __future__ import annotations

import json
import os
import re
import shutil
import threading
import time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

SCHEMA_VERSION = 1
SLUG_RE = re.compile(r"^[a-z0-9-]{1,64}$")
MAX_CONCEPT = 4000
VALID_DENSITY = (6, 8)
VALID_LANG = ("en", "ko")
SUMMARY_FIELDS = (
    "schema",
    "slug",
    "concept",
    "style",
    "density",
    "lang",
    "status",
    "created",
    "updated",
)

_locks: Dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()


class StorageError(Exception):
    """Base error for storage operations."""


class BookNotFound(StorageError):
    """Requested book does not exist."""


class BibleMissing(StorageError):
    """Book has no bible yet (generation has not run)."""


def utcnow() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def slugify(text: str) -> str:
    ascii_text = (
        unicodedata.normalize("NFKD", text or "")
        .encode("ascii", "ignore")
        .decode("ascii")
        .lower()
    )
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_text).strip("-")[:64].strip("-")
    return slug or "book"


def validate_slug(slug: Any) -> str:
    if not isinstance(slug, str) or not SLUG_RE.match(slug):
        raise ValueError("invalid slug")
    return slug


def _lock_for(key: str) -> threading.Lock:
    with _locks_guard:
        lock = _locks.get(key)
        if lock is None:
            lock = threading.Lock()
            _locks[key] = lock
        return lock


class Storage:
    """All book persistence. One instance per app; data_dir is the root."""

    def __init__(self, data_dir: os.PathLike[str] | str) -> None:
        self.root = Path(data_dir).resolve()
        self.books_dir = self.root / "books"
        self.trash_dir = self.root / ".trash"
        self.books_dir.mkdir(parents=True, exist_ok=True)
        self.trash_dir.mkdir(parents=True, exist_ok=True)

    # -- paths -----------------------------------------------------------
    def book_dir(self, slug: str) -> Path:
        validate_slug(slug)
        path = (self.books_dir / slug).resolve()
        if path != self.books_dir / slug or self.books_dir not in path.parents:
            raise ValueError("invalid slug")
        return path

    def book_file(self, slug: str) -> Path:
        return self.book_dir(slug) / "book.json"

    def _lock(self, slug: str) -> threading.Lock:
        return _lock_for(f"{self.root}::{slug}")

    # -- read ------------------------------------------------------------
    def exists(self, slug: str) -> bool:
        return self.book_file(slug).is_file()

    def load_book(self, slug: str) -> Dict[str, Any]:
        path = self.book_file(slug)
        backup = path.with_suffix(".json.bak")
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            data = self._load_backup(backup)
            if data is None:
                raise BookNotFound(slug)
            return data
        except (json.JSONDecodeError, UnicodeDecodeError):
            data = self._load_backup(backup)
            if data is None:
                raise StorageError(f"corrupted book: {slug}")
            return data

    @staticmethod
    def _load_backup(backup: Path) -> Optional[Dict[str, Any]]:
        try:
            data = json.loads(backup.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            return None
        data["recovered"] = True
        return data

    def list_books(self) -> List[Dict[str, Any]]:
        summaries: List[Dict[str, Any]] = []
        for entry in sorted(self.books_dir.iterdir()):
            if not entry.is_dir() or not SLUG_RE.match(entry.name):
                continue
            try:
                book = self.load_book(entry.name)
            except StorageError:
                continue
            summary = {key: book.get(key) for key in SUMMARY_FIELDS}
            bible = book.get("bible") or {}
            summary["name"] = bible.get("name") if isinstance(bible, dict) else None
            summary["board_count"] = len(book.get("board") or [])
            if book.get("recovered"):
                summary["recovered"] = True
            summaries.append(summary)
        summaries.sort(key=lambda item: item.get("created") or "", reverse=True)
        return summaries

    # -- write -----------------------------------------------------------
    def _write_book(self, slug: str, book: Dict[str, Any]) -> None:
        path = self.book_file(slug)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".json.tmp")
        payload = {k: v for k, v in book.items() if k != "recovered"}
        tmp.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        if path.is_file():
            os.replace(path, path.with_suffix(".json.bak"))
        os.replace(tmp, path)

    def new_slug(self, concept: str) -> str:
        base = slugify(concept)
        if not self.exists(base):
            return base
        for index in range(2, 1000):
            suffix = f"-{index}"
            candidate = f"{base[: 64 - len(suffix)]}{suffix}"
            if not self.exists(candidate):
                return candidate
        raise StorageError("could not allocate slug")

    def create_book(
        self, concept: str, style: str = "", density: int = 6, lang: str = "en"
    ) -> Dict[str, Any]:
        concept = _require_text(concept, "concept", MAX_CONCEPT)
        style = _require_text(style, "style", 200, allow_empty=True)
        if density not in VALID_DENSITY:
            raise ValueError("density must be 6 or 8")
        if lang not in VALID_LANG:
            raise ValueError("lang must be en or ko")
        with self._lock("::new"):
            slug = self.new_slug(concept)
            now = utcnow()
            book: Dict[str, Any] = {
                "schema": SCHEMA_VERSION,
                "slug": slug,
                "concept": concept,
                "style": style,
                "density": density,
                "lang": lang,
                "status": "empty",
                "created": now,
                "updated": now,
                "bible": None,
                "board": [],
            }
            self._write_book(slug, book)
        return book

    def save_book(self, slug: str, book: Dict[str, Any]) -> Dict[str, Any]:
        with self._lock(slug):
            book["updated"] = utcnow()
            self._write_book(slug, book)
        return book

    def update_bible(self, slug: str, patch: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(patch, dict):
            raise ValueError("patch must be an object")
        with self._lock(slug):
            book = self.load_book(slug)
            bible = book.get("bible")
            if not isinstance(bible, dict):
                raise BibleMissing(slug)
            bible.update(patch)
            book["bible"] = bible
            book["updated"] = utcnow()
            self._write_book(slug, book)
            return book

    # -- delete ----------------------------------------------------------
    def delete_book(self, slug: str) -> str:
        with self._lock(slug):
            source = self.book_dir(slug)
            if not source.is_dir():
                raise BookNotFound(slug)
            target = self.trash_dir / f"{slug}-{int(time.time())}"
            while target.exists():
                target = Path(f"{target}x")
            os.rename(source, target)
            return target.name

    def purge_trash(self, days: int = 7) -> int:
        cutoff = time.time() - days * 86400
        removed = 0
        if not self.trash_dir.is_dir():
            return 0
        for entry in self.trash_dir.iterdir():
            if not entry.is_dir():
                continue
            if _trash_stamp(entry) > cutoff:
                continue
            shutil.rmtree(entry, ignore_errors=True)
            removed += 1
        return removed


def _trash_stamp(entry: Path) -> float:
    tail = entry.name.rsplit("-", 1)[-1]
    if tail.isdigit():
        return float(tail)
    return entry.stat().st_mtime


def _require_text(
    value: Any, field: str, limit: int, allow_empty: bool = False
) -> str:
    if value is None and allow_empty:
        return ""
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a string")
    value = value.strip()
    if not value and not allow_empty:
        raise ValueError(f"{field} is required")
    if len(value) > limit:
        raise ValueError(f"{field} is too long (max {limit})")
    return value
