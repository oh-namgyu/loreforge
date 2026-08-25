"""REST API blueprint. Every response uses the {ok, data|error} envelope."""

from __future__ import annotations

from typing import Any, Dict, Tuple, Union

from flask import Blueprint, Response, current_app, jsonify, request, send_file

from .bible import BibleParseError, generate_bible, validate_bible
from .export import render_export
from .images import image_path, read_images
from .llm import LLMError, LLMNotConfigured
from .providers import NoProvider
from .render import normalise_kinds, render_book
from .storage import BibleMissing, BookNotFound, Storage, StorageError

api_bp = Blueprint("api", __name__, url_prefix="/api")
RAW_PREVIEW = 500
# a handler either returns the JSON envelope with its status, or a raw file/document
Reply = Union[Response, Tuple[Response, int]]


def ok(data: Any, status: int = 200) -> Tuple[Response, int]:
    return jsonify({"ok": True, "data": data}), status


def fail(message: str, status: int, **extra: Any) -> Tuple[Response, int]:
    payload: Dict[str, Any] = {"ok": False, "error": message}
    payload.update(extra)
    return jsonify(payload), status


def store() -> Storage:
    return current_app.config["STORAGE"]


def llm() -> Any:
    return current_app.config["LLM"]


def image() -> Any:
    provider = current_app.config.get("IMAGE")
    if provider is None:
        raise NoProvider("no image provider configured")
    return provider


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


@api_bp.post("/books/<slug>/generate")
def generate(slug: str) -> Tuple[Response, int]:
    """Concept -> bible. The stored book is untouched unless generation succeeds."""
    book = store().load_book(slug)
    try:
        bible = generate_bible(
            concept=book.get("concept") or "",
            style=book.get("style") or "",
            density=book.get("density") or 6,
            lang=book.get("lang") or "en",
            llm=llm(),
        )
    except LLMNotConfigured:
        return fail("llm-not-configured", 503)
    except LLMError as err:
        return fail(str(err) or "llm-error", 502, retryable=err.retryable)
    except BibleParseError as err:
        return fail("invalid-llm-output", 502, raw_preview=err.raw[:RAW_PREVIEW])
    book["bible"] = bible
    book["status"] = "draft"
    return ok(store().save_book(slug, book))


@api_bp.patch("/books/<slug>/bible")
def patch_bible(slug: str) -> Tuple[Response, int]:
    """The merged bible has to satisfy the generation schema, not just the patch."""
    body = _payload()
    if not body:
        return fail("empty patch", 400)
    return ok(store().update_bible(slug, body, validate=validate_bible))


@api_bp.post("/books/<slug>/render")
def render(slug: str) -> Tuple[Response, int]:
    """Board and/or solo image. Partial success stays ok:true with `failed` set."""
    kinds = normalise_kinds(_payload().get("kinds"))
    try:
        return ok(render_book(store(), image(), slug, kinds))
    except NoProvider:
        return fail("no-image-provider", 409)


@api_bp.get("/books/<slug>/export")
def export(slug: str) -> Reply:
    """One self-contained HTML file, offered as a download."""
    book = store().load_book(slug)
    if not isinstance(book.get("bible"), dict):
        raise BibleMissing(slug)
    document = render_export(book, read_images(store().book_dir(slug)))
    response = current_app.response_class(document, mimetype="text/html")
    response.headers["Content-Disposition"] = f'attachment; filename="{slug}-lorebook.html"'
    return response


@api_bp.get("/books/<slug>/image/<kind>")
def get_image(slug: str, kind: str) -> Reply:
    path = image_path(store().book_dir(slug), kind)
    if not path.is_file():
        return fail("image not found", 404)
    return send_file(path, mimetype="image/png", max_age=0)


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
