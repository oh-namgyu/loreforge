"""Image provider seam: kind whitelist, prompt derivation, adapter behaviour."""

import base64
from pathlib import Path

import pytest

from app import create_app
from core.fake_llm import FakeImage, fake_bible, fake_png
from core.images import is_png, read_images, write_image
from core.providers import ImageProvider, NoProvider, ProviderError
from core.providers.openai_image import DEFAULT_MODEL, OpenAIImage, decode_image
from core.render import normalise_kinds, prompt_for

CONCEPT = "Wandering Tea Merchant"


def test_kinds_default_to_board_only() -> None:
    assert normalise_kinds(None) == ["board"]
    assert normalise_kinds(["solo", "board", "solo"]) == ["solo", "board"]


@pytest.mark.parametrize("value", ["board", [], ["mural"], [1], {}])
def test_bad_kinds_rejected(value) -> None:
    with pytest.raises(ValueError):
        normalise_kinds(value)


def test_solo_prompt_derives_from_master_prompt() -> None:
    bible = fake_bible(CONCEPT)
    assert prompt_for("board", bible) == bible["master_prompt"]
    solo = prompt_for("solo", bible)
    assert solo.startswith(bible["master_prompt"])
    assert "single full-body character render" in solo
    with pytest.raises(ValueError):
        prompt_for("board", {"master_prompt": "  "})


# -- image files ---------------------------------------------------------
def test_write_and_read_images(tmp_path: Path) -> None:
    assert read_images(tmp_path) == {}
    assert write_image(tmp_path, "board", fake_png()) == "board.png"
    assert read_images(tmp_path) == {"board": fake_png()}
    assert list(tmp_path.glob("*.tmp")) == []
    with pytest.raises(ValueError):
        write_image(tmp_path, "mural", fake_png())


def test_png_signature_check() -> None:
    assert is_png(fake_png())
    assert not is_png(b"not a png") and not is_png("string") and not is_png(None)


# -- adapters ------------------------------------------------------------
def test_fake_image_is_a_valid_deterministic_png() -> None:
    data = FakeImage().render("anything", "1536x1024")
    assert data.startswith(b"\x89PNG\r\n\x1a\n")
    assert data == FakeImage().render("something else", "1024x1536")
    assert isinstance(FakeImage(), ImageProvider)


def test_openai_adapter_without_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(NoProvider):
        OpenAIImage().render("prompt", "1536x1024")


def test_openai_adapter_model_default_and_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LOREFORGE_IMAGE_MODEL", raising=False)
    assert OpenAIImage().model == DEFAULT_MODEL and OpenAIImage().size == "1536x1024"
    monkeypatch.setenv("LOREFORGE_IMAGE_MODEL", "some-other-model")
    assert OpenAIImage().model == "some-other-model"
    assert OpenAIImage(model="explicit").model == "explicit"


def test_decode_image_reads_b64_and_rejects_empty() -> None:
    class Item:
        b64_json = base64.b64encode(fake_png()).decode("ascii")

    assert decode_image(type("Result", (), {"data": [Item()]})()) == fake_png()
    with pytest.raises(ProviderError):
        decode_image(type("Empty", (), {"data": []})())
    with pytest.raises(ProviderError):
        decode_image(type("Junk", (), {"data": [type("I", (), {"b64_json": "!!"})()]})())


def test_image_provider_hook_is_opt_in(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOREFORGE_DATA", str(tmp_path / "data"))
    monkeypatch.delenv("LOREFORGE_FAKE_LLM", raising=False)
    assert isinstance(create_app().config["IMAGE"], OpenAIImage)
    monkeypatch.setenv("LOREFORGE_FAKE_LLM", "1")
    assert isinstance(create_app().config["IMAGE"], FakeImage)
