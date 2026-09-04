"""Smoke: stream wire order."""

from pico_ai.types import AICallRequest, StreamEvent
from pico_core.fsm import LoopEvent
from pico_sdk.config import Settings
from pico_sdk.session import AgentSession
from pico_tui.app import _SessionManager, ThinkingSegment


class ScriptedProvider:
    def __init__(self, turns):
        self._turns = [list(t) for t in turns]

    async def stream(self, request: AICallRequest):
        for event in self._turns.pop(0):
            yield event


def _to_loop_events(events):
    for e in events:
        if e.kind == "text":
            yield LoopEvent(kind="text", text=e.text)
        elif e.kind == "thinking":
            yield LoopEvent(kind="thinking", thinking=e.thinking)
        else:
            yield LoopEvent(kind="usage")


async def test_stream_preserves_wire_order(tmp_path):
    """text → thinking → text must render in that exact order."""

    class LoopAdapter:
        def __init__(self, provider):
            self.provider = provider
            self.session = None
            self.system_prompt = ""
            self.tools = None

        def stream(self, prompt):
            async def _gen():
                request = AICallRequest(model="m", messages=[])
                async for ev in self.provider.stream(request):
                    for le in _to_loop_events([ev]):
                        yield le
            return _gen()

    provider = ScriptedProvider([
        [
            StreamEvent(kind="text", text="answer!"),
            StreamEvent(kind="thinking", text="", thinking="hmm"),
            StreamEvent(kind="text", text=" more"),
        ]
    ])
    session = AgentSession(
        provider=provider,
        settings=Settings(session_dir=str(tmp_path)),
        working_dir=tmp_path,
        allow_bash=False,
    )
    mgr = _SessionManager(session)

    captured: list = []
    session.stream = LoopAdapter(provider).stream  # type: ignore[method-assign]
    await mgr.stream("hi", captured.append)

    assert len(captured) == 3
    first, second, third = captured
    assert first.plain == "answer!"
    assert isinstance(second, ThinkingSegment)
    assert second.text == "hmm"
    assert third.plain == " more"
