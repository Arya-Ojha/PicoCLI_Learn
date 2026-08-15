# 03 — Tools: read / write / edit / bash

**What to build:** the agent can invoke the four tools, feed results back, and loop `streaming ⇄ tool_executing` until done. Bash echoes commands and requires an opt-in flag.

**Blocked by:** 02 — Tracer bullet: headless text response.

**Status:** ready-for-agent

- [ ] The agent can read a file, write (create/overwrite) a file, and edit a file with a surgical search/replace patch.
- [ ] The agent can run a bash command and receive its output and exit code.
- [ ] Tool results are fed back into the conversation so the model can act on them.
- [ ] The loop continues streaming ⇄ tool_executing until the model stops requesting tools.
- [ ] Bash commands are echoed before execution, and bash is disabled unless an opt-in flag is set.
- [ ] Tool errors (non-zero exit, missing file) surface as tool results rather than crashing.
