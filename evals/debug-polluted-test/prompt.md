---
runs: 2
tags: [debug]
max_turns: 30
timeout_seconds: 600
allowed_tools: [Skill, Read, Edit, Write, Bash, Glob, Grep]
disallowed_tools: [Agent]
---

Follow the the-foundry:debug skill (load it with the Skill tool). The repo is in the current
directory. (Test harness note: you can't dispatch subagents here. Where the skill says to dispatch a Foundry agent, do that agent's work yourself and say which agent it would have been.) You can't wait for user replies: if you'd ask something, write the
question down and carry on with the most reasonable assumption. Don't commit.

The user's message: "test_report_header_uses_dollars fails when I run the whole suite but passes
when I run that file on its own. It started around when I added the euro invoice test."

When done, reply with the root cause in one sentence, the evidence, what you changed and why
there, and the proof (commands and real results).
