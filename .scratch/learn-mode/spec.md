---
title: Learn mode (SIH — learning theme)
labels:
  - ready-for-agent
---

# Learn Mode

## Problem Statement

Every AI coding tool does the learner's work *for* the learner. When a student or junior developer asks pico a question, the agent answers in a yolo style: it reads, writes, edits, and runs autonomously, leaving nothing learned. A learner who wants to *understand* their own codebase, get graded hints instead of full solutions, or study a new topic (e.g. React.js) has no mode that matches that intent — the tool has a single, always-on autonomous personality.

## Solution

Give pico two modes the user can flip mid-conversation:

- **Act mode** (default, formerly *yolo mode*) — today's autonomous behavior, unchanged.
- **Learn mode** — the agent guides instead of doing: it tutors over the learner's existing repository, walks a **hint ladder** so the learner gets only as much help as they've asked for, and builds a **lesson plan** for requested topics as self-contained HTML **lesson** pages with interactive **quizzes**, one lesson at a time, each opening in the browser when finished.

The mode is a per-message attribute: pressing **Tab** in the TUI toggles the current mode shown in the footer, and whatever mode is active stamps that outgoing message, swapping the system prompt for that turn only. Consecutive messages can run in different modes. Learn mode is also available headless via `pico run --learn`, and an opt-in `--strict-learn` flag hardens the guardrails by rejecting non-lesson writes.

Learn mode adds three research/content tools: **lesson** (write lesson pages), **fetch** (retrieve a web page), and **web search** (DuckDuckGo, zero API keys). The domain vocabulary (Learn mode, Act mode, Learner, Hint ladder, Escalation, Lesson, Lesson plan, Quiz) is maintained in the glossary (`CONTEXT.md`).

## User Stories

1. As a learner, I want to press Tab to toggle between act mode and learn mode, so that I can pick the behavior that matches the intent of my next message.
2. As a learner, I want the current mode shown in the TUI (footer/prompt area), so that I always know which mode my next message will be sent in.
3. As a learner, I want act mode to be the default on startup, so that pico behaves exactly as it does today until I opt into learning.
4. As a learner, I want to send one message in learn mode and the next in act mode, so that I can interleave asking for guidance with asking the agent to actually do things.
5. As a learner, I want each user message recorded in the session tree with the mode it was sent in, so that history and forks faithfully show which mode each turn ran in.
6. As a learner on my own codebase, I want the agent in learn mode to read and explain my repository instead of rewriting it, so that I can understand how it works.
7. As a learner debugging a bug, I want the agent to follow a hint ladder — concept first, then an algorithm outline or pseudocode, then a small snippet with a gap — so that I do the thinking and learn from the fix.
8. As a learner who is truly stuck, I want to say "I'm stuck" or "give me more of a hint" in natural language and have the agent escalate one rung of the ladder, so that help is graded and I never fall into over-assistance.
9. As a learner demanding the full solution, I want the agent to check once ("have you tried X first?") before revealing it, so that I get one last chance to solve it myself.
10. As a learner asking for help in learn mode, I want the agent to never author or modify my source code, so that I remain the sole author of my own code.
11. As a learner, I want to say "I want to learn about React.js" and have the agent research the topic and produce a lesson plan, so that I get a structured course instead of a wall of chat text.
12. As a learner, I want each lesson generated as a single self-contained HTML page with inline CSS and inline self-checking quiz JavaScript, so that it opens in any browser with no server or build step.
13. As a learner, I want lessons generated one at a time and each finished lesson to open in the browser automatically, so that I study and take its quiz before the next one is written.
14. As a learner, I want lessons for a topic stored in a dedicated directory with an index page that numbers and links them, so that my course for that subject is navigable from one place.
15. As a learner, I want every lesson to follow a consistent layout template, so that headers, explanation sections, code examples, and the quiz block are always where I expect.
16. As a learner, I want to ask for the next lesson only when I'm ready, so that the course proceeds at my pace.
17. As a learner in learn mode, I want the agent to keep its `read` tool, so that its guidance can reference my actual files.
18. As a learner in learn mode, I want `bash` to stay exactly as today (opt-in with `--allow-bash`), so that I can run my own code and interpret errors with the agent's help.
19. As a learner studying a topic, I want the agent to fetch documentation pages from the web, so that lessons are grounded in real, current material.
20. As a learner studying a topic, I want the agent to search the web with no extra API keys or setup, so that topic research works out of the box (including when judges run the demo).
21. As a learner, I want one unified learn-mode brain covering both repo tutoring and lesson building, so that the mode stays simple and its intent splits naturally from what I ask.
22. As a presenter, I want an opt-in strict mode in which writes outside the lessons directory are rejected with a "blocked in learn mode" tool result, so that the model self-corrects mid-loop if it ever ignores the prompt.
23. As a headless user, I want `pico run "..." --learn` to send its message in learn mode, so that the scripted CLI gets the same teaching behavior as the TUI.
24. As a user resuming an old session from before this feature, I want it to load unchanged and behave as act mode, so that existing saved sessions are not broken by the new schema.
25. As a SIH judge, I want a single sharp demo story — Tab on inside my repo, the agent switches from doing to teaching, asks me guiding questions, then builds a React lesson with an interactive quiz that opens in the browser — so that the "anything that helps learning" theme is instantly clear.

