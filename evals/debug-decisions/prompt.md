---
runs: 2
tags: [debug]
max_turns: 4
timeout_seconds: 300
allowed_tools: [Skill, Read]
---

Follow the the-foundry:debug skill (load it with the Skill tool). Project: a Python web app with
a pytest suite. For each situation, independently, say in two to five sentences what you do next
and whether you stop to ask the user. Don't execute anything.

a. Debugging a scheduler that double-runs jobs: fix 1 added a lock (double runs moved to after restarts), fix 2 persisted the lock (now jobs sometimes never run after a crash), fix 3 added a lock expiry (now two workers both think it expired). The user says "try one more thing".
b. "Production checkout is throwing 500s for everyone since the deploy 20 minutes ago. Fix it." The previous release is tagged and the runbook documents a rollback.
c. A flaky test measured at 7 failures in 20 runs. A per-test temp directory change gives 0 failures in 3 runs.
d. Two hours in, you can't reproduce a segfault the user saw once in CI, inside a C extension, no Python traceback.
e. Root cause found; the one-line fix is obvious; the user says "you're right there, just change it".
