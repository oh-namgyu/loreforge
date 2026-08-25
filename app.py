"""loreforge — self-hosted lore book studio. Application factory and entrypoint."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from flask import Flask, Response, send_from_directory

from core.api import api_bp, register_errors
from core.storage import Storage

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 6180
CSP = "default-src 'self'; img-src 'self' data:; base-uri 'none'; frame-ancestors 'none'"


def resolve_data_dir(data_dir: Optional[str | os.PathLike[str]] = None) -> Path:
    if data_dir:
        return Path(data_dir)
    env_dir = os.environ.get("LOREFORGE_DATA")
    if env_dir:
        return Path(env_dir)
    return BASE_DIR / "data"


def create_app(data_dir: Optional[str | os.PathLike[str]] = None) -> Flask:
    app = Flask(__name__, static_folder=str(STATIC_DIR), static_url_path="/static")
    storage = Storage(resolve_data_dir(data_dir))
    storage.purge_trash(days=int(os.environ.get("LOREFORGE_TRASH_DAYS", "7")))
    app.config["STORAGE"] = storage
    app.register_blueprint(api_bp)
    register_errors(app)

    @app.get("/")
    def index() -> Response:
        return send_from_directory(STATIC_DIR, "index.html")

    @app.after_request
    def security_headers(response: Response) -> Response:
        response.headers.setdefault("Content-Security-Policy", CSP)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        return response

    return app


def main() -> None:
    host = os.environ.get("HOST", DEFAULT_HOST)
    port = int(os.environ.get("PORT", DEFAULT_PORT))
    if host not in ("127.0.0.1", "localhost", "::1"):
        print(f"[warn] binding {host}: traffic is plain HTTP — put a TLS proxy in front")
    create_app().run(host=host, port=port, threaded=True)


if __name__ == "__main__":
    main()
