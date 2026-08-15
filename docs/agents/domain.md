# Domain docs

This repository uses a **single-context** domain-doc layout.

## Layout

- `CONTEXT.md` at the repo root — the project context every agent should read before starting work.
- `docs/adr/` — Architecture Decision Records (ADRs), the authoritative record of significant decisions.

## Consumer rules

- Read `CONTEXT.md` before beginning work to understand the project.
- When a decision is already recorded in an ADR, follow it; if work conflicts with a recorded ADR, flag the conflict rather than silently deviating.
- Add new ADRs under `docs/adr/` for significant decisions; do not overwrite existing ones.
