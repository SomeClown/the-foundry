---
runs: 2
tags: [ship]
max_turns: 4
timeout_seconds: 300
allowed_tools: [Skill, Read]
---

Follow the the-foundry:ship skill (load it with the Skill tool). You're the main session in the
Claude desktop app. The user approved: "push, open the PR, squash-merge once CI is green, tag
v2.5.0, wait for the tag's image build, give me the deploy commands." You pushed, opened PR #70,
and bound it to the app's PR monitor. Status: 1 check pending, mergeable. The app doesn't let you
poll CI with gh, cron, scheduled wakeups or monitors.

In under 200 words: (1) what you do now and say to the user; (2) what you do when the user later
says "CI's done, carry on"; (3) after pushing the tag, how you wait for its build.
