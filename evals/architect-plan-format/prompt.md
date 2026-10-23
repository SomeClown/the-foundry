---
runs: 2
tags: [agents]
max_turns: 20
timeout_seconds: 900
allowed_tools: [Agent, Skill, Read, Write, Bash, Glob, Grep]
---

(Test harness note: in this sandbox the plain `git` command is broken. Use `./bin/git` everywhere you would type `git`. Commit as you normally would.)

1. Dispatch the the-foundry:architect agent to plan the implementation of `docs/design.md` §2
   in this repo (the current directory). Tell it the plan will be run task by task with the
   run-plan skill.
2. Save the plan it returns, verbatim, to `docs/plans/2026-10-23-top-words.md`.
3. Load the the-foundry:run-plan skill with the Skill tool; it ships a `scripts/task-brief`
   script in its base directory. Run that script on the saved plan for Task 1 and for Task 2,
   writing into `./briefs`, and show its output lines.
4. Finish by quoting, verbatim, the plan's header block and its whole Task 1 section.
