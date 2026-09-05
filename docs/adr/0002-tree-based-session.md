# 0002 — Tree-based, append-only session model

- Status: Accepted
- Date: 2026-08-15

## Context

A work session needs a persistence model. The obvious choice is a linear transcript, but a tree model offers rollback and parallel timelines.

## Decision

Model a session as a tree of immutable, append-only nodes. Each node carries an id, a parent pointer, a timestamp, and a payload (user / assistant / tool request / tool result / compaction summary). Nodes are never edited or deleted.

Branches are timelines from root to leaf; forking rewinds to an earlier node and starts a new branch. Only the active branch is sent to the model, so abandoned branches cost no tokens.

## Consequences

- Rollback and "what-if" exploration become cheap: rewind and fork instead of restarting.
- The append-only invariant makes sessions replayable and diffable.
- The agent loop must track the active branch and assemble context from it, which is more complex than a flat transcript.
