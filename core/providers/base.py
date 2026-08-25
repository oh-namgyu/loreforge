"""The image provider seam: one method, two failure shapes.

`NoProvider` means the instance is not set up for images at all (no key, no
SDK) — the whole request is refused. `ProviderError` means one image call
failed while the provider itself is usable, so other kinds still run.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


class NoProvider(Exception):
    """No usable image provider: missing API key or missing SDK."""


class ProviderError(Exception):
    """One image call failed. `retryable` marks transient failures."""

    def __init__(self, message: str, retryable: bool = False) -> None:
        super().__init__(message)
        self.retryable = retryable


@runtime_checkable
class ImageProvider(Protocol):
    """Anything that turns a prompt into PNG bytes."""

    def render(self, prompt: str, size: str) -> bytes:
        """Return PNG bytes, or raise NoProvider / ProviderError."""
