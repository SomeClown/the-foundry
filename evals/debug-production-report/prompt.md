---
runs: 2
tags: [debug]
max_turns: 12
timeout_seconds: 300
allowed_tools: [Skill, Read, Glob, Grep, Bash]
disallowed_tools: [Agent]
---

Follow the the-foundry:debug skill (load it with the Skill tool). The repo is in the current
directory. Reply with exactly your first message to the user.

The user's message: "A server got the same code alert posted twice last night, about a minute apart, both pinging @everyone."
