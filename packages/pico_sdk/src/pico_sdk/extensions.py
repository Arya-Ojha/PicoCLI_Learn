"""Tool registration: register tools/providers, lifecycle hooks, tool loading."""

from __future__ import annotations

import importlib.util
import inspect
from collections import defaultdict
from pathlib import Path
from typing import Any, Callable

from pico_core.session import Session, ToolResultPayload

Hook = Callable[..., Any]


class ExtensionManager:
    """Tracks registered providers and lifecycle hooks.

    Tools are registered directly into the session's tool registry; this manager
    is the hook/provider surface and implements the loop's ``HookSink``.
    """

    def __init__(self) -> None:
        self._providers: dict[str, Any] = {}
        self._hooks: dict[str, list[Hook]] = defaultdict(list)

    # -- providers ----------------------------------------------------------

    def register_provider(self, name: str, provider: Any) -> None:
        self._providers[name] = provider

    def get_provider(self, name: str) -> Any | None:
        return self._providers.get(name)

    def provider_names(self) -> list[str]:
        return list(self._providers)

    # -- hooks --------------------------------------------------------------

    def on(self, event: str, callback: Hook) -> None:
        self._hooks[event].append(callback)

    async def _fire(self, event: str, **kwargs: Any) -> None:
        for callback in self._hooks.get(event, []):
            result = callback(**kwargs)
            if inspect.isawaitable(result):
                await result

    # HookSink implementation ----------------------------------------------

    async def on_session_start(self, session: Session) -> None:
        await self._fire("on_session_start", session=session)

    async def tool_before(self, name: str, arguments: dict) -> None:
        await self._fire(f"tool.before.{name}", name=name, arguments=arguments)
        await self._fire("tool.before.*", name=name, arguments=arguments)

    async def tool_after(
        self, name: str, arguments: dict, result: ToolResultPayload
    ) -> None:
        await self._fire(
            f"tool.after.{name}", name=name, arguments=arguments, result=result
        )
        await self._fire(
            "tool.after.*", name=name, arguments=arguments, result=result
        )

    # -- tool loading -------------------------------------------------------

    def load_plugins(self, directory: Path | str, session: Any) -> None:
        """Import every ``*.py`` file in ``directory`` and call its ``register``.

        Each tool module may define ``register(session)``, which receives the
        agent session and can call ``register_tool`` / ``register_provider`` /
        ``on`` on it.
        """
        directory = Path(directory)
        if not directory.is_dir():
            return
        for file in sorted(directory.glob("*.py")):
            if file.name.startswith("_"):
                continue
            spec = importlib.util.spec_from_file_location(file.stem, file)
            if spec is None or spec.loader is None:
                continue
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            register = getattr(module, "register", None)
            if callable(register):
                register(session)
