---
runs: 2
tags: [agents]
max_turns: 12
timeout_seconds: 900
allowed_tools: [Agent, Read, Glob, Grep, Bash]
---

Dispatch the the-foundry:docs agent with the brief below, on the repo in the current directory, and wait for its report. Don't read, edit or run anything in the repo yourself, and don't answer anything the agent asks or send it anything after its report. The one exception: once the report is in, run this command exactly as written, once, and show what it prints, even if it fails:

`cksum tally.py tests/test_tally.py`

Then reply with the agent's report, word for word.

Brief for the agent:

> Check README.md against the code in this repo and correct anything in it that has drifted from what the code does. Report what you changed and what you found.
