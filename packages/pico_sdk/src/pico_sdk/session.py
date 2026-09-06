"""The workbench library API: ``AgentSession``."""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from pathlib import Path
from typing import Any

from pico_core.fsm import AgentLoop, LoopEvent, RunResult
from pico_core.session import Session
from pico_core.todos import TodoStore, TodoWriteTool
from pico_core.tools import BashTool, EditTool, ReadTool, Tool, ToolRegistry, WriteTool

from .config import Settings, load_settings
from .docread import DocPage
from .extensions import ExtensionManager

DEFAULT_SYSTEM_PROMPT = (
    "You are pico, a self-hosted workbench agent. You work only inside the opened "
    "folder (cwd-jail) and produce real deliverables with knowledge-base citations. "
    "For tasks with 3+ steps, plan with todo_write first, keep "
    "exactly one item in_progress, and mark items completed as you finish them. "
    "Work autonomously to complete the user's task, then report what you did."
)




class AgentSession:
    """A workbench agent session: provider + tools + session tree + tool registration."""

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
        registry: list | None = None,
    ) -> None:
        self.settings = settings or load_settings()
        self.model = model or self.settings.model
        self.working_dir = Path(working_dir) if working_dir else Path.cwd()
        self.extensions = ExtensionManager()
        self.registry = registry if registry is not None else self._load_registry()

        self.system_prompt = system_prompt

        self.session = session or (Session(id=session_id) if session_id else Session())
        self.tools = ToolRegistry()
        self.todos = TodoStore()
        self._register_core_tools(allow_bash)

        self.loop = AgentLoop(
            provider=provider,
            session=self.session,
            tools=self.tools,
            system_prompt=self.system_prompt,
            model=self.model,
            context_window=self.settings.context_window,
            reserve_tokens=self.settings.reserve_tokens,
            hooks=self.extensions,
            router_fn=self._router_fn,
        )

    def _load_registry(self) -> list:
        from .router import load_registry

        try:
            return load_registry(Path(self.settings.models_file).expanduser())
        except OSError:
            return []

    def _router_fn(self, capability: str) -> tuple[str, str] | None:
        if not self.registry:
            return None
        from .router import route

        if self.model:
            return self.model, f"pinned to {self.model}"
        model_id, reason = route(capability, self.registry, default=self.model)
        self.model = model_id
        return model_id, reason

    @property
    def provider(self) -> Any:
        return self.loop.provider

    @property
    def provider_name(self) -> str:
        """Return a human-readable provider name."""
        provider = self.loop.provider
        display = getattr(provider, "display_name", "")
        if display:
            return display
        provider_class = type(provider).__name__
        # Convert CamelCase to readable name
        if "OpenRouter" in provider_class:
            return "OpenRouter"
        return provider_class.replace("Provider", "")

    @property
    def context_window(self) -> int:
        """Return the context window size."""
        return self.loop.context_window

    def estimate_tokens(self) -> int:
        """Return the current estimated token count."""
        return self.loop.estimate_tokens()

    # -- core tools ---------------------------------------------------------

    def _register_core_tools(self, allow_bash: bool) -> None:
        from .ocr import OcrTool
        from .summarize import SummarizeTool

        ocr = OcrTool(self.working_dir, self.settings, on_pages=self._append_ocr_pages)
        for tool in (
            ReadTool(self.working_dir),
            WriteTool(self.working_dir),
            EditTool(self.working_dir),
            BashTool(self.working_dir, enabled=allow_bash),
            TodoWriteTool(self.todos),
            ocr,
            SummarizeTool(self.working_dir, self.settings),
        ):
            self.tools.register(tool)

    def _append_ocr_pages(self, pages: Sequence[DocPage]) -> None:
        """Keep per-page ``ocr_page`` trace nodes for an ocr_read call."""
        from pico_core.session import ocr_page_payload

        from .ocr import trace_page_text

        for page in pages:
            self.session.append(
                self.session.active_leaf_id,
                ocr_page_payload(page.page, page.png, trace_page_text(page.text)),
            )

    # -- running ------------------------------------------------------------

    async def run(self, prompt: str, capability: str = "") -> RunResult:
        self.loop.system_prompt = self.system_prompt
        return await self.loop.run(prompt, capability=capability)

    def stream(self, prompt: str, capability: str = "") -> AsyncIterator[LoopEvent]:
        self.loop.system_prompt = self.system_prompt
        return self.loop.stream(prompt, capability=capability)

    def fork(self, node_id: str) -> None:
        self.session.fork(node_id)

    async def compact(self, instructions: str = "") -> None:
        await self.loop.compact(instructions)

    # -- tool/provider registration -------------------------------------------

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
        )
