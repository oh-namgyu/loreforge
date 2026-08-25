"""REST API blueprint. Every response uses the {ok, data|error} envelope."""

from __future__ import annotations

from typing import Any, Dict, Tuple

from flask import Blueprint, Response, current_app, jsonify, request

from .storage import BibleMissing, BookNotFound, Storage, StorageError

api_bp = Blueprint("api", __name__, url_prefix="/api")


def ok(data: Any, status: int = 200) -> Tuple[Response, int]:
    return jsonify({"ok": True, "data": data}), status


def fail(message: str, status: int) -> Tuple[Response, int]:
    return jsonify({"ok": False, "error": message}), status


def store() -> Storage:
    return current_app.config["STORAGE"]


def _payload() -> Dict[str, Any]:
    body = request.get_json(silent=True)
    if body is None:
        return {}
    if not isinstance(body, dict):
        raise ValueError("body must be a JSON object")
    return body


@api_bp.get("/books")
def list_books() -> Tuple[Response, int]:
    return ok(store().list_books())


@api_bp.post("/books")
def create_book() -> Tuple[Response, int]:
    body = _payload()
    density = body.get("density", 6)
    if isinstance(density, str) and density.isdigit():
        density = int(density)
    book = store().create_book(
        concept=body.get("concept"),
        style=body.get("style") or "",
        density=density,
        lang=body.get("lang") or "en",
    )
    return ok({"slug": book["slug"]}, 201)


@api_bp.get("/books/<slug>")
def get_book(slug: str) -> Tuple[Response, int]:
    return ok(store().load_book(slug))


@api_bp.patch("/books/<slug>/bible")
def patch_bible(slug: str) -> Tuple[Response, int]:
    body = _payload()
    if not body:
        return fail("empty patch", 400)
    return ok(store().update_bible(slug, body))


@api_bp.delete("/books/<slug>")
def delete_book(slug: str) -> Tuple[Response, int]:
    trashed = store().delete_book(slug)
    return ok({"slug": slug, "trashed": trashed})


def register_errors(app) -> None:
    """JSON envelope for API errors, including framework-raised ones."""

    @app.errorhandler(ValueError)
    def _bad_request(err: ValueError):
        return fail(str(err) or "bad request", 400)

    @app.errorhandler(BookNotFound)
    def _not_found(err: BookNotFound):
        return fail("book not found", 404)

    @app.errorhandler(BibleMissing)
    def _conflict(err: BibleMissing):
        return fail("book has no bible yet", 409)

    @app.errorhandler(StorageError)
    def _storage(err: StorageError):
        return fail(str(err) or "storage error", 500)

    @app.errorhandler(404)
    def _http_404(err):
        if request.path.startswith("/api/"):
            return fail("not found", 404)
        return err

    @app.errorhandler(405)
    def _http_405(err):
        if request.path.startswith("/api/"):
            return fail("method not allowed", 405)
        return err
