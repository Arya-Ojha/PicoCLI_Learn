"""Learn mode — provider seam: per-turn system prompt swap and mode stamping.

Prior art: tests/test_agent_session.py (FakeProvider end-to-end via AgentSession).
Only external behavior is asserted: which system prompt each turn carries,
and which mode each user message is stamped with.
"""

from pico_ai.types import StreamEvent
from pico_core.session import Session
from pico_sdk.session import (
    DEFAULT_SYSTEM_PROMPT,
    LEARN_SYSTEM_PROMPT,
)

from conftest import FakeProvider, make_session


async def test_act_prompt_is_default(tmp_path):
    provider = FakeProvider([[StreamEvent(kind="text", text="ok")]])
    session = make_session(provider, tmp_path)
    await session.run("hello")
    assert provider.calls[0].system == DEFAULT_SYSTEM_PROMPT


async def test_learn_message_swaps_system_prompt(tmp_path):
    provider = FakeProvider([[StreamEvent(kind="text", text="ok")]])
    session = make_session(provider, tmp_path)
    await session.run("hello", mode="learn")
    assert provider.calls[0].system == LEARN_SYSTEM_PROMPT


async def test_per_message_mode_interleaving(tmp_path):
    provider = FakeProvider(
        [
            [StreamEvent(kind="text", text="a")],
            [StreamEvent(kind="text", text="b")],
            [StreamEvent(kind="text", text="c")],
        ]
    )
    session = make_session(provider, tmp_path)
    await session.run("learn q", mode="learn")
    await session.run("act q", mode="act")
    await session.run("learn q2", mode="learn")
    assert [c.system for c in provider.calls] == [
        LEARN_SYSTEM_PROMPT,
        DEFAULT_SYSTEM_PROMPT,
        LEARN_SYSTEM_PROMPT,
    ]


async def test_user_payload_records_mode(tmp_path):
    provider = FakeProvider(
        [
            [StreamEvent(kind="text", text="a")],
            [StreamEvent(kind="text", text="b")],
        ]
    )
    session = make_session(provider, tmp_path)
    await session.run("learn msg", mode="learn")
    await session.run("act msg")
    users = [
        n.payload for n in session.session.active_branch() if n.payload.kind == "user"
    ]
    assert [u.mode for u in users] == ["learn", "act"]


async def test_session_round_trip_persists_mode(tmp_path):
    provider = FakeProvider([[StreamEvent(kind="text", text="a")]])
    session = make_session(provider, tmp_path)
    await session.run("learn msg", mode="learn")
    path = session.save()
    loaded = Session.load(path)
    user = next(
        n.payload for n in loaded.active_branch() if n.payload.kind == "user"
    )
    assert user.mode == "learn"


def test_legacy_session_without_mode_defaults_to_act():
    # A session persisted before this feature has no "mode" key on the payload.
    text = (
        '{"session_id": "s1", "active_leaf_id": "n1"}\n'
        '{"id": "n1", "parent_id": null, "timestamp": "2020-01-01T00:00:00+00:00", '
        '"payload": {"kind": "user", "content": "legacy"}}\n'
    )
    session = Session.from_jsonl(text)
    user = session.active_branch()[0].payload
    assert user.mode == "act"


def test_cli_exposes_learn_and_strict_flags():
    from pico_sdk.cli import build_parser

    args = build_parser().parse_args(["run", "hi", "--learn", "--strict-learn"])
    assert args.learn is True
    assert args.strict_learn is True


async def test_headless_learn_run_uses_learn_prompt(tmp_path, monkeypatch):
    """pico run --learn drives the run's calls with the learn system prompt."""
    import pico_sdk.cli as cli_module
    from pico_sdk.config import Settings

    provider = FakeProvider([[StreamEvent(kind="text", text="ok")]])

    def _fake_create_provider(settings=None):
        return provider

    monkeypatch.setattr(cli_module, "create_provider", _fake_create_provider)
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-v1-test")

    settings = Settings(session_dir=str(tmp_path / "sessions"))
    monkeypatch.setattr(cli_module, "load_settings", lambda: settings)

    parser = cli_module.build_parser()
    args = parser.parse_args(["run", "hello", "--learn"])
    args.cwd = str(tmp_path)

    exit_code = await cli_module.run_command(args)

    assert exit_code == 0
    assert provider.calls
    assert provider.calls[0].system == LEARN_SYSTEM_PROMPT
