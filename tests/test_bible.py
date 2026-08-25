import json
from pathlib import Path
from typing import Any, Dict, List

import pytest

from app import create_app
from core.bible import BibleParseError, build_prompt, generate_bible, validate_bible
from core.llm import LLMError, LLMNotConfigured
from core.storage import Storage


class FakeLLM:
    """Returns canned replies in order and records every prompt it saw."""

    def __init__(self, *replies: str) -> None:
        self.replies: List[str] = list(replies)
        self.calls: List[tuple] = []

    def generate(self, system: str, user: str) -> str:
        self.calls.append((system, user))
        assert self.replies, "llm called more times than the test allows"
        return self.replies.pop(0)


class BrokenLLM:
    """Always fails with the given error."""

    def __init__(self, error: Exception) -> None:
        self.error = error
        self.calls = 0

    def generate(self, system: str, user: str) -> str:
        self.calls += 1
        raise self.error


def bible_payload(**overrides: Any) -> Dict[str, Any]:
    data: Dict[str, Any] = {
        "name": "Rin Ashgrove",
        "profile": {
            "age": "29",
            "role": "wandering tea merchant",
            "body": "lean and tall",
            "traits": ["patient", "wry"],
        },
        "background": "She walked the salt road for a decade before settling.",
        "voice": {"personality": "dry", "speech": "clipped sentences"},
        "lines": [
            {"situation": f"situation {index}", "line": f"line {index}"}
            for index in range(5)
        ],
        "palette": [
            {"hex": "#1A2B3C", "name": "ink"},
            {"hex": "#FFAA00", "name": "amber"},
            {"hex": "#0F0F0F", "name": "soot"},
            {"hex": "#DDE3E8", "name": "steam"},
        ],
        "world": "A coastal republic held together by tea houses.",
        "master_prompt": "A single character sheet grid with six labelled sections.",
    }
    data.update(overrides)
    return data


