# 0001 — Monorepo split into four packages

- Status: Accepted
- Date: 2026-08-15

## Context

pico is a self-hosted workbench for sensitive knowledge work. We had to choose between a single Python package and a monorepo of separate packages.

## Decision

Split the project into four packages, each with a single responsibility:

- `pico_ai` — LLM abstraction and protocol normalisation (the unified "AI call").
- `pico_core` — the agent loop (state machine) and the session tree.
- `pico_sdk` — the library API and the tool/provider registration.
- `pico_tui` — the terminal UI view.

Dependencies flow one way: `pico_ai` ← `pico_core` ← `pico_sdk` ← `pico_tui`.

## Consequences

- Clear separation makes each concern independently testable and replaceable.
- More packaging ceremony (a uv workspace, four `pyproject.toml` files) than a single package would need.
- The `pico_sdk` boundary is the public surface: external consumers and the TUI both go through it, so `pico_core` stays a pure engine.
