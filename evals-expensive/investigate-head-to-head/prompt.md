---
runs: 1
tags: [head-to-head]
max_turns: 12
timeout_seconds: 3600
allowed_tools: [Agent, Read, Glob, Grep, Bash]
---

Dispatch the the-foundry:investigate agent on the repo in the current directory with the brief below, and wait for it. Then reply with its report, complete and word for word, adding only a last line that says END-OF-REPORT. Don't read the code yourself, and don't shorten or summarize the report.

Brief for the agent: "This is a new codebase to me, and I need to understand the whole thing. In this sandbox the plain `git` command is blocked: use `./bin/git` wherever you'd type `git`, and tell any agent you brief to do the same. In the route inventory, give every route its full path on its own line, never grouped under a prefix. Give every CLI subcommand as `fxctl <name>`. When a gotcha's source cites a ticket, incident, change number, or named event, quote that reference word for word next to the gotcha."
