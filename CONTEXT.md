# Pico Sovereign Workbench

A self-hosted, air-gapped workbench for routine but sensitive knowledge work. All models, tools, and documents run on the organization's own hardware; nothing leaves the premises.

## Language

### Work execution

**Agent**:
The workbench agent that plans multi-step tasks and calls local tools to produce deliverables.
_Avoid_: chatbot, assistant

**Cwd-jail**:
The folder the agent was opened in; the agent may only read, write, or execute inside it.
_Avoid_: sandbox, container, Docker

**Turn**:
One user message plus the agent's full response, including any tool calls it makes.
_Avoid_: iteration, step

**Tool**:
A local capability the agent can invoke (file access, document emit, knowledge search, document read).
_Avoid_: plugin, extension, function

**Deliverable**:
A real work product emitted as a file: Word, Excel, PowerPoint, working code, or a calculation with steps shown.
_Avoid_: chat reply, draft text

**Approval note**:
The Word deliverable drafted from inspection findings plus knowledge-base citations.
_Avoid_: report, letter

### Models

**Router**:
Picks the model for each task from the registry by capability label.
_Avoid_: dispatcher, orchestrator, judge

**Registry**:
The `models.yaml` list of usable models with their capabilities and VRAM cost.
_Avoid_: model list, config

**Capability**:
A static task label (`code`, `summary`, `vision`, `ocr`) assigned to a model in the registry.
_Avoid_: skill, modality

**Testing-only provider**:
The OpenRouter cloud backend, kept for routing tests on small GPUs and slated for removal.
_Avoid_: cloud model, fallback

### Knowledge and documents

**Corpus**:
The folder-mounted set of manuals, SOPs, and past correspondence the knowledge base indexes.
_Avoid_: knowledge base, DMS, database

**Inspection finding**:
A structured fact extracted from a scanned report or drawing, with its source page retained.
_Avoid_: OCR text, summary

### Provenance

**Session**:
One persisted unit of work, represented as a tree of nodes.
_Avoid_: conversation, chat

**Node**:
An immutable, append-only unit of event data in a session. Once written it is never edited or deleted.
_Avoid_: message, event

**Branch**:
A timeline: the sequence of nodes from the root to a leaf.
_Avoid_: thread, history

**Fork**:
Rewinding to an earlier node and starting a new branch from it.
_Avoid_: rollback, undo

**Trace**:
The live projection of a session's tool subtypes (`router.decision`, `kb.hit`, `ocr.page`) shown in the Tracing tab.
_Avoid_: log, span export

**Offline run**:
A run with no external network (venue Wi-Fi off); the proof of the sovereign claim.
_Avoid_: air-gap certificate, firewall attestation
