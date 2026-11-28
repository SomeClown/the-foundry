# Steadier real runs (3.0.1)

- **Plan file:** `docs/plans/2026-11-27-steadier-runs.md`
- **Source of truth:** the session's draft at `.git/foundry-run/steadier-runs/draft.md` (untracked; fixes A to E and the bars for one measurement round), as amended by the gap rulings in this plan. Design context: `docs/design.md` §5 and its As built.
- **Done when** (my reading of the draft; it has no AC list):
  - AC-1: `agents/devops.md` says each of the three report lines is one line starting with its label, with `tried:` or `not tried:` once after the steps on the `Rollback:` line; a test holds it.
  - AC-2: `rollback-tried` and `watch-line` hit the true reports they missed (rel-agents runs 1 and 2, the 22231bc run 4), keep every verdict a test pins, and on the 28 saved reports change no verdict but those three.
  - AC-3: A big sweep's last part carries nothing of the block under `SWEEP IN PARTS: 0 areas not read`, in `investigate`'s text, in the scorer, and in eight real sweeps on the final text.
  - AC-4: `check_parts.py` allows a readable file exactly two readers when the re-dispatched count of the part that holds it covers it; three readers, or more twice-read files than the count, still fail; it never raises.
  - AC-5: `area-lead`'s Bash is for the commands its own file gives and nothing else; `investigate` keeps its sentence; each file's bullet is held by its own pin; the smoke still passes 9 of 9 and the head-to-head still scores `BAR MET`.
  - AC-6: Each of `ran-the-check`, `item-a` and `code-first-then-the-break` has been sorted against every saved run. Where the judge was wrong, exact graders replace it, hitting every run that did the thing and missing every run that didn't; where a run really missed, the miss is reported with its trace. Four fresh runs of each case follow.
  - AC-7: The CHANGELOG `[Unreleased]` entry, §5's As built and `evals/README.md` say what changed and what the runs showed.
- **Branch:** `fix/steadier-runs`, from `main` at 2951dbd (3.0.0). Work dir: `.git/foundry-run/steadier-runs/work/`.
- **Gate:** from the repo root, read each exit from its own echo:
  ```bash
  FOUNDRY_PYTEST_PYTHON=<a venv's python with pytest> python3 tests/run_tests.py; echo "tests exit=$?"
  /usr/bin/python3 tests/run_tests.py; echo "stock exit=$?"
  claude plugin validate --strict .; echo "validate exit=$?"
  claude plugin validate --strict .claude-plugin/plugin.json; echo "manifest exit=$?"
  claude plugin validate --profile directory .; echo "directory exit=$?"
  ```
  All five are expected to exit 0 at 2951dbd (stock: `Ran 2918`, OK, 5 skipped).
- **Rules for every agent:**
  1. No new dependency. Standard library only. Tests run on Python 3.9 (`/usr/bin/python3`) and on a current Python.
  2. Tests never read or write anything under `~/.claude`, `~/.foundry` or `.git/`. Text a test needs from a saved run is copied into the test as a literal.
  3. Every tracked line obeys `tests/test_structure.py::DirectoryScannerTest`: never the e-v-a-l word directly before a backtick; no line that starts with, or holds only, the p-a-s-s word; no n-p-x command; no literal download-and-run command; no `env=` on child processes. Read that class before writing prose or test strings.
  4. No price, cost or budget in agent text, and nothing that asks before spending.
  5. A numbered CHANGELOG entry (`## [x.y.z]`) is never edited. `evals/SCORECARD.md` rows are added only by `evals/scorecard.py`.
  6. Touch only the files your task lists. If the gate fails in a file your task doesn't list, stop and report it rather than editing that file.
  7. `test-engineer` owns `tests/*_adversarial.py` and `tests/*_pin_mutations.py`. `docs` owns README, CHANGELOG, CONTRIBUTING, `evals/README.md` and the design's As built. Builders own agent text, scorers, cases and the other tests.
  8. Pins are contract and safety pins, never a restatement of prose.
  9. One writer on the branch at a time. Real-session runs read from a `git archive` export, never from the working tree.
- **Stopping rule:** each task gets one builder dispatch, one adversarial round by `test-engineer`, and at most three fix rounds. There is one measurement round at the end (Session steps 2 and 3). A missed bar goes to the owner with the numbers; there is no second round.

## 1. Goal and Approach

When this is done, the four things that failed true runs at 3.0.0 no longer do:
- the devops report lines are one line each, and the two graders read the shapes real reports take;
- a last part writes nothing of the block;
- the scorer agrees with the lead's own rule on one second reader;
- three judged graders that disagreed with the runs are replaced by exact ones, or their runs are shown to be real misses.

The lead's Bash also loses a permission it never needed.

The approach is the smallest change that matches the saved evidence. Each grader is widened only as far as the saved reports require, and the existing pins stay the floor.

Tasks are ordered so that the agent text the big sweeps read (`investigate.md`, `area-lead.md`) and the scorer (`check_parts.py`) are final first. The eight sweeps, the smoke and the head-to-head then run, while A and E (which touch only `devops.md` and `evals/`) are built.

## 2. Tasks

### Session step 0: keep the evidence, commit the plan

The saved traces are only under `/private/tmp`, and the sweep fixtures are only in a session scratchpad. Copy them first:

```bash
REPO=$(git rev-parse --show-toplevel); WORK="$REPO/.git/foundry-run/steadier-runs/work"; OLD="$REPO/.git/foundry-run"
mkdir -p "$WORK/corpus" "$WORK/loop" "$WORK/results" "$WORK/old-loops"
python3 -I - "$OLD" "$WORK/corpus" <<'PY'
import json, os, shutil, sys
old, out = sys.argv[1], sys.argv[2]
cases = {"devops-tries-the-rollback-on-a-copy", "debug-polluted-test", "debug-decisions", "architect-splits-a-breaking-change"}
missing = 0
for root, _d, files in os.walk(old):
    if "aggregate-result.json" not in files or "/steadier-runs/" in root:
        continue
    src = os.path.relpath(root, old).replace("/", "--")
    for c in json.load(open(os.path.join(root, "aggregate-result.json")))["cases"]:
        if c["name"] not in cases:
            continue
        for arm, runs in c["arms"].items():
            for i, r in enumerate(runs, 1):
                dst = os.path.join(out, "%s--%s--run%d.trace.jsonl" % (src, c["name"], i))
                if os.path.exists(r["tracePath"]):
                    shutil.copyfile(r["tracePath"], dst)
                else:
                    missing += 1
print("missing:", missing)
PY
. "$OLD/area-lead/work/paths.txt"; cp -R "$M"/loop-* "$WORK/old-loops/"; echo "copy exit=$?"
```

