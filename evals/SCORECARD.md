# Scorecard

What the behavior cases scored, release by release. `evals/scorecard.py` writes the rows from the harness's `aggregate-result.json` (see "Recording results" in [README.md](README.md)); nothing reads them to pass or fail anything.

- **Started** is when the harness run began (UTC); **Plugin** the version it loaded; **Commit** the commit it ran on, passed in because the result file doesn't hold it; **Claude Code** the harness's version.
- **Fully passed** counts runs in which every grader passed. The harness's own pass mark depends on `--threshold` and isn't recorded.
- **Graders failed** names each grader that failed and in how many runs.
- **Cost** is the runs' cost plus their judging, in US dollars.

| Started (UTC) | Plugin | Commit | Claude Code | Case | Runs | Fully passed | Graders failed | Cost |
|---|---|---|---|---|---|---|---|---|
