---
runs: 2
tags: [brainstorm]
max_turns: 4
timeout_seconds: 300
allowed_tools: [Skill, Read]
---

Follow the the-foundry:brainstorm skill (load it with the Skill tool). Project: a Python Discord bot that posts a daily news digest per server, one embed per game per day in that game's channel. It runs in Docker with SQLite and an APScheduler job runner. You can't read
     the code in this test. Reply with exactly the message you would send the user, and nothing else.

USER: I'd like the bot to post a weekly recap every Sunday, the stories people reacted to most. Can we brainstorm it?
