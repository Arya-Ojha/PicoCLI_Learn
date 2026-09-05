# Cwd-jail as the sandbox

The problem statement requires sandboxed code execution, but Docker/gVisor is out of scope for this milestone and unsafe unsandboxed bash breaks the sovereign story. We decided the opened folder is the sandbox: resolved paths must stay inside it after `resolve()`, bash is cwd-locked with a 30s timeout and no network binaries, and every denial is traced.
