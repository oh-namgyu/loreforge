"""OpenAI image provider. The SDK import stays inside the call so tests never need it."""

from __future__ import annotations

import base64
import binascii
import os
from typing import Any

from ..llm import is_retryable
from .base import NoProvider, ProviderError

DEFAULT_MODEL = "gpt-image-1"
DEFAULT_SIZE = "1536x1024"


def decode_image(result: Any) -> bytes:
    """Pull the first base64 image out of an images.generate response."""
    for item in getattr(result, "data", None) or []:
        payload = getattr(item, "b64_json", None)
        if not payload:
            continue
        try:
            return base64.b64decode(payload, validate=True)
        except (binascii.Error, ValueError) as err:
            raise ProviderError("provider returned undecodable image data") from err
    raise ProviderError("provider returned no image data")


class OpenAIImage:
    """gpt-image-1 through the OpenAI Images API."""

    def __init__(self, model: str = "", size: str = "") -> None:
        self.model = model or os.environ.get("LOREFORGE_IMAGE_MODEL") or DEFAULT_MODEL
        self.size = size or DEFAULT_SIZE

    def render(self, prompt: str, size: str = "") -> bytes:
        client = self._client()
        try:
            result = client.images.generate(
                model=self.model, prompt=prompt, size=size or self.size, n=1
            )
        except Exception as err:  # provider failures are normalised for the API layer
            raise ProviderError(
                f"{type(err).__name__}: {err}", retryable=is_retryable(err)
            ) from err
        return decode_image(result)

    @staticmethod
    def _client() -> Any:
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise NoProvider("OPENAI_API_KEY is not set")
        try:
            import openai
        except ImportError as err:
            raise NoProvider("the openai package is not installed") from err
        return openai.OpenAI(api_key=api_key)
