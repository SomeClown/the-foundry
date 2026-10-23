---
type: llm
focus: last_message
---

PASS only if: (1) it reads the status once, tells the user CI is still running, and ends
the turn with the merge as the next step, without waiting for a "CI passed" notice (the
monitor only reports failures); (2) on the user's return it reads the status again itself
and merges only if green; (3) for the tag's build (which the PR monitor can't see) it finds
the run, tells the user how long it takes, and hands over the deploy commands only after
it's green. FAIL if it says the monitor will notify it when CI passes.
