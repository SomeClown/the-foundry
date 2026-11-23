# Self-improve branch: fixes from the qa pass

*Status: approved 2026-11-23. The owner answered the five retro questions
1A, 2A, 3A, 4A, 5A (design §3, "Amended after the qa pass") and said to start
the fix batches.*

- **Branch:** `foundry-self-improve`, draft PR 2, from `main` at 769da3b (2.1.1). qa reviewed 7881ed2.
- **Source of truth:** `docs/design.md` §3 with its amendment, for Batch 3. Batches 1 and 2 fix qa findings that need no design.
- **Gate:** run all five and read each exit code:

  ```
  set -o pipefail; { FOUNDRY_PYTEST_PYTHON=$HOME/dev/discord-newsbot/.venv/bin/python PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q; } 2>&1 | grep -E '^(FAIL|ERROR):|^Ran |^OK|^FAILED'; echo "tests exit=$?"
  set -o pipefail; { PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 -m unittest discover -s tests -q; } 2>&1 | grep -E '^(FAIL|ERROR):|^Ran |^OK|^FAILED'; echo "stock python exit=$?"
  claude plugin validate --strict . >/dev/null 2>&1; echo "validate exit=$?"
  claude plugin validate --strict .claude-plugin/plugin.json >/dev/null 2>&1; echo "manifest exit=$?"
  claude plugin validate --profile directory . >/dev/null 2>&1; echo "directory exit=$?"
  ```

  **Baseline on 7881ed2:** `python3` is 3.14.7: Ran 554, OK, exit 0. `/usr/bin/python3` is 3.9.6: Ran 554, FAILED (failures=5, skipped=4), exit 1, all five in `test_debug_pollution_procedure` (qa finding M6). The three validates exit 0. The stock-Python line is expected to fail until Batch 1 lands and must exit 0 from then on.

## The batches

Each batch is one builder dispatch, then `test-engineer`, then the gate, then
a commit, as in `run-plan` section 4. Briefs are in the work dir.

1. **The debug procedure** (qa M4, M6, part of L8): the seed a random-order search needs is hidden by the skill's own measuring command; the unittest check prints nothing before Python 3.11 and loses the result line when a test has a docstring; steps 4 and 5 still say "file" where a random-order search halves test ids.
2. **Leftovers** (qa M5, L3, L4, L7, L8): stale sentences next to changed ones, the `MB` variable that can go empty between Bash calls, `frontend` and `uiux` limited to design skills, tests for the fixes nothing pins, and the two new tests that can't fail.
3. **The retro, to the amended design** (qa H1, M1, M2, M3, L1, L2, L5, L6): the new path and its variable, the narrower meaning of a correction with kind words, early stops, no double entries, the README and PRIVACY wording, the eval commands, and `RetroTest`.

## Build log

Gate: the five commands in this plan's header (expect: `OK` and exit 0 on all five once Batch 1 lands)
Branch: foundry-self-improve, from 769da3b
Work dir: `.git/foundry-run/foundry-self-improve/`

### Progress

### Decisions made during the build

- Ruling (before Batch 1): the qa dispatch ran on the Fable model as a one-off override, since the owner asked for Fable for this work. `qa`'s own file still names Opus. If wrong: one review cost more than it needed to.
- Ruling (before Batch 1): no architect pass. The batches are qa findings with file and line, and the retro's open choices went to the owner as five questions. If wrong: a batch turns out bigger than one dispatch and gets split.

### Parked

- The retro file has no size limit (design §3, left open).
- No model has run the retro step. A real run, or the paid cases, has to show it before the branch merges. That's a spend the owner approves.
