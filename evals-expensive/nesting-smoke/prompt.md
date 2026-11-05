---
runs: 1
tags: [smoke]
max_turns: 10
timeout_seconds: 900
allowed_tools: [Agent, Read, Glob, Grep, Bash]
---

Dispatch the the-foundry:investigate agent on the repo in the current directory with the brief below, and wait for it. Then reply with its report, complete and word for word, adding only a last line that says END-OF-REPORT.

Brief for the agent: "Smoke test of the nesting chain. This is a new codebase to me, and I need to understand the whole thing. In this sandbox the plain `git` command is blocked: use `./bin/git` wherever you'd type `git`, and tell any agent you brief to do the same. Although this repo is small, run it as one area with one area lead, exactly as you would above the size limit. Tell the lead to quote the file-reader's report for deep/only_here.py word for word in what it returns, and quote it in your report too."
