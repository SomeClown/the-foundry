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
- Batch 1: complete (from eb3cc78; gate: Ran 612, OK on python3 3.14.7 (1 skip, the seeded-loop run test, no pytest-randomly) and on /usr/bin/python3 3.9.6 (5 skips), validates 0/0/0; adversarial: 2 bugs in the first unittest line fixed in round 1, the line replaced by one grep in round 2 on a ruling; 2 of 3 rounds used)
- Batch 2: complete (from d357f25; gate: Ran 695, OK on python3 3.14.7 (1 skip) and /usr/bin/python3 3.9.6 (5 skips), validates 0/0/0; adversarial: no bugs, no fix rounds; every fix qa found unpinned now has a pin with a mutation that proves it)
- Batch 3: complete (from ccc350d; gate: Ran 815, OK on python3 3.14.7 (1 skip) and /usr/bin/python3 3.9.6 (5 skips), validates 0/0/0; adversarial: no bugs; 2 of 3 fix rounds used, one for a gap in my own design call and one for the heredoc marker and five prose findings; no real retro file was created)
- Docs: complete (design §3 As built; CHANGELOG, README and PRIVACY brought in line with the skills; one phrase re-pinned by test-engineer; a new PR description drafted in the work dir, not posted)
- After the run: the owner took both open recommendations (`user` first in the tie-break; the first real retro write, done). A small fix dispatch follows for the kind-word order and the misplaced sentence the real run found.
- Follow-up: complete (from 2b65dc5; gate: Ran 825, OK on both Pythons (1 and 5 skips), validates 0/0/0; `user` first among the kind words in both skills, the clean-run sentences back together, 91 mutations on the retro's pins)
- Paid cases, with the owner's OK (cap $15, spent $4.59), on 242d918:
  - debug tag x 2: exit 1, $3.47, 525 s. Five of six cases at or above 0.8: decisions 1.00, flaky-pressure 1.00, user-fix-is-right 1.00, wrong-total 1.00, polluted-test 0.88 (`ran-the-check` failed run 2, votes PASS FAIL FAIL). debug-production-report 0.67 in both runs (`asks-and-hands-over` FAIL FAIL FAIL each time).
  - run-plan tag x 2: exit 0, $1.12, 167 s. Both cases 1.00 in both runs. They are four-turn decision cases and don't reach the retro.
  - The retro in a model's hands: two debug hunts wrote one (flaky-pressure run 1, wrong-total run 2), each with the resolve command, the heading, the line shape, a kind word and `retro exit=0`, and each said so in its report. The other full hunts had nothing to correct and wrote nothing.
  - The harness runs each case with its own throwaway home (`/private/tmp/e-.../home`), and the caller's `FOUNDRY_RETRO_FILE` did not reach the session: both writes resolved to that home's `.foundry/retro.md`. The real file's checksum was the same before and after. So the prefix on the documented commands does nothing, and the real file was never at risk from these cases.
- Batch 4: complete (from c629b21; gate: Ran 857, OK on both Pythons (1 and 5 skips), validates 0/0/0; the eval prefix removed and the docs corrected, who a retro line names, debug's Production paragraph; adversarial: no bugs, no fix rounds; one phrase sent back by me, the ban on a leading `cd`)
- Re-run after Batch 4, on 8a73e2d: debug-production-report x 4: exit 0, $0.76, 105 s. 1.00 in all four runs; `asks-and-hands-over` PASS PASS PASS each time (12 of 12 votes, against 0 of 6 before the fix). Paid spend so far: $5.35 of the $15 cap.
- The retro's first repeat (`run-plan [missed]`, twice) went to the owner through `brainstorm` on 2026-11-23. Owner decisions: 1A (an unchecked finding is checked in run-plan's fix-batch step), 2A (qa labels each finding as run or read), 3A (design calls the session adds mid-run get brainstorm's cold read before they're briefed), 4A (a finding only a paid run can check is parked and reported with its cost). Batch 5 builds it; the brief is `fix-5-brief.md` in the work dir, with the calls I made.
- Batch 5: complete (from b57cd50; gate: Ran 928, OK on both Pythons (1 and 5 skips), validates 0/0/0; run-plan checks a read-only finding before building on it and parks one only a paid run can check, qa labels each finding, the session's own design calls get a cold read; adversarial: no bugs, no fix rounds; the new eval situation h hasn't been run)
- Paid check of Batch 5, on b7017d5: run-plan-decisions x 4: exit 0, $1.15, 181 s. 1.00 in all four runs, all eight items; the new item h PASS PASS PASS each time. Every answer batched the finding qa had run, parked the one qa had only read, and carried on. I had told the owner about $0.55, the price of two runs, and ran four: $0.60 over what I quoted. Paid spend so far: $6.50 of the $15 cap.

### Decisions made during the build

- Ruling (before Batch 1): the qa dispatch ran on the Fable model as a one-off override, since the owner asked for Fable for this work. `qa`'s own file still names Opus. If wrong: one review cost more than it needed to.
- Ruling (before Batch 1): no architect pass. The batches are qa findings with file and line, and the retro's open choices went to the owner as five questions. If wrong: a batch turns out bigger than one dispatch and gets split.
- Ruling (Batch 1): both adversarial failures are real bugs, not misread tests. The brief says the line reads the victim's own result; a victim that writes to stderr (`... noise`, verdict on the next line) and a failing subTest (a bare `... `) both come out with no verdict, which step 4 can take for "didn't fail". If wrong: one fix round spent on cases nobody hits.
- Ruling (Batch 1, after fix round 1): the 600-character awk line is correct but not something a session can adapt by hand or a reader can check, and it decides the verdict out of sight. Replace it with one grep that shows three things (the victim's own line, a `FAIL:` or `ERROR:` header for the victim, the `Ran N tests` footer) and let the prose say how to read them. If wrong: the session misreads three lines where one would have done; the tests run the grep against real runs either way.
- Ruling (Batch 2): item 8 (the setup-failure reading) was carried from Batch 1 into this batch's brief instead of spending Batch 1's third fix round on it. Same file, one alternative in the grep. If wrong: nothing; it landed here.
- Ruling (Batch 3): my design call "skip the append when this run's heading is already in the file" loses the later lines of a run that stopped early, wrote its retro (5A), and went on the same day. Changed in design §3 to: drop the lines already there, append the rest. If wrong: a run's entry can sit under two blocks with the same heading, which reads fine.
- Ruling (Batch 3): the three `evals-expensive/` head-to-head commands stay without the `FOUNDRY_RETRO_FILE` prefix. They run `investigate` only, which has no retro step, and evals/README says so. If wrong: nothing reaches the real file from them either way.
- Ruling (Batch 3, after the adversarial round): fix five prose findings and the heredoc marker in round 2. The check for lines already written matches the project and run whatever the date (a run that crosses midnight no longer writes twice); the date is `date +%F`; the project name is the repo's top folder; debug's run name is defined; a tie between kind words goes to the first listed; lines are copied, not reworded. The marker becomes one a retro line can't equal, since a line reading exactly `RETRO` ended the heredoc and let later lines run as commands. If wrong: a few more sentences in two skills.
- Ruling (paid cases): debug-production-report's failure isn't from this branch. Section 1 of the debug skill is unchanged here, and the same grader failed in the 2026-10-23 and 2026-11-06 runs. It has now failed in three runs, and in both attempts this time, so it stops being "a known flaky grader" and becomes a finding: both answers handed the user a log command that writes a file on the server, where the grader wants read-only commands. If wrong: the cause is something else in the first message, and a wording fix won't move the score.
- Ruling (Batch 4): the builder's Production paragraph banned a `cd` before a command. Lifted: a `cd` on its own line above the command is fine. It's stricter than the grader's rule and than real use. If wrong: the re-run still fails and the rule gets tightened then.

### Parked

- Batch 5, from the cold read, all left: the cold-read rule sits in section 5's "only these stop the run" list and could be read as a stop; "run by you" doesn't say the check leaves the tree untouched; "parked" now has two meanings in run-plan; a parked HIGH finding's question doesn't have to carry its severity; a read-only agent as a "cheapest check" costs something, and "paid run" has no threshold.
- Batch 4, from the cold read, all left: pipes in a production command are neither allowed nor banned; a dispatched agent's work redone once fits both "counts" and "left out"; "corrected on the spot" could be read to cover a user's correction; evals/README states the harness's own-home behavior as fact from one run.
- Batch 3, from the last cold read, all left for the owner or a first real run: the tie-break puts `user` last, so a user correction that also fits `missed` is recorded as `missed`; a line exactly `FOUNDRY_RETRO_END` still ends the entry (the text forbids it, nothing enforces it); with any-date matching, a later separate run of the same plan that records an identical line has it dropped as already written; the no-repo fallback names no command; a resumed debug hunt's "name already in the file" doesn't say which file.
- Batch 3: in a git worktree the project's name is the worktree's folder, so one project can show under two names. A relative `FOUNDRY_RETRO_FILE` resolves against the Bash call's folder. `tests/test_investigate_batch1.py` keeps its older batch-named title. All left.
- From the paid cases, for the next fix round: the eval commands' `FOUNDRY_RETRO_FILE` prefix does nothing and its stated reason is wrong (the harness gives each case its own home); one retro line named `test-engineer` for a slip the session made itself, close to a copy of the skill's own example line, and counted something "rewritten once"; debug's first message on a production report keeps failing its grader.
- Batch 2: odd corners of the unittest readings, pinned as they stand: a `tearDownClass` failure after a passing victim reads "didn't fail"; a module that won't import reads "didn't match"; a `SkipTest` raised in class or module setup reads "didn't match".
- Batch 2 → Batch 3: `agents/frontend.md`'s new sentence is indented 2 spaces where the list item uses 3; the new test file and class are named after this run (`test_batch2_pin_mutations.py`, `Batch2PinsTest`) and want names a later reader understands.
- Batch 1 → carried into Batch 2 (item 8): a failing `setUpClass` or `setUpModule` in the victim's class leaves only `Ran 0 tests`, which the readings call "didn't match, fix the id". The id is right and the victim never passed. Found by test-engineer in round 2, pinned as it stands.
- Batch 1: a victim that prints its own `FAIL: test_y (...)` or `Ran 3 tests` line at the start of a line fools the grep. Left: it takes a test that prints unittest's own summary lines. Pinned as accepted.
- Batch 1: a unittest victim that's an unexpected success, skipped, or an expected failure shows no failure header, so the four readings call it "didn't fail". Left: a pollution search's victim is a plain failing test, and the victim's own line still shows.
- The retro file has no size limit (design §3, left open).
- No model has run the retro step. A real run, or the paid cases, has to show it before the branch merges. That's a spend the owner approves.

### Retro

- implement [fix-rounds]: read the unittest verdict from the verbose line, which a printing test or a failing subTest hides, then grew the fix into a 600-character awk program; should have read the end-of-run failure headers with one grep from the start (Batch 1, fix rounds 1 and 2)
- run-plan [missed]: my design call skipped the retro append whenever the run's heading was already in the file, which loses a stopped run's later lines; should have keyed the check on lines, which the builder pointed out (Batch 3, fix round 1)
- implement [missed]: put a sentence between the two clean-run sentences in run-plan's Retro text, so "Nothing goes to the cross-project file" read as a rule for every run; should have reread the paragraph after the insert (the first real run of the step, after Batch 3)
- run-plan [missed]: built an eval-command prefix and its explanation on qa's reading that the cases would write the real retro file, which qa had marked "by reading; not run"; should have checked what home the harness gives a case before building on it (the paid cases, after Batch 3)

Appended to `~/.foundry/retro.md` on 2026-11-23 with the owner's OK, following run-plan's Retro text as written: the first real run of the step. The file didn't exist, the folder and file were created, `retro exit=0`, and there were no earlier lines to repeat. The session was in auto mode, so this run doesn't show what the default mode's prompt looks like.

Found while following the text: in run-plan's Retro section, the sentence "Nothing goes to the cross-project file." now sits after the sentence about a `### Retro` section already in the log, so it reads as a rule for every run. It belongs with "write `- none` in the build log ... and stop there". A wording fix for a builder.