@pytest.fixture()
def build(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Factory: an app wired to the fake llm the test provides."""
    monkeypatch.setenv("LOREFORGE_DATA", str(tmp_path / "data"))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    def make(llm: Any = None):
        app = create_app(llm=llm)
        app.config.update(TESTING=True)
        return app.test_client(), app.config["STORAGE"]

    return make


def body(res) -> dict:
    return json.loads(res.data)


def make_book(client, concept: str = "Wandering Tea Merchant", **extra) -> str:
    res = client.post("/api/books", json={"concept": concept, **extra})
    assert res.status_code == 201
    return body(res)["data"]["slug"]


def raw_book(store: Storage, slug: str) -> bytes:
    return store.book_file(slug).read_bytes()


# -- happy paths ---------------------------------------------------------
def test_generate_stores_draft(build) -> None:
    llm = FakeLLM(json.dumps(bible_payload()))
    client, store = build(llm)
    slug = make_book(client)

    res = client.post(f"/api/books/{slug}/generate")
    assert res.status_code == 200
    data = body(res)["data"]
    assert data["status"] == "draft"
    assert data["bible"]["name"] == "Rin Ashgrove"
    assert len(data["bible"]["lines"]) == 5

    stored = store.load_book(slug)
    assert stored["status"] == "draft"
    assert stored["bible"]["palette"][0]["hex"] == "#1A2B3C"
    assert len(llm.calls) == 1


def test_prompt_carries_style_density_and_language(build) -> None:
    llm = FakeLLM(json.dumps(bible_payload()))
    client, _ = build(llm)
    slug = make_book(client, "Salt Road Envoy", style="ukiyo-e", density=8, lang="ko")

    assert client.post(f"/api/books/{slug}/generate").status_code == 200
    system, user = llm.calls[0]
    assert "ONLY one JSON object" in system
    assert "Salt Road Envoy" in user and "ukiyo-e" in user
    assert "8 sections" in user and "Korean" in user
    assert "Write it in English." in user


def test_fenced_response_is_parsed(build) -> None:
    fenced = "```json\n" + json.dumps(bible_payload()) + "\n```"
    client, store = build(FakeLLM(fenced))
    slug = make_book(client)

    assert client.post(f"/api/books/{slug}/generate").status_code == 200
    assert store.load_book(slug)["bible"]["name"] == "Rin Ashgrove"


def test_retry_after_invalid_json(build) -> None:
    llm = FakeLLM("here you go, boss", json.dumps(bible_payload()))
    client, store = build(llm)
    slug = make_book(client)

    res = client.post(f"/api/books/{slug}/generate")
    assert res.status_code == 200
    assert len(llm.calls) == 2
    first_user, second_user = llm.calls[0][1], llm.calls[1][1]
    assert "rejected" in second_user and first_user in second_user
    assert store.load_book(slug)["status"] == "draft"


# -- failure paths: the stored book must never change --------------------
def test_two_bad_replies_leave_book_untouched(build) -> None:
    llm = FakeLLM("not json", json.dumps({"name": "Rin"}))
    client, store = build(llm)
    slug = make_book(client)
    before = raw_book(store, slug)

    res = client.post(f"/api/books/{slug}/generate")
    assert res.status_code == 502
    payload = body(res)
    assert payload["ok"] is False and payload["error"] == "invalid-llm-output"
    assert payload["raw_preview"] == '{"name": "Rin"}'
    assert len(llm.calls) == 2
    assert raw_book(store, slug) == before


def test_raw_preview_is_capped(build) -> None:
    noise = "x" * 900
    client, store = build(FakeLLM(noise, noise))
    slug = make_book(client)

    res = client.post(f"/api/books/{slug}/generate")
    assert res.status_code == 502
    assert body(res)["raw_preview"] == "x" * 500


def test_retryable_llm_error_keeps_status(build) -> None:
    llm = BrokenLLM(LLMError("RateLimitError: slow down", retryable=True))
    client, store = build(llm)
    slug = make_book(client)

    book = store.load_book(slug)
    book["bible"] = bible_payload()
    book["status"] = "draft"
    store.save_book(slug, book)
    before = raw_book(store, slug)

    res = client.post(f"/api/books/{slug}/generate")
    assert res.status_code == 502
    payload = body(res)
    assert payload["ok"] is False and payload["retryable"] is True
    assert "slow down" in payload["error"]
    assert llm.calls == 1
    assert raw_book(store, slug) == before
    assert store.load_book(slug)["status"] == "draft"


def test_non_retryable_llm_error(build) -> None:
    client, store = build(BrokenLLM(LLMError("BadRequestError: nope")))
    slug = make_book(client)
    before = raw_book(store, slug)

    res = client.post(f"/api/books/{slug}/generate")
    assert res.status_code == 502
    assert body(res)["retryable"] is False
    assert raw_book(store, slug) == before


def test_missing_api_key_is_503(build) -> None:
    client, store = build()  # real AnthropicText, no key in the environment
    slug = make_book(client)
    before = raw_book(store, slug)

    res = client.post(f"/api/books/{slug}/generate")
    assert res.status_code == 503
    assert body(res) == {"ok": False, "error": "llm-not-configured"}
    assert raw_book(store, slug) == before
    assert store.load_book(slug)["status"] == "empty"


def test_injected_not_configured_is_503(build) -> None:
    client, _ = build(BrokenLLM(LLMNotConfigured("no key")))
    slug = make_book(client)
    assert client.post(f"/api/books/{slug}/generate").status_code == 503


def test_generate_unknown_or_bad_slug(build) -> None:
    client, _ = build(FakeLLM())
    assert client.post("/api/books/ghost/generate").status_code == 404
    assert client.post("/api/books/../generate").status_code in (400, 404)


# -- validator -----------------------------------------------------------
@pytest.mark.parametrize(
    "payload, expected",
    [
        ({"name": None}, "name"),
        ({"world": ""}, "world"),
        ({"master_prompt": 12}, "master_prompt"),
        ({"profile": {"age": "9", "role": "r", "body": "b"}}, "profile.traits"),
        ({"profile": "not an object"}, "profile"),
        ({"voice": {"personality": "dry"}}, "voice.speech"),
        ({"lines": [{"situation": "s", "line": "l"}] * 4}, "lines must have 5-8"),
        ({"lines": [{"situation": "s", "line": "l"}] * 9}, "lines must have 5-8"),
        ({"lines": [{"situation": "s"}] * 5}, "lines[0].line"),
        ({"palette": [{"hex": "#1A2B3C", "name": "ink"}] * 3}, "palette must have 4-6"),
        ({"palette": [{"hex": "1A2B3C", "name": "ink"}] * 4}, "palette[0].hex"),
        ({"palette": [{"hex": "#12345", "name": "ink"}] * 4}, "palette[0].hex"),
        ({"palette": [{"hex": "#1A2B3C"}] * 4}, "palette[0].name"),
    ],
)
def test_validator_rejects(payload: dict, expected: str) -> None:
    with pytest.raises(ValueError) as err:
        validate_bible(bible_payload(**payload))
    assert expected in str(err.value)


def test_validator_accepts_bounds_and_case() -> None:
    validate_bible(bible_payload())
    validate_bible(
        bible_payload(
            lines=[{"situation": "s", "line": "l"}] * 8,
            palette=[{"hex": "#aabbcc", "name": "fog"}] * 6,
        )
    )


def test_validator_rejects_non_object() -> None:
    for value in ([], "text", None, 5):
        with pytest.raises(ValueError):
            validate_bible(value)


def test_validator_collects_every_violation() -> None:
    with pytest.raises(ValueError) as err:
        validate_bible(bible_payload(name="", world=None, lines=[]))
    message = str(err.value)
    assert "name" in message and "world" in message and "lines" in message


def test_generate_bible_raises_parse_error_with_raw() -> None:
    llm = FakeLLM("nope", "still nope")
    with pytest.raises(BibleParseError) as err:
        generate_bible("concept", "style", 6, "en", llm)
    assert err.value.raw == "still nope"
    assert len(llm.calls) == 2


def test_build_prompt_defaults_unknown_language() -> None:
    _, user = build_prompt("concept", "", 6, "jp")
    assert "English" in user and "artist's choice" in user
