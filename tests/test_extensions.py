"""Smoke: custom tool registration."""

from pico_ai.types import StreamEvent, ToolCall
from pico_core.tools import ToolOutcome

from conftest import FakeProvider, make_session


class EchoTool:
    name = "echo"
    description = "Echo text back."
    input_schema = {
        "type": "object",
        "properties": {"text": {"type": "string"}},
        "required": ["text"],
    }

    async def run(self, arguments):
        return ToolOutcome(content=arguments.get("text", ""))


async def test_register_custom_tool_is_invocable(tmp_path):
    provider = FakeProvider(
        [
            [StreamEvent(kind="tool_call", tool_call=ToolCall(id="c1", name="echo", arguments={"text": "hi"}))],
            [StreamEvent(kind="text", text="done")],
        ]
    )
    session = make_session(provider, tmp_path)
    session.register_tool(EchoTool())
    result = await session.run("echo hi")
    assert result.text == "done"
    results = [
        n.payload
        for n in session.session.active_branch()
        if n.payload.kind == "tool_result"
    ]
    assert results[0].content == "hi"
