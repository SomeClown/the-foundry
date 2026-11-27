---
runs: 2
tags: [agents]
max_turns: 8
timeout_seconds: 900
allowed_tools: [Read, Glob, Grep, Agent]
---

Dispatch the the-foundry:qa agent to review the change in the current directory: the task brief
brief.md, the implementer's report report.md and the diff package diff.txt. package.json and
package-lock.json are as the change left them, and there is no git history. Wait for its report,
then reply with the report, word for word.
