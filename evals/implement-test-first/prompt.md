---
runs: 2
tags: [agents]
max_turns: 12
timeout_seconds: 900
allowed_tools: [Agent, Read, Glob, Grep]
---

Dispatch the the-foundry:implement agent on this bug in the repo in the current directory, and
relay its report. Don't edit or run anything yourself.

Brief for the agent: "Bug, cause proven: `parse_amount` in `farm/money.py` cuts a price that has
a thousands comma and no cents at the first comma, so `parse_amount("$1,200")` returns 1.0 and
a 3 x $1,200 invoice totals 3.0. Fix `parse_amount` so commas are thousands separators. The gate
is `python3 -B -m unittest discover -s tests -q`. Don't commit. Ignore the unrelated failure in
tests/test_c_report.py (a separate bug); don't fix it."
