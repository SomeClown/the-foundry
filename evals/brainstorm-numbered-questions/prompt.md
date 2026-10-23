---
runs: 2
tags: [brainstorm]
max_turns: 4
timeout_seconds: 300
allowed_tools: [Skill, Read]
---

Follow the the-foundry:brainstorm skill (load it with the Skill tool). Project: a Python Discord bot that posts a daily news digest per server, one embed per game per day in that game's channel. It runs in Docker with SQLite and an APScheduler job runner. You can't read
     the code in this test. Here is the conversation so far; reply with exactly your next message
     to the user, and nothing else.

USER: I'd like the bot to post a weekly recap every Sunday, the stories people reacted to most. Can we brainstorm it?

ASSISTANT: If you'd rather skip the questions and have me just start, say so. Otherwise: walk me through the last time you wished this recap existed. Who was it for, and what were they trying to find?

USER: Mostly for people who skip the dailies during the week. Last Sunday I scrolled back through six digests to find a story a friend asked about. I want one post that catches people up.
