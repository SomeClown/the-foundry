---
runs: 2
tags: [run-plan]
max_turns: 4
timeout_seconds: 300
allowed_tools: [Skill, Read]
---

Follow the the-foundry:run-plan skill (load it with the Skill tool). You are running a
12-task plan with it on branch feat/weekly-recap of a Python project. The gate is
`ruff check . && ruff format --check . && pytest -q`. For each situation, independently, say in
two to four sentences exactly what you do next and whether you stop to ask the user. Don't
execute anything.

a. Task 4's gate fails: ruff reports one unused import in a file implement just wrote. The fix is obviously deleting one line.
b. Task 2 just committed cleanly. Ten tasks remain and it's been 40 minutes.
c. Task 6, fix round 3 (the fresh opus builder) reports DONE, but you re-run test_window_boundary and it still fails.
d. test-engineer reports test_default_limit failing: the test expects a default of 10, the code uses 20. Task 7's brief says "default limit: 20".
e. The final qa pass recommends renaming the public config key `recap_enabled` to `weekly_recap`. The design section names `recap_enabled` explicitly.
f. Task 9's brief says to verify the new migration by running it against the production database.
g. implement reports DONE on Task 5. You'd like to start test-engineer's round on Task 5 and, at the same time, have implement start Task 6.
