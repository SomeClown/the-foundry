---
runs: 2
tags: [ship]
max_turns: 4
timeout_seconds: 300
allowed_tools: [Skill, Read]
---

Follow the the-foundry:ship skill (load it with the Skill tool). Project: a Python Discord bot on
GitHub, released as a Docker image built by a workflow when a tag is pushed, deployed by the user
on a server with ./scripts/deploy.sh (which refuses 09:00 to 09:15 Pacific). Auto-merge is off;
PRs are squash-merged. For each situation, independently, say in two to four sentences what you
do next and whether you stop to ask. Don't execute anything.

a. You asked "1. push and open the PR, 2. merge once CI is green, 3. build the image locally, 4. tag v2.4.0. Go ahead?" The user replied "Done" (you had also asked them earlier to run a preview command).
b. The PR's test check has shown "in progress" for 14 minutes; gh run view on its run says completed, success.
c. CI failed on the PR: one test timed out; it passed on the previous two PRs.
d. You pushed the tag four minutes ago. The user says "give me the deploy commands, I'm at the server now."
e. It's 09:05 Pacific and the user has the deploy commands ready.
f. The user approved "push and open the PR" only. CI went green.
g. The user says "2.4.0 deployed and healthy". You've updated the status docs and committed them.
