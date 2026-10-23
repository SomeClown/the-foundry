---
runs: 2
tags: [brainstorm]
max_turns: 12
timeout_seconds: 300
allowed_tools: [Skill, Read, Edit, Write, Glob, Grep]
---

Follow the the-foundry:brainstorm skill (load it with the Skill tool). Every part of the design
below has been approved; do the skill's "write the design" step now, in this repo. For the
builder check, don't dispatch anything: end your reply with one line saying what brief you'd
give the reviewer.

Approved (the user's decisions unless marked as your guess):
- A weekly recap every Sunday at the server's digest time, in the same channel as the daily digest (user picked 2A).
- "Reacted to most" = total emoji reactions on the digest message that carried the story (user picked 1A).
- Top 10 stories, Monday through Saturday in the server's time zone (your guess; user approved Part 1).
- On by default for new and existing servers; an admin command turns it off (user picked B).
- Skip the recap in a week with fewer than 3 stories (user: "a recap of two stories is silly").
- Ties go to the newer story (your guess; approved with Part 3).
- The user said: don't let this turn into an analytics dashboard.