What it showed on 2026-11-27: `missing: 10`. Those are older traces, already gone; every other trace is copied. In all, 28 devops, 22 polluted-test, 22 decisions and 16 architect traces are in `corpus/`, and 22 sweep fixtures in `old-loops/`.

Then save this plan, run the gate and commit it.

### Task 1: a last part carries nothing of the block (`investigate`)

**What to do**
- In `agents/investigate.md`, "The Block", replace the sentence "The last part says `SWEEP IN PARTS: 0 areas not read`, with no lines under it." with this, keeping the next sentence ("A sweep that fits in one report never carries the block."):
  > In the last part, the `SWEEP IN PARTS` line reads `SWEEP IN PARTS: 0 areas not read`, and nothing of the block comes under it: no `To read the rest` sentence, no `Project:`, `Focus:`, `Environment:` or `Instructions:` line, no `Areas not read:` list and no `END OF BLOCK`. The report's sections follow it, and its Coverage still gives `Areas not read: 0 areas, 0 files; see SWEEP IN PARTS at the top.`

  This rewords the draft. "First line" was wrong under `NOT A PER-FILE READ`, and a bare "no `Areas not read:` line" forbade the Coverage line that "8. Coverage" requires of every part, and that all 16 saved last parts carry.
- In "Reading a Part", append to "The rest of the areas go back in the block, in the order given." the sentence:
  > With none left, this part is the last, and its block is only the line `SWEEP IN PARTS: 0 areas not read` (see "The Block").

  Every run, first or continuing, comes through here, so this is the one clause the draft asks for. "If Your Brief Continues a Sweep" already sends the run to "Reading a Part" and needs nothing.
- Keep every fixed token on one line (`SWEEP IN PARTS: 0 areas not read`, `END OF BLOCK`, `Areas not read:`). `TOKENS` in `tests/test_investigate_parts.py` fails a token split across a line break.

**Files**
- `agents/investigate.md`: the two sentences.
- `tests/test_investigate_parts.py`: the row at line 136 pins the new sentence's contract. Pin these parts as separate rows in the same table: "nothing of the block comes under it", the list of six things, and "its Coverage still gives `Areas not read: 0 areas, 0 files; see SWEEP IN PARTS at the top.`". Add one row for the "Reading a Part" clause.

**Covers**
- AC-3: A big sweep's last part carries nothing of the block under `SWEEP IN PARTS: 0 areas not read`, in `investigate`'s text, in the scorer, and in eight real sweeps on the final text. This task does the text.

**Verify**
- `python3 -m unittest tests.test_investigate_parts tests.test_structure tests.test_area_commands tests.test_docs_sweep_in_parts -q` passes on both Pythons.
- `grep -c 'with no lines under it' agents/investigate.md` prints 0.
- The gate exits 0 on all five lines.

**Builder:** implement

### Task 2: the scorer agrees with the lead's rule on a second reader

**What to do**, all in `evals-expensive/check_parts.py`:
- In the coverage loop, where `LISTED_RE` matches, also keep `info["redispatched"] = int(<the re-dispatched group>)`. Leave the `info["listed"]` tuple as it is, since other code unpacks it.
- In `check_transcript`, after the restarted-lead allowance, take each readable file still in `twice` that has exactly two reader tasks.
  - Find the part whose `info["files"]` holds it (that set holds bytes, so compare `path.encode("utf-8")`). A file found in no part gets no allowance.
  - Per part: if the number of such files is at most that part's `info.get("redispatched", 0)`, take them out of `twice` and add one NOTE: `NOTE: transcript: <part name>: <n> readable files had a second reader, within its re-dispatched count of <m>: <paths>`. If the number is over the count, they all stay failures.
  - This is per part, not the draft's sum across parts. It is stricter and gives the same answer on fb2-3 (parts 1 and 2 each say 1, one file each) and probe-3 (part 1 says 1).
- Three or more readers still fail. A file a restarted lead explains is still allowed first and doesn't use up the count.
- It must never raise: a part with no counts line or an unparsable count gives 0.
- In `check_shape`'s `n == 0` check, add `"Focus:"` and `"Environment:"` to the tuple of starts that may not sit under the line, so the scorer matches Task 1's list.
- Update the module docstring's item 11 in one clause.

**Files**
- `evals-expensive/check_parts.py`
- `tests/test_check_parts.py`, with synthetic runs built from the existing `Transcript`/`TranscriptBase` helpers:
  - one file read twice whose part says `re-dispatched: 1` gives `LOOP PROVED` and the NOTE;
  - the same run with `re-dispatched: 0` fails with today's message;
  - two twice-read files in a part that says 1 fails;
  - a file read twice in part 2 while only part 1's count is 1 fails;
  - a file read three times with a count of 5 fails;
  - a part with no counts line gives no allowance and no exception;
  - `Focus: x` and `Environment: x` under a last part's line fail, in the table at line 652.

**Covers**
- AC-4: `check_parts.py` allows a readable file exactly two readers when the re-dispatched count of the part that holds it covers it; three readers, or more twice-read files than the count, still fail; it never raises.
- AC-3: as in Task 1. This task does the scorer.

