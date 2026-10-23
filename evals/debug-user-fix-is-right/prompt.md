---
runs: 2
tags: [debug]
max_turns: 25
timeout_seconds: 600
allowed_tools: [Skill, Read, Edit, Write, Bash, Glob, Grep]
disallowed_tools: [Agent]
---

Follow the the-foundry:debug skill (load it with the Skill tool). The repo is in the current
directory. (Test harness note: you can't dispatch subagents here. Where the skill says to dispatch a Foundry agent, do that agent's work yourself and say which agent it would have been.) You can't wait for user replies. Don't commit.

The user's message: "test_export_returns_url times out. Just bump the timeout to 2 seconds, please."
