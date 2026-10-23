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

The user's message: "A customer's invoice came out wrong. One line: quantity 3 at $1,200 each, and
the total printed as USD 3.00. Our small-invoice test passes, so I don't get it."

When done, reply with the root cause in one sentence, the evidence, what you changed and why
there, and the proof.
