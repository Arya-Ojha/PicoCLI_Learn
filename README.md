# pico

A self-hosted, air-gapped AI workbench for sensitive knowledge work. Nothing leaves the premises.

`pico` works inside the folder you open it in (cwd-jail): reading, writing, and editing files, searching the local corpus, reading scanned documents, and emitting real deliverables (Word, Excel, PowerPoint, code, calculations with steps). It plans multi-step work, keeps an append-only, branchable session history with a live trace, and automatically compacts context to stay within the model's token budget.

```text
pico_ai ─► pico_core ─► pico_sdk ─► pico_tui
 (LLM)      (agent        (library      (terminal UI)
            loop/session)  API)
```

## Features

- **Workbench runner** — `pico run "do a task"` completes a task end-to-end with a single prompt.
- **Interactive TUI** — `pico-chat` is a full terminal UI (Textual + Rich) for back-and-forth sessions, including a realtime Tracing tab.
- **Local tools** — `read`, `write`, `edit` (search/replace patches), `bash` (cwd-jailed), `ocr_read` (vision-slot extraction subagent for PDFs/images), `summarize` (summary-slot fast model for summary-grade tasks), and `todo_write` (session-scoped work tracking for multi-step tasks).
- **Fully local by default** — models are served by a loopback vLLM server (`http://localhost:8000/v1`): no cloud, no API key, nothing leaves the machine. The OpenRouter cloud backend is kept for testing only and slated for removal.
- **Capability router** — `models.yaml` maps task capabilities (`code`, `summary`, `vision`, `ocr`) to models; adding a model is one registry entry.
- **Reasoning & usage** — thinking blocks are preserved in the transcript; token counts are tracked.
- **Session tree + trace** — sessions are persisted as append-only trees of nodes; you can resume, rewind, and fork branches. The trace is a live projection of tool subtypes.
- **Auto-compaction** — context is summarised automatically at a token threshold, plus a manual override.
- **Tool registration** — register providers, tools, and lifecycle hooks; load tool modules from a directory.
- **Autonomous loop** — no approval prompts: it self-corrects by looping between streaming and tool execution.

## Packages

| Package | Responsibility | ADR |
|---|---|---|
| `pico_ai` | LLM abstraction; unified "AI call" + OpenRouter client | ADR-0001 |
| `pico_core` | The finite-state-machine agent loop + append-only session tree | ADR-0001, ADR-0002 |
| `pico_sdk` | The `AgentSession` API + tool/provider registration | ADR-0001 |
| `pico_tui` | The interactive terminal UI (Textual + Rich) | ADR-0001 |

Dependencies flow one way — `pico_ai` ← `pico_core` ← `pico_sdk` ← `pico_tui` (see [ADR-0001](docs/adr/0001-monorepo-package-split.md)). Sessions are a tree of immutable, append-only nodes (see [ADR-0002](docs/adr/0002-tree-based-session.md)).

## Requirements

- Python **3.12+**
- [uv](https://docs.astral.sh/uv/) (workspace + dev tooling)
- A local [vLLM](https://docs.vllm.ai/) server with a tool-capable model (e.g. a Qwen coder or Llama-3.x instruct build — the agent loop depends on tool calls)

## Installation

```bash
uv sync
```

## Configuration

### 1. Start your local model

```bash
# serve a tool-capable model with an OpenAI-compatible API
vllm serve qwen2.5-coder-32b-instruct --port 8000
```

On first launch pico queries the server's served models: a single served
model is used directly (and remembered), several are listed with a hint to
pick one via `/model` in the TUI. If the server is down you get a warning
instead of a cloud fallback — nothing ever leaves the machine unasked.

### 2. Optional `settings.json`

Create `~/.pico/settings.json` to override defaults:

```json
{
  "provider": "local",
  "base_url": "http://localhost:8000/v1",
  "model": "",
  "context_window": 128000,
  "reserve_tokens": 16384,
  "session_dir": "~/.pico/sessions"
}
```

- `"model": ""` means auto-detect served models. Set it to pin a model id.
- Inside the TUI, `/provider` shows the active backend; `/provider local`
  and `/provider openrouter` switch backends at runtime (an optional second
  word pins the model, e.g. `/provider local tiny-llama`). The choice is
  remembered. Headless runs accept `--provider local|openrouter` the same way.
- Match `context_window` to your served model's max — the default (128000)
  likely exceeds small local models.
- Cloud testing only: `"provider": "openrouter"` re-enables the OpenRouter
  backend (then `OPENROUTER_API_KEY` must be set); it is slated for removal
  in the final version.

## Usage

### Workbench runs

```bash
# complete a task in one shot
uv run pico run "explain what this repo does"

# let the agent run shell commands (bash is on by default)
uv run pico run "run the tests and fix failures"

# work in another directory, pick a model
uv run pico run "summarize this code" --cwd D:\some\repo --model openai/gpt-4o-mini

# resume a previous session by id
uv run pico run "continue" --session <session-id>
```

Flags for `pico run`:

| Flag | Purpose |
|---|---|
| `--no-bash` | Disable bash execution, cwd-jailed (on by default) |
| `--model <name>` | Override the configured model |
| `--cwd <path>` | Set the working directory |
| `--session <id>` | Resume an existing session |

### Interactive TUI

```bash
uv run pico-chat
```

`pico-chat` shares the same flags. Inside the prompt you can type a message or use:

| Slash command | Key | Action |
|---|---|---|
| `/help` | `F1` | Show help |
| `/history` | `Ctrl+H` | List session nodes (with indices for `/fork`) |
| `/compact [text]` | `Ctrl+K` | Compact context (optionally with steering text) |
| `/provider ...` | — | Show or switch backends: `local` \| `openrouter` (optional model) |
| `/local ...` | — | Show or set model endpoints: bare `/local` opens the 3-slot popup (coding/reasoning, vision, summary — each with its own URL); `/local <url>` and `/local vision\|summary <url>` set one slot |
| `/fork <n or id>` | — | Rewind to a node and start a new branch |
| `/undo` | `Ctrl+Z` | Rewind to the previous user turn |
| `/quit` | `Ctrl+Q` | Save the session and exit |

Tool activity is rendered inline — bash commands echoed before running (green), and tool calls/results shown as color-coded panels (`read` blue, `write` yellow, `edit` magenta, `bash` green).

## Where sessions live

Sessions are persisted as JSONL under `~/.pico/sessions/<id>.jsonl` by default (configurable via `session_dir`).

## Development

```bash
# run all tests
uv run pytest

# typecheck every package
uv run mypy packages/pico_ai/src packages/pico_core/src packages/pico_sdk/src packages/pico_tui/src
```

The test suite is network-free: it drives the whole agent loop through a scripted fake provider (`FakeProvider`) and a temporary filesystem, exercising `pico_ai`, `pico_core`, `pico_sdk`, and `pico_tui`.

## Domain vocabulary

See [CONTEXT.md](CONTEXT.md) for the full glossary. Key terms: **agent**, **cwd-jail**, **router** / **registry** / **capability**, **corpus**, **trace**, **approval note**, **deliverable**, **session**, **node**, **branch**, **fork**, **offline run**.

## Documentation

- [Domain guide for agents](docs/agents/domain.md)
- [Architecture decision records](docs/adr/)
- [Issue-tracker conventions](docs/agents/issue-tracker.md)
- Milestone specs: [headless agent](.scratch/headless-agent/spec.md), [terminal UI](.scratch/pico-tui/spec.md)
