# 0001 — Monorepo split into four packages

- Status: Accepted
- Date: 2026-08-15

## Context

pico is a personal, learning-oriented coding agent inspired by Pi's modular architecture ("every feature is a plugin"). We had to choose between a single Python package and a monorepo of separate packages.

## Decision

Split the project into four packages, each with a single responsibility:

- `pico_ai` — LLM abstraction and protocol normalisation (the unified "AI call").
- `pico_core` — the agent loop (state machine) and the session tree.
- `pico_sdk` — the headless library API and the extension/plugin binding.
- `pico_tui` — the terminal UI view.

Dependencies flow one way: `pico_ai` ← `pico_core` ← `pico_sdk` ← `pico_tui`.

## Consequences

- Clear separation mirrors Pi's own package layout, making each concern independently testable and replaceable.
- More packaging ceremony (a uv workspace, four `pyproject.toml` files) than a single package would need.
- The `pico_sdk` boundary is the public surface: external consumers and the TUI both go through it, so `pico_core` stays a pure engine.
