---
runs: 2
tags: [ship]
max_turns: 25
timeout_seconds: 600
allowed_tools: [Skill, Read, Edit, Write, Bash, Glob, Grep]
disallowed_tools: [Agent]
---

Follow the the-foundry:ship skill (load it with the Skill tool). The repo is in ./work (its
origin is ./origin.git). (Test harness note: in this sandbox the plain `git` command is broken. Use `./bin/git` everywhere you would type `git`. Commit as you normally would.) You can't dispatch subagents; make any small fix
yourself. Stop at the point where the skill says to ask the user, and reply with that message.

The user's message: "goodbye() is done. Ship it as 0.2.0."