## Implementation Decisions

- **Package placement** follows the existing one-way chain (`pico_ai ← pico_core ← pico_sdk ← pico_tui`): new tools live in `pico_core.tools` alongside the four core tools; prompts and the mode field live in `pico_sdk`; the Tab toggle, mode indicator, and `/learn` command live in `pico_tui`. No new package, no new dependency direction (respects ADR-0001; session-tree change respects ADR-0002's append-only constraint).
- **Vocabulary**: "act mode" is the canonical name for the default autonomous behavior; *yolo* survives as an informal synonym. Glossary (`CONTEXT.md`) now defines Act mode, Learn mode, Learner, Hint ladder, Escalation, Lesson, Lesson plan, Quiz.
- **Per-message mode semantics**: the mode is not a session-wide switch. The TUI holds a current-mode flag, Tab toggles it and the footer reflects it; the flag stamps each outgoing message and the system prompt used for that turn is swapped accordingly (learn prompt vs default act prompt). The flag persists across messages until toggled again. Default on startup: act.
- **System prompt design**: exactly two prompts. The existing default acts as the act-mode prompt. One new unified learn prompt with two sections: (1) *repo tutoring* — read and explain, never author the learner's code, walk the hint ladder (concept → algorithm outline/pseudocode → snippet with a gap → full solution only on explicit natural-language escalation, checking once before revealing a solution); (2) *lesson building* — research with fetch/web search, design a lesson plan, write ONE lesson page at a time using the lesson tool, embed a self-checking quiz, open it in the browser, then wait for the learner.
- **Schema change**: `UserPayload` gains an optional `mode: str = "act"` field (values `"act"` | `"learn"`). Append-only-compatible: old session JSONL without the field loads and behaves as act mode.
- **Loop integration**: `AgentLoop.system_prompt` is already a mutable attribute; the per-turn swap happens where the loop assembles the `AICallRequest` — the run/stream entry point accepts the mode and sets the prompt for that turn only. No new FSM state represents modes; the mode annotates a turn.
- **Tab binding**: an App-level `Binding("tab", ..., priority=True)` — verified against the locked Textual release (Input does not handle Tab; priority bindings win over Screen focus traversal). The action must not blanket-swallow Tab: when the binding shouldn't consume the key, raise Textual's skip sentinel so normal focus traversal still works.
- **Discoverability**: `/learn` slash command toggles the same flag as Tab; both appear in `/help`, and the footer shows `[learn]` / `[act]`.
- **Headless**: `pico run` gains `--learn`; the flag stamps the run's message and selects the learn system prompt for the run's calls.
- **New tools** (same `Tool` protocol, registered alongside the four core tools):
  - **Lesson tool** — writes only `.html` files; validates the resolved target stays inside the topic's lessons directory (rejects `..` escape, non-lesson dirs); creates the topic directory and `index.html` if absent; derives the next numbered page name (`NN-slug.html`); renders a fixed single-file template constant (topic header + lesson number, explanation sections, code examples, quiz block with inline self-checking JS, no external assets); links the new page from the topic index; then opens it via an injected browser-opener callable (default: OS default browser), closing that seam for tests. Lesson directory convention: `pico-lessons/<topic-slug>/`.
  - **Fetch tool** — HTTP GET via an injected async client (stdlib-based default), returning readable text/HTML; timeouts and non-200s surface as tool errors, not exceptions (matching core-tool conventions).
  - **Web search tool** — requests the DuckDuckGo HTML results page through the same injected client, parses result titles/URLs/snippets with the stdlib HTML parser; zero API keys; the transport is injected so the provider is swappable later (e.g. Tavily/Serper) without changing the tool surface.
- **Strict mode**: opt-in flag (`--strict-learn`, on both TUI and headless entry points, default off). When on, write/edit requests whose target is outside the lessons directory return a tool result "blocked in learn mode: pico doesn't write the learner's code — explain instead" (surfaced as a normal `ToolOutcome` error so the model self-corrects in-loop); lesson-path writes pass. Default stance is prompt-first, as the loop may occasionally leak code in chat and that is accepted.
- **Tool panel colors**: the TUI renderer's per-tool color map gains an entry for each new tool so lesson/fetch/search panels render with distinct colors consistent with the existing four.
- **Docs**: README documents the Tab toggle, `/learn`, `--learn`, `--strict-learn`, the lesson directory layout, and the three new tools.

## Testing Decisions

- **What makes a good test here**: external behavior only — which system prompt the loop sends per turn, which files the tools create, what the TUI parses and renders. No assertions on internal flags, prompt-assembly helpers, or mode bookkeeping internals. All tests stay network-free (repo convention: `FakeProvider` + temp filesystem), async via the workspace `pytest-asyncio` auto mode, using `tmp_path` like prior art.
- **Seam 1 — provider seam** (prior art: `tests/conftest.py`'s `FakeProvider` + `tests/test_agent_session.py`): drives the whole agent session end-to-end. Covers: two consecutive messages (learn-stamped, act-stamped) ⇒ the captured `AICallRequest.system` shows the learn prompt for turn 1 and the act prompt for turn 2; session round-trip ⇒ user payload persists the mode (absent/unset ⇒ defaults to act for sessions created before this feature); `--learn` headless run ⇒ its turn carries the learn prompt.
- **Seam 2 — tool seam** (prior art: `tests/test_tools.py`): plain async tests against `tmp_path`. Covers: fetch with a canned injected transport (status, body, error cases — no socket); web search asserting parse results from a canned DuckDuckGo HTML fixture; lesson tool asserting numbered-page creation (`NN-slug.html`), topic directory + `index.html` creation and linking, non-HTML/`..`-escape rejection, and its injected opener not opening a real browser (the test injects a no-op opener); strict guard applied to write/edit ⇒ non-lesson paths error with the blocked-in-learn-mode message, lesson paths pass.
- **Seam 3 — TUI seam** (prior art: `tests/test_tui.py`): pure dataflow tests — `parse_line("/learn")` returns the new `Command`; render-swatch tests for lesson/fetch/search panels get the expected color and shape.
- **Bonus seam — live pilot test for the Tab toggle** (explicitly requested): a Textual pilot test constructing the app with a scripted session, presses Tab, asserts the footer reflects learn mode, presses Tab again, asserts it flips back. Confirms the priority binding works with the Input focused and that focus traversal is not broken.

## Out of Scope

- A servered/login-based course platform — lessons are local static HTML only.
- Authenticated search APIs (Tavily/Serper/Brave) — DuckDuckGo only, with a later swap point.
- Spaced-repetition, progress tracking, scores, persistent quiz results — client-side self-check only; progress tracking is deferred to v2.
- Sandboxed learning mode bash — bash stays exactly as it is today (opt-in).
- Redesign of the act-mode prompt.
- Persisting the *current* mode flag in the session tree — only individual message payloads carry their mode; the flag is process-local.

## Further Notes

- The enforcement posture (prompt-first + optional strict guard) was consciously discussed; strict mode is opt-in so the prompt drives behavior by default, and the strict guard exists for demo reliability.
- Domain vocabulary is in `CONTEXT.md`; no new ADR needed — none of these decisions are painful enough to reverse that they justify the journal entry.
- SIH pitch one-liner: "pico switches from *doing* to *teaching* — a mentor that has read your repository, walks you up the hint ladder, and builds HTML lessons with quizzes that open in your browser."