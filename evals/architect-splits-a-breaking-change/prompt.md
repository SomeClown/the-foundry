---
runs: 2
tags: [agents]
max_turns: 12
timeout_seconds: 900
allowed_tools: [Agent, Read, Glob, Grep]
---

Dispatch the the-foundry:architect agent with the brief below, on the repo in the current directory, and wait for its plan. Don't read, edit or run anything in the repo yourself, and don't answer anything the agent asks or send it anything after its plan. Then reply with the agent's plan, word for word.

Brief for the agent:

> Plan this change for the repo in the current directory: rename `customers.email` to `customers.contact_email`. Marketing wants the new name in every export by the end of the quarter. The service runs all day, and the runbook says a migration is applied while it keeps running.
