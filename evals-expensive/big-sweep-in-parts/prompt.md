---
runs: 1
tags: [big-sweep]
max_turns: 40
timeout_seconds: 3600
allowed_tools: [Agent, Read, Glob, Grep, Bash, Write]
---

You're the session a user is working in, and they want to get to know the repo in the current directory. Dispatch the the-foundry:investigate agent with the brief below, and follow through on what its report tells you until the whole codebase has been read. Each time investigate returns a report, save it, complete and word for word, to `parts/part-<n>.md` (n counting from 1) with the Write tool before you do anything else. If a result arrives as a preview with the full text saved to a file, read that file and save the full text. Don't read the code yourself. When you're finished, reply with one line per saved file: its path and the report's first line.

Brief for the agent: "This is a new codebase to me, and I need to understand the whole thing. In this sandbox the plain `git` command is blocked: use `./bin/git` wherever you'd type `git`, and tell any agent you brief to do the same. In the route inventory, give every route its full path on its own line, never grouped under a prefix. Give every CLI subcommand as `twctl <name>`. When a gotcha's source cites a ticket, incident, change number, or named event, quote that reference word for word next to the gotcha."
