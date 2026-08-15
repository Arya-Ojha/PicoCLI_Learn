"""Ticket 06 — extension binding: custom tools/providers, hooks, plugin loading."""

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
    # the echo tool ran and its result is in the tree
    results = [
        n.payload
        for n in session.session.active_branch()
        if n.payload.kind == "tool_result"
    ]
    assert results[0].content == "hi"


def test_register_and_use_provider(tmp_path):
    session = make_session(FakeProvider([]), tmp_path)
    other = FakeProvider([])
    session.register_provider("fake", other)
    assert "fake" in session.extensions.provider_names()
    session.use_provider("fake")
    assert session.loop.provider is other


async def test_lifecycle_hooks_fire(tmp_path):
    (tmp_path / "a.txt").write_text("hello", encoding="utf-8")
    provider = FakeProvider(
        [
            [StreamEvent(kind="tool_call", tool_call=ToolCall(id="c1", name="read", arguments={"path": "a.txt"}))],
            [StreamEvent(kind="text", text="done")],
        ]
    )
    session = make_session(provider, tmp_path)
    calls = []

    async def on_start(session):
        calls.append("on_session_start")

    async def before(name, arguments):
        calls.append(f"before:{name}")

    async def after(name, arguments, result):
        calls.append(f"after:{name}")

    session.on("on_session_start", on_start)
    session.on("tool.before.*", before)
    session.on("tool.after.*", after)
    await session.run("read a.txt")
    assert "on_session_start" in calls
    assert "before:read" in calls
    assert "after:read" in calls


def test_load_plugins_from_directory(tmp_path):
    plugin_dir = tmp_path / "plugins"
    plugin_dir.mkdir()
    (plugin_dir / "myplugin.py").write_text(
        "def register(session):\n"
        "    from pico_core.tools import ToolOutcome\n"
        "    class HelloTool:\n"
        "        name = 'hello'\n"
        "        description = 'say hello'\n"
        "        input_schema = {'type': 'object'}\n"
        "        async def run(self, arguments):\n"
        "            return ToolOutcome(content='hello')\n"
        "    session.register_tool(HelloTool())\n",
        encoding="utf-8",
    )
    session = make_session(FakeProvider([]), tmp_path)
    session.load_plugins(plugin_dir)
    assert "hello" in session.tools.names()
