---
runs: 1
tags: [reply-size]
max_turns: 12
timeout_seconds: 3600
allowed_tools: [Agent, Read, Glob, Grep, Bash]
---

Dispatch the the-foundry:investigate agent on the repo in the current directory with the brief below, and wait for it. Then, before anything else, write two lines. Line 1: `RECEIVED: whole` if the agent result you got ends with the line `TAIL-MARK-6620`, otherwise `RECEIVED: preview`, followed by the notice that came with the result, quoted word for word. Line 2: `SAVED OUTPUT: read`, `SAVED OUTPUT: blocked` (and what blocked it), or `SAVED OUTPUT: none`; if there was a saved file, try to open it with Read before you write this line. Then reply with the report, complete and word for word, from the saved output if that's where the whole text is, adding only a last line that says END-OF-REPORT. Don't read the code yourself.

Brief for the agent: "This is a new codebase to me, and I need to understand the whole thing. In this sandbox the plain `git` command is blocked: use `./bin/git` wherever you'd type `git`, and tell any agent you brief to do the same. The user approved reading every file, whatever the count. Make the last line of your report exactly `TAIL-MARK-6620`."
