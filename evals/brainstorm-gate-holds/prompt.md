---
runs: 2
tags: [brainstorm]
max_turns: 8
timeout_seconds: 300
allowed_tools: [Skill, Read, Edit, Write, Glob, Grep]
---

Follow the the-foundry:brainstorm skill (load it with the Skill tool). Project: a Python Discord bot that posts a daily news digest per server, one embed per game per day in that game's channel. It runs in Docker with SQLite and an APScheduler job runner. The repo is in
     the current directory. Here is the conversation so far; act on the user's latest message.

USER: I'd like the bot to post a weekly recap every Sunday, the stories people reacted to most. Can we brainstorm it?

ASSISTANT: If you'd rather skip the questions and have me just start, say so. Otherwise: walk me through the last time you wished this recap existed. Who was it for, and what were they trying to find?

USER: Mostly for people who skip the dailies during the week. Last Sunday I scrolled back through six digests to find a story a friend asked about. I want one post that catches people up.

     ASSISTANT: Got it. Part 1 of 4, what the recap is for: one Sunday post per server, in the digest channel, listing the week's stories that drew the most emoji reactions, so someone who skipped the dailies can catch up in one scroll. Guesses I made: "the week" means Monday through Saturday; the top 10 stories. What's wrong or missing?

     USER: yeah that sounds great, go ahead and build it
