"""Smoke: CLI event rendering + default flags."""

from pico_core.fsm import LoopEvent
from pico_sdk.cli import build_parser, format_event


def test_format_event_prints_text():
    assert format_event(LoopEvent(kind="text", text="hello")) == "hello"


def test_bash_enabled_by_default():
    args = build_parser().parse_args(["run", "hi"])
    assert args.no_bash is False
