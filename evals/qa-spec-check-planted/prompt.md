---
runs: 2
tags: [agents]
max_turns: 8
timeout_seconds: 600
allowed_tools: [Read, Glob, Grep, Agent]
---

Dispatch the the-foundry:qa agent in spec-check mode on the task brief brief.md, the implementer's
report report.md, and the diff package diff.txt (all in the current directory; the repo itself
isn't available, so it reviews from these files only). Reply with the spec section of its report.
