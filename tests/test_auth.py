import json
import time
from pathlib import Path

import pytest

from app import create_app
from core import auth

TOKEN = "test-dummy-auth-token"  # not a real credential; fixture value only


@pytest.fixture()
def open_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("LOREFORGE_DATA", str(tmp_path / "data"))
    monkeypatch.delenv("AUTH_TOKEN", raising=False)
    application = create_app()
    application.config.update(TESTING=True)
    return application.test_client()


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("LOREFORGE_DATA", str(tmp_path / "data"))
    monkeypatch.setenv("AUTH_TOKEN", TOKEN)
    application = create_app()
    application.config.update(TESTING=True)
    return application.test_client()


def body(res) -> dict:
    return json.loads(res.data)


def login(client, token: str = TOKEN):
    return client.post("/login", data={"token": token})


# --- open mode -------------------------------------------------------------


@pytest.mark.parametrize("path", ["/", "/api/books"])
def test_open_mode_needs_no_cookie(open_client, path: str) -> None:
    assert open_client.get(path).status_code == 200


def test_open_mode_mutation_without_origin_header(open_client) -> None:
    res = open_client.post("/api/books", json={"concept": "Salt Road Caravan"})
    assert res.status_code == 201


def test_open_mode_has_no_login_route(open_client) -> None:
    assert open_client.get("/login").status_code == 404


# --- gate ------------------------------------------------------------------


def test_api_without_cookie_is_401_envelope(client) -> None:
    res = client.get("/api/books")
    assert res.status_code == 401
    assert body(res) == {"ok": False, "error": "unauthorized"}


def test_ui_without_cookie_redirects_to_login(client) -> None:
    res = client.get("/")
    assert res.status_code == 302
    assert res.headers["Location"].endswith("/login")


@pytest.mark.parametrize("path", ["/login", "/static/style.css"])
def test_exempt_paths_reachable_without_cookie(client, path: str) -> None:
    assert client.get(path).status_code == 200


def test_wrong_token_is_401_and_sets_no_cookie(client) -> None:
    res = login(client, "nope")
    assert res.status_code == 401
    assert b"Invalid token" in res.data
    assert auth.COOKIE_NAME not in res.headers.get("Set-Cookie", "")


def test_correct_token_sets_cookie_and_grants_access(client) -> None:
    res = login(client)
    assert res.status_code == 302
    cookie = res.headers["Set-Cookie"]
    assert cookie.startswith(f"{auth.COOKIE_NAME}=")
    assert "HttpOnly" in cookie and "SameSite=Strict" in cookie
    assert client.get("/api/books").status_code == 200


def test_logout_clears_cookie(client) -> None:
    login(client)
    res = client.get("/logout")
    assert res.status_code == 302
    assert client.get("/api/books").status_code == 401


@pytest.mark.parametrize(
    "cookie",
    [
        "notatoken",
        "1700000000.deadbeef",
        "abc.{sig}",
        "{ts}.{sig}x",
    ],
)
def test_tampered_cookie_rejected(client, cookie: str) -> None:
    ts = str(int(time.time()))
    client.set_cookie(auth.COOKIE_NAME, cookie.format(ts=ts, sig=auth.sign(TOKEN, ts)))
    assert client.get("/api/books").status_code == 401


def test_expired_session_rejected(client) -> None:
    stale = int(time.time()) - 9 * 3600
    client.set_cookie(auth.COOKIE_NAME, auth.make_session(TOKEN, stale))
    assert client.get("/api/books").status_code == 401


def test_session_inside_window_accepted(client) -> None:
    fresh = int(time.time()) - 7 * 3600
    client.set_cookie(auth.COOKIE_NAME, auth.make_session(TOKEN, fresh))
    assert client.get("/api/books").status_code == 200


# --- origin gate -----------------------------------------------------------


@pytest.mark.parametrize(
    "headers",
    [
        {"Origin": "http://evil.example"},
        {"Referer": "http://evil.example/x"},
        {},
    ],
)
def test_mutation_with_bad_origin_is_403(client, headers: dict) -> None:
    login(client)
    res = client.post("/api/books", json={"concept": "Salt Road Caravan"}, headers=headers)
    assert res.status_code == 403
    assert body(res)["error"] == "cross-origin request rejected"


@pytest.mark.parametrize(
    "headers",
    [
        {"Origin": "http://localhost"},
        {"Referer": "http://localhost/"},
    ],
)
def test_mutation_with_matching_origin_passes(client, headers: dict) -> None:
    login(client)
    res = client.post("/api/books", json={"concept": "Salt Road Caravan"}, headers=headers)
    assert res.status_code == 201


def test_delete_requires_origin(client) -> None:
    login(client)
    created = client.post(
        "/api/books", json={"concept": "Salt Road Caravan"}, headers={"Origin": "http://localhost"}
    )
    slug = body(created)["data"]["slug"]
    assert client.delete(f"/api/books/{slug}").status_code == 403
    assert (
        client.delete(f"/api/books/{slug}", headers={"Origin": "http://localhost"}).status_code
        == 200
    )


def test_get_needs_no_origin_header(client) -> None:
    login(client)
    assert client.get("/api/books").status_code == 200


# --- bind guard ------------------------------------------------------------


@pytest.mark.parametrize("host", ["127.0.0.1", "localhost", "::1", "127.0.0.5"])
def test_loopback_bind_needs_no_token(host: str) -> None:
    lines: list[str] = []
    auth.check_bind(host, None, lines.append)
    assert lines == []


def test_external_bind_without_token_exits(capsys) -> None:
    with pytest.raises(SystemExit) as exc:
        auth.check_bind("0.0.0.0", None)
    assert exc.value.code == 1
    assert "AUTH_TOKEN" in capsys.readouterr().out


def test_external_bind_with_token_warns() -> None:
    lines: list[str] = []
    auth.check_bind("0.0.0.0", TOKEN, lines.append)
    assert len(lines) == 1 and "TLS proxy" in lines[0]


# --- helpers ---------------------------------------------------------------


def test_signature_depends_on_token() -> None:
    ts = "1700000000"
    assert auth.sign(TOKEN, ts) != auth.sign("other", ts)
    assert not auth.verify_session(auth.make_session("other"), TOKEN)


@pytest.mark.parametrize(
    "header,expected",
    [
        ("http://localhost", True),
        ("https://localhost", True),
        ("http://localhost:6180", False),
        ("http://other", False),
        (None, False),
    ],
)
def test_same_origin_compares_host_and_port(header, expected: bool) -> None:
    assert auth.same_origin(header, "localhost") is expected
