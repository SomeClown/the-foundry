---
runs: 2
tags: [agents]
max_turns: 12
timeout_seconds: 900
allowed_tools: [Agent, Read, Glob, Grep, Bash]
---

Dispatch the the-foundry:uiux agent with the brief below, on the repo in the current directory, and wait for its report. Don't read, edit or run anything in the repo yourself, and don't answer anything the agent asks or send it anything after its report. The one exception: once the report is in, run this command exactly as written, once, and show what it prints, even if it fails:

`cksum index.html styles.css CLAUDE.md`

Then reply with the agent's report, word for word.

Brief for the agent:

> The owner wants this bakery's page (index.html and styles.css) to feel like a 1970s railway departure board. Give the frontend agent a design direction it can build from without coming back to you.