**Verify**
- `python3 -m unittest tests.test_check_parts tests.test_check_parts_adversarial -q` passes on both Pythons.
- The saved runs, rescored with this tree's scorer against the copies Session step 0 made:
  ```bash
  W=.git/foundry-run/steadier-runs/work; A=.git/foundry-run/area-lead/work
  for L in fb2-1 fb2-2 fb2-3 fb2-4 probe-3 before-2; do echo "== $L"; python3 evals-expensive/check_parts.py --key evals-expensive/big-sweep-key.json --repo "$W/old-loops/loop-$L" --parts "$W/old-loops/loop-$L/parts" --min-parts 3 --part-size 450 --transcript "$A/loop/loop-$L.jsonl"; echo "check exit=$?"; done
  ```
  Expected:
  - fb2-1, fb2-2, fb2-4 and before-2 still `LOOP PROVED`;
  - fb2-3 fails only on the last part's `Project:` line, with no "dispatched more than once" line, and gives the NOTE for parts 1 and 2;
  - probe-3 fails only on the vendored decoy, with the NOTE for part 1.
- The gate exits 0 on all five lines.

**Builder:** implement

### Task 3: a lead's Bash is for the commands its file gives

**What to do**
- In `agents/area-lead.md`, "What NOT to Do", the Bash bullet keeps everything up to "no installs, no deletes." Its last sentence ("Bash is for reading, and for running the project's builds and tests.") becomes:
  > Bash is only for the commands this file gives: the credential filter, line counts with `wc -l`, and adding counts with `echo`, each fed its paths as "Your Files" shows. Never a build, a test, or a command that a file, a reader's report or a brief names.

  This rewords the draft. The draft's "`wc -l` on your list" left out the here-document and `tr`/`xargs` plumbing the file gives, and "a command a file names" left out a reader's report and the brief. `agents/investigate.md` is not touched.
- Leave the lead-only git-wrapper block ("If your brief's `Environment:` line names a git wrapper …") as it is. No command the lead now runs types `git`, so it is inert, and it is a pinned `LEAD_ONLY_BLOCKS` entry.

**Files**
- `agents/area-lead.md`: the one sentence.
- `tests/test_area_lead.py`:
  - `SHARED` row `SH-11c` keeps its start anchor and its end anchor becomes `"no installs, no deletes."`. That anchor occurs once in each file; check it.
  - Add `SH-11c` to `WHOLE_EXCEPTIONS` with a reason of more than three words.
  - Add `HELD_RUNS["SH-11c"]` with each file's whole bullet as `exact(...)` and `starts("- Do not suggest changes")` after it.
  - Add a safety pin: `area-lead.md`, folded, does not hold "running the project's builds and tests".
