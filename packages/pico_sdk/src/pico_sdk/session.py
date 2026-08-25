"""The headless library API: ``AgentSession``."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from pico_core.fsm import AgentLoop, LoopEvent, RunResult
from pico_core.learn_tools import (
    FetchTool,
    GuardedEditTool,
    GuardedWriteTool,
    LessonTool,
    SearchTool,
)
from pico_core.session import Mode, Session
from pico_core.tools import BashTool, EditTool, ReadTool, Tool, ToolRegistry, WriteTool

from .config import Settings, load_settings
from .extensions import ExtensionManager

DEFAULT_SYSTEM_PROMPT = (
    "You are pico, a coding agent. You can read, write, and edit files, and run "
    "bash commands. Work autonomously to complete the user's task, then report "
    "what you did."
)

LEARN_SYSTEM_PROMPT = (
    "You are pico in LEARN MODE. Your job is to help the learner learn, not to "
    "do the work for them. Never author or modify the learner's own source code; "
    "the learner is the only author of their code. Use `read` freely to see their "
    "code and run `bash` only to run their tests/code as feedback.\n\n"
    "There are two ways to help:\n"
    "1. TUTORING over their repository — explain, ask Socratic questions, and "
    "walk a hint ladder. Start with the concept, then an algorithm outline or "
    "pseudocode, then at most a small snippet with a gap. Only give a full "
    "solution after an explicit, repeated request, and check once ('have you "
    "tried X first?') before revealing it.\n"
    "2. LESSON BUILDING for a topic they ask to learn (e.g. React.js). Research "
    "with the `search` and `fetch` tools, design a lesson plan, then write ONE "
    "lesson page at a time with the `lesson` tool. Each page is self-contained "
    "HTML with an explanation and an interactive quiz. After writing a page, stop "
    "and let the learner study it before writing the next. Never author their "
    "project code while building lessons."
)


class AgentSession:
    """A headless agent session: provider + tools + session tree + extensions."""

    def __init__(
        self,
        *,
        provider: Any,
        model: str | None = None,
        settings: Settings | None = None,
        working_dir: str | Path | None = None,
        allow_bash: bool = True,
        session_id: str | None = None,
        session: Session | None = None,
        system_prompt: str = DEFAULT_SYSTEM_PROMPT,
        learn_system_prompt: str | None = None,
        strict_learn: bool = False,
    ) -> None:
        self.settings = settings or load_settings()
        self.model = model or self.settings.model
        self.working_dir = Path(working_dir) if working_dir else Path.cwd()
        self.extensions = ExtensionManager()
        self.strict_learn = strict_learn

        # The two per-message system prompts; "act" is today's default.
        self.act_system_prompt = system_prompt
        self.learn_system_prompt = learn_system_prompt or LEARN_SYSTEM_PROMPT

        self.session = session or (Session(id=session_id) if session_id else Session())
        self.tools = ToolRegistry()
        self._register_core_tools(allow_bash)

        self.loop = AgentLoop(
            provider=provider,
            session=self.session,
            tools=self.tools,
            system_prompt=self.system_prompt_for("act"),
            model=self.model,
            context_window=self.settings.context_window,
            reserve_tokens=self.settings.reserve_tokens,
            hooks=self.extensions,
        )

    @property
    def provider(self) -> Any:
        return self.loop.provider

    # -- mode ---------------------------------------------------------------

    def system_prompt_for(self, mode: Mode) -> str:
        """Return the system prompt used for a message sent in ``mode``."""
        return self.learn_system_prompt if mode == "learn" else self.act_system_prompt

    # -- core tools ---------------------------------------------------------

    def _register_core_tools(self, allow_bash: bool) -> None:
        write: Tool = (
            GuardedWriteTool(self.working_dir)
            if self.strict_learn
            else WriteTool(self.working_dir)
        )
        edit: Tool = (
            GuardedEditTool(self.working_dir)
            if self.strict_learn
            else EditTool(self.working_dir)
        )
        for tool in (
            ReadTool(self.working_dir),
            write,
            edit,
            BashTool(self.working_dir, enabled=allow_bash),
            LessonTool(self.working_dir),
            FetchTool(),
            SearchTool(),
        ):
            self.tools.register(tool)

    # -- running ------------------------------------------------------------

    async def run(self, prompt: str, *, mode: Mode = "act") -> RunResult:
        self.loop.system_prompt = self.system_prompt_for(mode)
        return await self.loop.run(prompt, mode=mode)

    def stream(self, prompt: str, *, mode: Mode = "act") -> AsyncIterator[LoopEvent]:
        self.loop.system_prompt = self.system_prompt_for(mode)
        return self.loop.stream(prompt, mode=mode)

    def fork(self, node_id: str) -> None:
        self.session.fork(node_id)

    async def compact(self, instructions: str = "") -> None:
        await self.loop.compact(instructions)

    # -- extension binding --------------------------------------------------

    def register_tool(self, tool: Tool) -> None:
        self.tools.register(tool)

    def register_provider(self, name: str, provider: Any) -> None:
        self.extensions.register_provider(name, provider)

    def use_provider(self, name: str) -> None:
        provider = self.extensions.get_provider(name)
        if provider is None:
            raise KeyError(f"unknown provider: {name}")
        self.loop.provider = provider

    def on(self, event: str, callback: Any) -> None:
        self.extensions.on(event, callback)

    def load_plugins(self, directory: str | Path) -> None:
        self.extensions.load_plugins(directory, self)

    # -- persistence --------------------------------------------------------

    def session_path(self) -> Path:
        directory = Path(self.settings.session_dir).expanduser()
        return directory / f"{self.session.id}.jsonl"

    def save(self) -> Path:
        path = self.session_path()
        self.session.save(path)
        return path

    @classmethod
    def load(
        cls,
        session_id: str,
        *,
        provider: Any,
        model: str | None = None,
        settings: Settings | None = None,
        working_dir: str | Path | None = None,
        allow_bash: bool = True,
        system_prompt: str = DEFAULT_SYSTEM_PROMPT,
        learn_system_prompt: str | None = None,
        strict_learn: bool = False,
    ) -> "AgentSession":
        """Resume an existing session persisted under ``session_dir``."""
        settings = settings or load_settings()
        directory = Path(settings.session_dir).expanduser()
        session = Session.load(directory / f"{session_id}.jsonl")
        return cls(
            provider=provider,
            model=model,
            settings=settings,
            working_dir=working_dir,
            allow_bash=allow_bash,
            session=session,
            system_prompt=system_prompt,
            learn_system_prompt=learn_system_prompt,
            strict_learn=strict_learn,
        )
