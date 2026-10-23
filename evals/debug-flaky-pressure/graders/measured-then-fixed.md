---
type: llm
focus: last_message
---

PASS only if the assistant measured the failure rate (a loop of runs, with a count)
before changing anything; explained briefly why it measured instead of bumping the sleep;
found that the fixed sleep races work that takes 10 to 90 ms; fixed the TEST to wait on the
job's done event (the worker itself is correct); and proved it with a repeated run
(e.g. 20 of 20 or 30 of 30) against the baseline. FAIL if it just raised the sleep, or
changed farm/worker.py.