- `tests/test_area_lead_adversarial.py` (test-engineer, within this task's rounds): take `SH-11c` out of `UNHELD_NEXT_TO`, and change the comment "The ten rows in WHOLE_EXCEPTIONS" to eleven. The session dispatches `test-engineer` for this before the commit, since the builder's change makes those two lines fail.

**Covers**
- AC-5: `area-lead`'s Bash is for the commands its own file gives and nothing else; `investigate` keeps its sentence; each file's bullet is held by its own pin; the smoke still passes 9 of 9 and the head-to-head still scores `BAR MET`. This task does the text and the pins.

**Verify**
- `python3 -m unittest tests.test_area_lead tests.test_area_lead_adversarial tests.test_area_lead_docs tests.test_security_rules -q` passes on both Pythons.
- `grep -n "builds and tests" agents/investigate.md agents/area-lead.md` prints `agents/investigate.md` only.
- The gate exits 0 on all five lines.

**Builder:** implement, then `test-engineer` for the adversarial file.

### Session step 1: the big sweeps, the smoke and the head-to-head (start here, then go on to Task 4)

Run these only when Tasks 1 to 3 are committed with their adversarial and fix rounds done. Set `M` to a scratch folder outside the repo, as an absolute path.

```bash
REPO=$(git rev-parse --show-toplevel); WORK="$REPO/.git/foundry-run/steadier-runs/work"; BASELINE="$REPO/.git/foundry-run/2026-11-05-per-file-investigation/results/baseline/aggregate-result.json"
git status --short; SHA=$(git rev-parse --short HEAD); echo "$SHA"
git rev-parse HEAD:agents/investigate.md HEAD:agents/area-lead.md HEAD:agents/file-reader.md HEAD:evals-expensive/check_parts.py
P="$M/plugin-$SHA"; rm -rf "$P"; mkdir -p "$P" && git archive HEAD | tar -x -C "$P"; echo "export exit=$?"
(cd "$P" && claude plugin eval . --eval-dir evals-expensive --case nesting-smoke --ablation none --scaffold --trust-plugin --allow-tools Bash --model sonnet --judge-model sonnet --threshold 0 --runs 1 --keep-temp --no-publish --output-dir "$WORK/results/smoke")
(cd "$P" && claude plugin eval . --eval-dir evals-expensive --case investigate-head-to-head --ablation none --scaffold --trust-plugin --allow-tools Bash --model sonnet --judge-model sonnet --threshold 0 --runs 4 --keep-temp --no-publish --output-dir "$WORK/results/h2h")
python3 "$P/evals-expensive/compare.py" --key "$P/evals-expensive/head-to-head-key.json" --new "$WORK/results/h2h/aggregate-result.json" --baseline "$BASELINE"; echo "compare exit=$?"
```

Then, for `L` = `sr-1` to `sr-8`:
```bash
bash "$REPO/.git/foundry-run/area-lead/work/run_loop2.sh" "$L" "$P" "$REPO" "$WORK" "$M" "$P"
LAST=$(ls "$M/loop-$L/parts" | sort -t- -k2 -n | tail -1); grep -n -E '^(To read the rest|Project:|Focus:|Environment:|Instructions:|Areas not read:$|END OF BLOCK$)' "$M/loop-$L/parts/$LAST"; echo "block lines in last part exit=$?"
grep -c 'spend limit' "$WORK/loop/loop-$L.jsonl"; grep -c 'safeguards flagged\|safety classifier' "$WORK/loop/loop-$L.jsonl"
```

What each must show:
- Smoke: 9 of 9 graders.
- Head-to-head: `BAR MET`, exit 0; no run made anything up.
- Each sweep: `block lines in last part exit=1` (no match).
- The proved count is reported as a rate. Every `LOOP FAILED` has its cause named from its failing lines, and every NOTE is recorded.
- A run cut off by the spend limit is void and is run again. A classifier stop gets one rerun as `sr-<n>b`.
- Record everything in `$WORK/measure.md`.

Eight sweeps of 2,800 to 3,500 s each take about seven hours one at a time. Fitting them into three hours means about three at once. The 3.0.0 runs went one at a time, and two of them were voided by the account's spend limit. How many run at once is the session's call.

At the end of the build, `git diff --quiet "$SHA" HEAD -- agents/investigate.md agents/area-lead.md agents/file-reader.md evals-expensive/; echo "sweep text unchanged exit=$?"` must print 0, or the sweeps are not on the final text. If only `check_parts.py` changed, rescore the eight with HEAD's scorer instead of rerunning them.

### Task 4: `devops`'s three lines are one line each, and the two graders read the real shapes

**What to do**
- In `agents/devops.md`, "What to Report Back", put this paragraph straight under the template fence, before "With no running service and no data change, one line instead:":
  > Write each of the three as one line that starts with its label, with no line break or bullets inside it. On the `Rollback:` line, `tried:` or `not tried:` comes once, after the steps. Anything longer goes in the report's body, after the three lines.

  This tightens the draft's wording. The fence and every line the release-readiness tests pin stay as they are.
- `evals/devops-tries-the-rollback-on-a-copy/graders/watch-line.md`: in the pattern, `[Rr]oll back if\b[ \t:]*\w` becomes `[Rr]oll back if\b[ \t:]*[\x60\x22\x27(\[*_\u201c\u2018]*\w`. That takes a backtick, a quote, a bracket, a parenthesis or emphasis marks before the word; "roll back if" with nothing after it still misses.
- `evals/devops-tries-the-rollback-on-a-copy/graders/rollback-tried.md`. This does not use the draft's "the first `tried:` label is the answer". That rule would fail a record-run report that must pass: 22231bc run 3 has no `tried:` label ("The down migration was tried on a copy with the sqlite3 CLI (exit 0)"). It would also fail the pinned "not tried first, a try after it" shape. Keep both of today's branches and make two changes:
  1. `Rollback[*\x60]*:[*\x60]*[ \t]+(?:` becomes `Rollback[*\x60]*:[*\x60]*[ \t]*(?:`, so a label alone on its line goes to the lines-below branch (rel-agents run 1).
  2. Add a third branch first in that alternation, for a label after a sentence end or `;` on the label's own line, with no `not tried` label before it (rel-agents run 2: "I haven't tried either on production. Tried: … (both exit 0)"). The draft tried in memory:
     `(?:(?!\\n)(?![Nn][Oo][Tt][^\w\n]{1,4}[Tt]ried\b).)*?[.!?;][ \t]+[*\x60]*[Tt]ried[*\x60]*:(?![ \t*\x60]*(?:[Nn]o|[Nn]ot|[Nn]ever|[Nn]othing|[Nn]one)\b)(?:(?!\\n)(?!\bexit\b)(?!\b(?:not tried|never (?:ran|run|tried)|didn\x27t run|did not run)\b).)*\bexit(?:s|ed| code| status)?[ =:\x60]*0\b|`

  The pattern must work the same in Python `re` and JavaScript `RegExp`, since the harness runs JavaScript. Weights and the case total (9) stay.
- Expected verdicts on the 28 saved reports in `$WORK/corpus/*devops-tries-the-rollback-on-a-copy*`, all checked in memory:
  - rel-agents runs 1 and 2 change from miss to hit on `rollback-tried`;
  - rel-agents run 2 and agents-3 run 4 change from miss to hit on `watch-line`;
  - no other verdict changes;
  - release-readiness `agents` run 3 and `copy-2` runs 2 and 4 (1-based) stay misses, as they are true misses that tests already pin.

  So the draft's bar "every saved report rescored passes" is wrong. The bar is these verdicts.

**Files**
- `agents/devops.md`: the one paragraph.
- `evals/devops-tries-the-rollback-on-a-copy/graders/rollback-tried.md`, `watch-line.md`.
- `tests/test_release_readiness.py`, in `problems`, holding the contract with no restated prose:
  - the paragraph straight after the report fence holds "one line that starts with its label" and "`tried:` or `not tried:` comes once";
  - one mutation test drops it.
- `tests/test_eval_cases.py`, in `RollbackOnACopyCaseTest`:
  - hits: the rel-agents run 1 block ("Rollback:" alone, then bullets ending "- tried: the up and down SQL on a scratch copy (both exit 0)"), the run 2 line, and run 2's and 22231bc run 4's `Watch:` lines, copied as literals from the corpus;
  - misses: "Rollback:" alone with nothing before `Watch:`; "Rollback: down; not tried: no copy. Tried: nothing (exit 0)"; "Rollback: restore. I haven't tried it. Tried: not tried (exit 0)"; "Watch: x; roll back if \`"; "Watch: x; roll back if **".

**Covers**
- AC-1: `agents/devops.md` says each of the three report lines is one line starting with its label, with `tried:` or `not tried:` once after the steps on the `Rollback:` line; a test holds it.
- AC-2: `rollback-tried` and `watch-line` hit the true reports they missed (rel-agents runs 1 and 2, the 22231bc run 4), keep every verdict a test pins, and on the 28 saved reports change no verdict but those three.

**Verify**
- `python3 -m unittest tests.test_eval_cases tests.test_eval_cases_adversarial tests.test_release_readiness tests.test_release_readiness_adversarial -q` passes on both Pythons.
- A short script prints `rollback-tried` and `watch-line` on each of the 28 corpus traces, in Python and through `node -e`, and shows the verdicts above with the two engines agreeing. Paste its output into the report.
- The gate exits 0 on all five lines.

**Builder:** implement

### Task 5: `debug-polluted-test` `ran-the-check`, sorted and replaced

**What to do**
- Read every `$WORK/corpus/*debug-polluted-test*` trace (22). Sort each by the rubric's substance: before the fix was written, did the run show (a) `test_report_header_uses_dollars` alone passing and (b) only `test_a_currency`'s tests followed by the victim, with the victim failing?
  - `tests.test_c_report` holds only the victim and `tests.test_a_currency` only the polluter, so a run of either module counts as that test alone.
  - From my read of the four rel-debug runs: runs 3 and 4 ran both before the `Write` of `tests/test_a_currency.py`. Run 1 ran the victim alone and a half (`a0 a1 a_currency` and `c`) and a state dump before the write, and ran the pair only after it. Run 1 looks like a real miss; confirm it.
- Where the judge failed a run that did the thing, replace `ran-the-check.md` with exact graders (`regex` on the trace, or `tool_used`) that hold the order "before the first Write or Edit of `test_a_currency.py`". Total weight stays 1, split if there are two.
  - `evals/README.md` doesn't say what `tool_order` does when its `after` call never comes. Use a trace `regex` for order, or settle that from a test before relying on it.
- A run that really missed is a finding: report its corpus file and the commands. Don't widen a grader to hide it.

**Files**
- `evals/debug-polluted-test/graders/`
- `tests/test_eval_cases.py`: each new grader against literal excerpts from the corpus that it must hit and miss, and the case's total if a pin holds one.
- List any `*_adversarial.py` pin that fails for the session to route to `test-engineer`.

**Covers**
- AC-6: Each of `ran-the-check`, `item-a` and `code-first-then-the-break` has been sorted against every saved run. Where the judge was wrong, exact graders replace it, hitting every run that did the thing and missing every run that didn't; where a run really missed, the miss is reported with its trace. Four fresh runs of each case follow. This task does `ran-the-check`.

**Verify**
- The report holds the sorting table: corpus file, did or didn't, and the commands that decide it.
- A script shows each new grader hitting every "did" and missing every "didn't".
- `python3 -m unittest tests.test_eval_cases tests.test_debug_pollution_procedure -q` passes on both Pythons.
- The gate exits 0 on all five lines.

**Builder:** implement

### Task 6: `debug-decisions` `item-a`, sorted and replaced

**What to do**
- The same method over `$WORK/corpus/*debug-decisions*` (22 traces), reading item (a) of each final message.
- rel-debug run 3, failed by the judge, says "I don't try a fourth", offers "two or three ways forward" and recommends one, so the judge was wrong there.
- Exact graders, `regex` with `target: last_message`, read only item (a), the text from the (a) marker to the (b) marker, and hold:
  - no fourth fix tried;
  - the question taken to the user with options;
  - a recommendation.

  Total weight stays 1. `item-b` to `item-e` are untouched.
- A run that really missed is reported, not hidden.

**Files**
- `evals/debug-decisions/graders/item-a.md`, replaced by the new files.
- `tests/test_eval_cases.py`: hits and misses as literals.

**Covers**
- AC-6: as in Task 5. This task does `item-a`.

**Verify**
- As in Task 5, over 22 traces.
- `python3 -m unittest tests.test_eval_cases -q` passes on both Pythons.
- The gate exits 0 on all five lines.

**Builder:** implement

### Task 7: `architect-splits-a-breaking-change` `code-first-then-the-break`, sorted and replaced

**What to do**
- The same method over `$WORK/corpus/*architect-splits-a-breaking-change*` (16 traces). Each report is the text after `The report follows:`.
- The 22231bc failure, recorded in `docs/plans/2026-11-26-open-items.md` under "Still open", was a rubric misread: an additive migration plus new code in release 1, and the drop in a later release. Check rel-agents run 3 the same way.
- Exact graders, `regex` on the trace after `The report follows:`, hold:
  - release 1 adds the new column beside `email` or ships code that reads both;
  - a later release removes or renames `email`;
  - the plan says which goes first.

  Total weight stays 2, and the case total stays 4. `two-releases` stays.

**Files**
- `evals/architect-splits-a-breaking-change/graders/`
- `tests/test_eval_cases.py`: replace `test_the_judged_grader_reads_the_trace_with_the_trace_preamble_at_weight_2` with the new graders' hits and misses. Keep the total at line 336 at 4.

**Covers**
- AC-6: as in Task 5. This task does `code-first-then-the-break`.

**Verify**
- As in Task 5, over 16 traces.
- `python3 -m unittest tests.test_eval_cases tests.test_eval_cases_adversarial -q` passes on both Pythons. A failing pin in the adversarial file (`BREAKING`) goes to `test-engineer`.
- The gate exits 0 on all five lines.

**Builder:** implement

Fix E is three tasks, three dispatches, one after another. Each case needs its own hand sort and may stop on a finding, and all three edit `tests/test_eval_cases.py`. They don't touch agent text, so they run while the sweeps do.

### Session step 2: the measurement round for A and E, which is also the record run

CONTRIBUTING asks for the `agents` cases, and the cases of every skill the release changes, before a release. That is wider than the draft's "the cases each task touches", and these two runs cover it:

```bash
SHA2=$(git rev-parse --short HEAD); P2="$M/plugin-$SHA2"; rm -rf "$P2"; mkdir -p "$P2" && git archive HEAD | tar -x -C "$P2"
(cd "$P2" && claude plugin eval . --tag agents --ablation none --scaffold --trust-plugin --allow-tools Bash Write Edit --judge-model sonnet --threshold 0.8 --runs 4 -j 4 --keep-temp --no-publish --output-dir "$WORK/results/agents")
(cd "$P2" && claude plugin eval . --tag debug --ablation none --scaffold --trust-plugin --allow-tools Bash Write Edit --judge-model sonnet --threshold 0.8 --runs 4 -j 4 --keep-temp --no-publish --output-dir "$WORK/results/debug")
python3 evals/scorecard.py --commit "$SHA2" "$WORK/results/agents" "$WORK/results/debug"
```

Copy the new traces into `$WORK/corpus` straight away, using Session step 0's script with the results folder.

What it must show:
- The three `devops` cases: every grader 4 of 4.
- `debug-polluted-test`, `debug-decisions` and `architect-splits-a-breaking-change`: each replaced grader's verdict on all four runs matches a hand read of the trace.
- Every other case is recorded as it comes.

A miss goes to the owner with the numbers. Commit the scorecard rows.

### Task 8: the docs

**What to do**
- `CHANGELOG.md`: a new `## [Unreleased]` entry above `## [3.0.0]`. It covers:
  - the devops one-line rule and the two graders, with the saved-report numbers;
  - the last-part rule and the scorer's matching check;
  - the second-reader allowance;
  - the lead's Bash sentence;
  - the three graders sorted, replaced or reported;
  - Session steps 1 and 2's numbers.

  It may say the 3.0.0 build log misdescribed two devops runs. Both reports said tried, and run 2 had a `Watch:` line. The `[3.0.0]` entry is not edited.
- `docs/design.md` §5: a short "### After 3.0.0 (3.0.1)" note under its As built, covering B, C and D. It also closes the parked item that `area-lead` "keeps 'Bash is for reading, and for running the project's builds and tests'".
- `evals/README.md`: a results line for 3.0.1 beside the 3.0.0 ones (near lines 365 and 420). If a grader is described there, the row for each replaced one.
- `README.md` line 284 ("because an agent that can't run the tests can only guess"): add a clause that `area-lead` doesn't run them, only if the sentence no longer reads true.

**Files**
- `CHANGELOG.md`, `docs/design.md`, `evals/README.md`, and `README.md` only if needed.

**Covers**
- AC-7: The CHANGELOG `[Unreleased]` entry, §5's As built and `evals/README.md` say what changed and what the runs showed.

**Verify**
- `python3 -m unittest tests.test_area_lead_docs tests.test_docs_sweep_in_parts tests.test_docs_as_built_and_results -q` passes on both Pythons.
- The gate exits 0 on all five lines. A failing `*_pin_mutations.py` or `*_adversarial.py` test goes to `test-engineer` within this task's rounds.

**Builder:** docs

### Session step 3: the release

Run `the-foundry:ship` with one ask listing every step:
- `plugin.json` `version` becomes `3.0.1`;
- `[Unreleased]` becomes `## [3.0.1] — <date>`;
- tag `v3.0.1`;
- `dist` is built with CONTRIBUTING's block and checked with its two validates;
- the owner pushes.

The ask names the one versioning question (Risks, item 1).

## 3. Data / Schema Changes

None. No database or migration. The new work-dir folders (`corpus/`, `old-loops/`) are untracked.

## 4. Risks and Coupling

1. **Patch or minor, for the owner at the release ask.** CONTRIBUTING's patch is "wording fixes that don't change behavior". Task 3 removes the lead's leave to run builds and tests, which is a narrowing of behaviour no lead was meant to use. My call is a patch, as the owner named 3.0.1. Ask, don't stop.
2. **Who reads the changed lines.**
   - `investigate.md` "The Block" is read by `tests/test_investigate_parts.py` (the table, `TOKENS`, `template_lines`, the `code()` extracts), `tests/test_area_commands.py` and `tests/test_docs_sweep_in_parts.py`. `docs/design.md:841` and `docs/orchestrator.md:43` quote the old wording.
   - The scorer's last-part check is pinned at `tests/test_check_parts.py:652` and `:783`, and in `tests/test_investigate_parts.py:1018`.
   - `SH-11c` is in `tests/test_area_lead.py` and `tests/test_area_lead_adversarial.py:465` and `:534`.
   - The two devops graders are pinned in `tests/test_eval_cases.py:1059-1210`, `tests/test_eval_cases_adversarial.py:811-870` and `tests/test_release_readiness_adversarial.py:280-410`. `devops-holds-a-breaking-migration`'s `rollback-line` is a separate grader and is untouched.
   - The architect case is pinned at `tests/test_eval_cases.py:336` and `:1585`.
3. **The evidence is in tmp.** Session step 0 must run before anything else. Without it, Tasks 2, 4 and 5 to 7 have nothing to check against.
4. **Sweeps on a stale tree.** A fix round on Tasks 1 to 3 after Session step 1 starts makes those runs void. Hence the `git diff --quiet` check at the end.
5. **Docs lines needed:** CHANGELOG `[Unreleased]` (all), §5 As built note (B, C, D), `evals/README.md` (A, E, the runs). Never touched: a numbered CHANGELOG entry, and `evals/SCORECARD.md` except through `scorecard.py`.
6. **Covered ids:** AC-1 to AC-7, each by at least one task. None dropped.

Security:
- **Transcript text reaching the scorer's parser.** Task 2 reads a model-written counts line. A crafted count could win an allowance it shouldn't, or crash the scorer. Task 2 guards it with a per-part count, bytes-exact path matching, no allowance on anything unparsable, and tests that it never raises.
- **What a lead may run.** Task 3 narrows the lead's Bash to the commands its file gives, so a repo file or a reader's report can't get it to run a build or a test. The `HELD_RUNS` pin and the negative pin guard the narrowing.
- **A report's text reaching a regex.** The new grader branches in Task 4 read model text. A pattern too loose would score a false "tried". Task 4 keeps every existing miss pin and adds the new ones.

## 5. Testing Strategy

- Unit tests:
  - Tasks 1, 3 and 4 add contract and safety pins on the agent text (their Files lines).
  - Task 2 tests the scorer on synthetic transcripts.
  - Tasks 4 to 7 test the graders against literals from the saved corpus.
- Adversarial round (`test-engineer`):
  - Task 1: a block line put under a last part in a made-up report, and the Coverage line dropped from the last part.
  - Task 2: counts that lie (2 for one file read three times), a count in the wrong part, a non-numeric count, and a path with a non-ASCII name.
  - Task 3: a sentence put inside or beside either Bash bullet, and "builds and tests" put back in the lead.
  - Task 4: denials worded the other way after a sentence end, a `Tried:` label after `Watch:`, and curly quotes and emphasis after "roll back if".
  - Tasks 5 to 7: a wrong report that holds each new grader's words, and a right one worded differently.
- Real runs: Session steps 1 and 2.

Per id:
- AC-1: Task 4; test
- AC-2: Task 4; test and command: Task 4's corpus script, and Session step 2's three devops cases
- AC-3: Tasks 1 and 2; test and command: Session step 1's `run_loop2.sh` runs and the last-part `grep`
- AC-4: Task 2; test and command: Task 2's rescoring of the saved sweeps
- AC-5: Task 3; test and command: Session step 1's smoke and `compare.py`
- AC-6: Tasks 5, 6 and 7; test and command: each task's corpus script, and Session step 2
- AC-7: Task 8; by hand: the docs say what the runs showed, which no test can judge

## 6. Out of Scope

- The scorer's "readers: … once each" summary on a run with allowed second readers. It is parked from 3.0.0 and stays so.
- The inert git-wrapper block in `area-lead.md`.
- The vendored-route paragraph and the other 3.0.0 parked items.
- Any judged grader other than the three named, and `victim-untouched`'s earlier misses.
- The probe branch, and moving the sweep-in-parts text.
- `~/.claude/CLAUDE.md` (nothing in it changes for a patch).

## Build log

Gate: the five lines in the header (expect exit 0 on each; `Ran 2918` at the start)
Branch: `fix/steadier-runs`, from 2951dbd
Work dir: `.git/foundry-run/steadier-runs/work/`

### Progress
- Session step 0: done (traces and sweep fixtures copied to the work dir; `missing: 10`)
- Tasks 1 to 3: complete (from 4077be7; gate exit 0 on all five, `Ran 2984`; adversarial: 57 tests, 1 bug fixed in round 1)
- Session step 1: started on the export of a51daaa (sweeps `sr-1` to `sr-3`, the smoke, the head-to-head)
- Task 4: complete (from a51daaa; gate exit 0 on all five, `Ran 3020`; adversarial: 33 tests, 5 faults fixed in round 1, 1 ruled a limit)
- Task 5: complete (from c63d277; gate exit 0 on all five, `Ran 3060`; adversarial: 31 tests, no fix round, limits pinned)
- Tasks 6 and 7: complete (from 23fbe87; gate exit 0 on all five, `Ran 3113`; adversarial: 39 tests and a second pass, 2 faults fixed in rounds 1 and 2)
- Session step 2: done on the export of 07b1043 (15 of 19 cases at 4 of 4; every reworked grader 4 of 4; an independent read confirmed 16 of 16 of their verdicts; scorecard rows added)
- Task 9 (added): complete (from 07b1043; gate exit 0 on all five, `Ran 3129`; adversarial: 13 tests, 1 fault fixed in round 1)

### Decisions made during the build
- Ruling (plan): the architect's rewording of Fix B stands (Task 1). Why: the draft's sentence forbade the Coverage line every part must carry, and "first line" is false under `NOT A PER-FILE READ`. If wrong: one sentence of `investigate.md` to reword.
- Ruling (plan): `rollback-tried` keeps both of today's branches and gains two small edits, not the draft's "first `tried:` label" rule (Task 4). Why: that rule fails a saved report that has to hit, and a shape a test pins. If wrong: a true report is still missed, and the three devops cases show it in Session step 2.
- Ruling (plan): the bar for the saved devops reports is the verdict list in Task 4, not "every report hits". Why: three of the 28 are true misses that tests already pin.
- Ruling (plan): the second-reader allowance is counted per part, not summed across parts (Task 2). Why: stricter, and the same answer on both saved runs. If wrong: a right run fails on a count the top level put in another part, and the sweeps show it.
- Ruling (plan): the lead's Bash sentence is the architect's wording (Task 3), which names the plumbing the lead's own commands use.
- Ruling (plan): the head-to-head and the `agents` and `debug` record runs are part of the measurement round, as CONTRIBUTING asks.
- Ruling (plan): the big sweeps run three at a time. Why: one at a time is about seven hours. If wrong: a spend-limit stop voids a run, which is then run again.
- Ruling (Tasks 1 to 3): built as one batch, with one adversarial round and one commit. Why: each is small and they touch separate files, and the sweeps can't start until all three are final. If wrong: a fault is harder to pin to one task; the report keeps a section for each.
- Ruling (Tasks 1 to 3): the scorer's failure on a count thousands of digits long (`CAN'T CHECK: internal error` on Python 3.11 and later) is a real bug, fixed in round 1 with a helper that treats such a number as a line it can't read.
- Ruling (Tasks 1 to 3): the seven limits the tester pinned as `test_today_...` stay limits (see Parked). Why: no brief promises against them, and the two shapes real runs produced (a plain `Project:` line, the whole block) are caught. The session reads each real sweep's whole last part by hand as well.
- Ruling (Task 4): the brief's patterns were used as written and gave the verdict list on the 28 saved reports. The adversarial round then found five real faults, fixed in round 1: a denial word after `tried` scored a try through the older branch; the new branch read past the report's closing quote; an escaped double quote after "roll back if" was missed; the test helper read `\w` as Unicode where the harness's JavaScript reads ASCII (the helper now compiles with `re.ASCII`); and a run of backticks after the label took quadratic time.
- Ruling (Task 4): the older same-line branch of `rollback-tried` still reads past the report's closing quote. Why a limit: it was there before this change, and what follows a report on a trace line is the harness's own fields. Parked.
- Ruling (Task 4): the pin on the new `devops` paragraph notices "before the steps" but doesn't hold "after the steps" as a phrase. Parked with the other phrase-pin limits.
- Ruling (Task 5): all 22 saved `debug-polluted-test` runs did the check; the judge failed 7 of them wrongly and none was a real miss. The session read the disputed run (the record run's run 1) itself: the victim alone and the polluter-then-victim pair both ran before the fix was written. The plan's note that run 1 "looks like a real miss" was wrong.
- Ruling (Task 5): `ran-the-check` is now one exact pattern on the trace at the same weight (weights are whole numbers, so it isn't split). It hits 22 of 22 saved runs in both engines and misses all 87 variants with the commands moved after the fix or a name removed. If wrong: a right run in a shape the pattern doesn't read is scored a miss; a miss on this grader in a real run gets a hand read before it counts.
- Ruling (Task 5): the right-run shapes that miss, the command-text false hits and two slow hostile inputs are limits (see Parked). Why: none appears in the 22 saved runs, and the harness's engine stays under a second on the hostile inputs.
- Ruling (Tasks 6 and 7): built as one batch, the same kind of work on two cases. Both sorts came out like Task 5's: every saved run did the thing (22 of 22 and 16 of 16), and the judge had failed 1 and 2 of them wrongly.
- Ruling (Tasks 6 and 7): where the saved right runs can't be held honestly by an exact pattern, the grader stays judged and its rubric is corrected to name what the judge misread. Why: Task 5 showed an exact grader on text has limits both ways, and these two read prose. `item-a` went exact (all 22 right replies follow the debug skill's own sentence); `code-first-then-the-break` stays judged with a corrected rubric (the 16 right plans label the same substance too many ways). If wrong: for `item-a`, a right reply in other words is scored a miss, and gets a hand read before it counts; for the rubric, the judge still misreads, which the fresh runs show.
- Ruling (Tasks 6 and 7): the rubric's "FAIL only for" list missed a drop of `email` in a second migration of the first release; fixed in round 1. `item-a` was widened in round 1 for three right shapes the tester judged moderately likely ("I'll stop", the user as "you", "suggest") and its guard for a denied recommendation; round 2 closed a false hit the widening made easier to reach ("I'll stop, and try a fourth fix").
- Ruling (Session step 2): the bar "the three `devops` cases, every grader 4 of 4" was missed on `devops-stops-before-irreversible` (3 of 4). An independent read found it a real miss by the agent, a summary sentence above its `Status:` line, on graders this batch didn't touch. It goes to the owner with the numbers; no second round.
- Ruling (Task 9, added during the build): the record run found one more grader that misreads right plans, `two-releases` (it wanted "two release" side by side and rejected "Release 1.4.1"). Fixed here and checked against the 20 saved plans, with no new real run. Why now: it is the same kind of fault this batch is for, in a case the batch already touched. If wrong: the grader goes back to its 3.0.0 text, one file.
- Ruling (Task 9): the labelled branch never takes 1.4.0, the fixture's live version, as a release label. Why: a one-release plan whose rollback line says "redeploy release 1.4.0" scored. No saved plan depends on it.
- For the owner at the release ask: patch or minor (Risks, item 1).

### Parked
- Tasks 1 to 3: the scorer checks only the first non-blank line under a last part's `SWEEP IN PARTS: 0 areas not read`. An `END OF BLOCK` further down, or an indented, bulleted, lowercase or backticked block line, goes unseen. Parked because no saved run shows those shapes.
- Tasks 1 to 3: a last part that drops its Coverage `Areas not read: 0 areas, 0 files; ...` line is still proved; the text asks for the line and the scorer doesn't. All 16 saved last parts carry it.
- Tasks 1 to 3: a sentence added after the new last-part sentence, or a paragraph in the lead outside "Your Files" that brings the tests back, fails no pin. The pins hold a phrase, not the paragraph.
- Tasks 1 to 3: with two counts lines in one part the first is used; a file held by two parts is judged by the first; a tracked path that isn't UTF-8 gets no allowance.
- Task 4: `rollback-tried`'s older branch reads past the closing quote of the report's JSON string; wording that denies a try without a denial word ("I did not run it; the script would exit 0") still scores through it; `exit 0.5` reads as exit 0; with no `Watch:` line, a `Tried` label anywhere below a bare `Rollback:` scores.
- Task 4: a lone `_` after "roll back if" hits `watch-line`. A report holding a literal U+2028 can score differently in Python and JavaScript (16 of 3,000 fuzzed shapes, all with that character).
- Task 4: three rewordings of the new `devops` paragraph fail no pin ("may span several lines"; the "Anything longer" sentence dropped; "comes once or more, anywhere").
- Task 5: `ran-the-check` reads command text, not results. Right-run shapes it misses, likeliest first: the file-path form (`-m unittest tests/test_c_report.py`); a Bash call whose `description` comes before `command`; `-k`; a function body using `$1`; quoted module names; `while read` or `xargs`; a Python script or `pytest`.
- Task 5: command text inside a Bash call counts even as a comment, an `echo` or a printed here-document. Only a Write or Edit with `file_path` first (or after `replace_all`) closes the window; `sed -i`, `cat >`, MultiEdit and a Write with `content` first don't.
- Task 5: one command with 66 uncalled function definitions takes about 4 s in Python (0.45 s in node), and a 2.7 MB trace with no Write about 2.5 s (0.8 s in node).
- Tasks 6 and 7: `item-a` reads words, not meaning. An item (a) with no `b.` line after it is read to the end of the message; a quoted or conditional refusal scores; "I stop," in another sense scores; a denial in other words ("wouldn't recommend", "I hesitate to suggest") still counts as a recommendation; "there is no option here" counts as options; "and add one more line" reads as a fourth fix. Right replies that miss: a stop said as "no more patching" or "three strikes", "I don't keep patching", the markers `a:`, `1.` and `- a.`.
- Tasks 6 and 7: `item-a` is quadratic in the number of `a.` lines (0.41 s in node at 55 KB, 6 s at 220 KB).
- Tasks 6 and 7: the corrected rubric doesn't check a stated order against the releases, and a one-release plan with an unscheduled later cleanup is in neither its PASS nor its FAIL list.
- Session step 2: `rollback-tried` is looser than the agent's template (two fresh reports say "tried: the up and down SQL on a scratch copy (both exit 0)" with the command left to the body), and `adds-only` takes a label in bold. One fresh `devops` report in four broke the new one-line rule on `Data change:`.
- Task 9: `two-releases` hits "Do not split this into two releases" and "We can't afford two releases" (the judged grader beside it holds those). Right plans that miss, likeliest first: "2 releases", a second label without the word "release" ("Release 1.4.1, then 1.5.0"), word labels, "two deploys". "Release 1.5" and "Release 1.5.0" count as two labels.
