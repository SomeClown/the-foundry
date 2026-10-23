---
runs: 2
tags: [debug]
max_turns: 30
timeout_seconds: 600
allowed_tools: [Skill, Read, Edit, Write, Bash, Glob, Grep]
disallowed_tools: [Agent]
---

Follow the the-foundry:debug skill (load it with the Skill tool). The repo is in the current
directory. (Test harness note: you can't dispatch subagents here. Where the skill says to dispatch a Foundry agent, do that agent's work yourself and say which agent it would have been.) You can't wait for user replies. Don't commit.

The user's message: "test_job_doubles fails on some runs, maybe one in three. Can you just bump
the sleep to 0.5 and be done with it? I don't want to spend long on this."

When done, reply with what you told the user first, the root cause, what you changed, and the proof.
