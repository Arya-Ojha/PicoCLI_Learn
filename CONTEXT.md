# Context

The domain vocabulary for **pico**, a Python CLI coding agent inspired by Pi's modular, plugin-driven architecture.

## Glossary

- **Agent** — the autonomous coding agent itself. It runs in **act mode** by default (informally, *yolo mode*): it acts on its own, without asking for approval at each step.
- **Act mode** — the default mode: the agent completes tasks autonomously on the user's behalf. Contrast with **learn mode**.
- **Session** — one persisted coding session, represented as a tree of nodes.
- **Node** — an immutable, append-only unit of event data in a session. Each node carries an id, a pointer to its parent, a timestamp, and a payload. Once written, a node is never edited or deleted — only built upon.
- **Payload** — the content of a node: a **user** message, an **assistant** message, a **tool request**, a **tool result**, or a **compaction summary**.
- **Branch** — a timeline: the sequence of nodes from the root to a leaf. A session can hold many parallel branches.
- **Fork** — rewinding to an earlier node and starting a new branch from it (for example, after a change that broke the codebase).
- **Turn** — one user message plus the agent's full response to it, including any tool requests it makes.
- **Tool** — a capability the agent can invoke. The core tools are **read**, **write**, **edit**, and **bash**.
- **Tool request** — the agent asking to run a tool.
- **Tool result** — the output returned by running a tool.
- **Compaction** — summarising older context so the session fits within the model's context window.
- **Context window** — the token budget of the model in use.
- **Reserve tokens** — the portion of the context window held back for the model's own response.
- **Provider** — an LLM backend. Every provider is reached through a single gateway and exposed as one unified **AI call**.
- **AI call** — the unified request/response shape used to talk to any provider.
- **Headless** — running the agent programmatically (as a library) with no terminal UI.
- **Extension** (also **plugin**) — a modular capability registered into the agent: a tool, a provider, or a UI widget. Extensions are loaded from a plugins directory or registered explicitly.
- **Learn mode** — a mode in which the agent restrains itself: instead of completing the task, it guides the user to complete it. It explains, questions, and plans lessons, but does not author the user's code. The opposite philosophy of acting autonomously.
- **Learner** — the user while a message is sent in learn mode.
- **Hint ladder** — the graded levels of help in learn mode: concept → algorithm outline/pseudocode → small snippet with a gap → full solution (only on explicit escalation).
- **Escalation** — moving up the hint ladder, culminating in breaking through to a full solution on the learner's explicit repeated request.
- **Lesson** — a single self-contained learning unit rendered as a static HTML page with embedded explanations and an interactive quiz (self-checking via inline JavaScript, no server).
- **Lesson plan** — the sequence of lessons the agent designs for a topic the learner wants to study (for example, "React.js fundamentals").
- **Quiz** — the interactive question section embedded in a lesson page, giving immediate feedback to the learner.
- **Lessons directory** — `pico-lessons/<topic-slug>/` under the working directory: each topic's numbered lesson pages plus an `index.html` lesson plan live there, inside the working directory and never outside it.
- **Fetch tool** — the learn-mode tool that retrieves the text of a web page, letting the agent research real material while building lessons.
- **Web search** — the learn-mode tool that runs a DuckDuckGo search and returns matching titles, URLs, and snippets. Zero API keys; the transport is injectable so a search API can be swapped in later.
- **Strict learn** — the opt-in hardening behind `--strict-learn`: `write`/`edit` whose target is outside the lessons directory is rejected with *"pico doesn't write the learner's code"*. Lesson-path writes always pass.
- **Lesson tool** — the learn-mode tool that writes one self-contained HTML lesson page and opens it in the browser.
