"""Shared test fixtures: the scripted fake provider at the provider seam."""

from __future__ import annotations

import pytest

from pico_ai.types import AICallRequest, StreamEvent
from pico_sdk.config import Settings
from pico_sdk.session import AgentSession


@pytest.fixture(autouse=True)
def _isolate_user_settings(tmp_path, monkeypatch):
    """Redirect the default settings file into tmp_path.

    Regression guard: an old full-flow test once wrote its tmp session_dir
    into the real ``~/.pico/settings.json``. No test may touch it again.
    """
    import pico_sdk.config as config_module

    monkeypatch.setattr(
        config_module,
        "default_settings_path",
        lambda: tmp_path / "settings.json",
    )


class FakeProvider:
    """A scripted provider that yields predetermined turns, one per stream() call."""

    def __init__(self, turns: list[list[StreamEvent]]) -> None:
        self._turns = [list(t) for t in turns]
        self.calls: list[AICallRequest] = []

    async def stream(self, request: AICallRequest):
        self.calls.append(request)
        if self._turns:
            for event in self._turns.pop(0):
                yield event


def make_session(provider, tmp_path, **kwargs) -> AgentSession:
    """Build an AgentSession whose sessions are persisted under ``tmp_path``."""
    return AgentSession(
        provider=provider,
        settings=Settings(session_dir=str(tmp_path)),
        working_dir=tmp_path,
        **kwargs,
    )

