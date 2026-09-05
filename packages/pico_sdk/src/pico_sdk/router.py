"""Capability router: deterministic capability -> model-id from a registry.

The registry lives in ``~/.pico/models.yaml``. ``Settings.model == ""``
means the router decides per turn; an explicit id pins the model.
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel


class RegistryEntry(BaseModel):
    """One usable model in the registry."""

    id: str
    provider: str = "local"
    ctx: int = 32_768
    vram_gb: float = 3.0
    caps: list[str] = []
    testing_only: bool = False


def default_registry_path() -> Path:
    """Return the default registry file path."""
    return Path.home() / ".pico" / "models.yaml"


def _parse_simple_yaml(text: str) -> list[dict]:
    """Parse the minimal ``models.yaml`` subset (list of flat mappings)."""
    items: list[dict] = []
    current: dict | None = None
    current_key: str | None = None
    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("- "):
            if current is not None:
                items.append(current)
            current = {}
            current_key = None
            rest = stripped[2:].strip()
            if rest:
                if ":" in rest:
                    k, v = rest.split(":", 1)
                    current[k.strip()] = _coerce(v.strip())
                continue
            continue
        if current is None:
            continue
        if ":" not in stripped:
            if current_key == "caps" and isinstance(current.get("caps"), list):
                (current["caps"]).append(stripped.strip("[], ").strip("\"'"))
            continue
        k, v = stripped.split(":", 1)
        k = k.strip()
        v = v.strip()
        if v == "":
            if k == "caps":
                current[k] = []
                current_key = k
            else:
                current[k] = ""
                current_key = k
            continue
        if v.startswith("[") and v.endswith("]"):
            inner = v[1:-1].strip()
            current[k] = [p.strip().strip("\"'") for p in inner.split(",") if p.strip()] if inner else []
        else:
            current[k] = _coerce(v)
        current_key = k
    if current is not None:
        items.append(current)
    return items


def _coerce(value: str) -> str | int | float | bool:
    low = value.lower().strip("\"'")
    if low in ("true", "false"):
        return low == "true"
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        pass
    return value.strip("\"'")


def load_registry(path: Path | None = None) -> list[RegistryEntry]:
    """Load the registry; missing file yields an empty list (caller falls back)."""
    path = Path(path) if path is not None else default_registry_path()
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return []
    if text.startswith("{") or text.startswith("["):
        data = json.loads(text)
        rows = data if isinstance(data, list) else data.get("models", [])
        return [RegistryEntry.model_validate(r) for r in rows]
    return [RegistryEntry.model_validate(r) for r in _parse_simple_yaml(text)]


def route(
    capability: str, registry: list[RegistryEntry], default: str = ""
) -> tuple[str, str]:
    """Pick a model id for ``capability``.

    Returns ``(model_id, reason)``. Exact capability match wins; otherwise
    the first non-testing entry; otherwise ``default``.
    """
    cap = capability.strip().lower()
    for entry in registry:
        if cap and cap in [c.lower() for c in entry.caps]:
            return entry.id, f"capability '{cap}' matched {entry.id}"
    for entry in registry:
        if not entry.testing_only:
            return entry.id, f"fallback to {entry.id} (no '{cap}' match)"
    if registry:
        return registry[0].id, f"fallback to testing-only {registry[0].id}"
    return default, "empty registry; using default"


EXAMPLE_YAML = """\
# Capability registry. Adding a model = one entry, no redesign.
- id: qwen2.5-3B-instruct-Q4
  provider: local
  ctx: 32768
  vram_gb: 2.5
  caps: [code, summary]
  testing_only: false
- id: nuextract-3-4B-Q4
  provider: local
  ctx: 8192
  vram_gb: 3.0
  caps: [vision, ocr]
  testing_only: false
- id: openrouter-vision-alias
  provider: openrouter
  ctx: 128000
  vram_gb: 0
  caps: [vision, ocr, code, summary]
  testing_only: true
"""
