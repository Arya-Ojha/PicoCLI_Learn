"""The provider seam: a single async streaming interface every backend implements."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol

from .types import AICallRequest, StreamEvent


class Provider(Protocol):
    """A backend that turns a request into a stream of normalized events."""

    def stream(self, request: AICallRequest) -> AsyncIterator[StreamEvent]:
        """Yield normalized stream events for a request."""
        ...
