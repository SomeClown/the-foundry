# Behavior tests for the skills (and some agents)

> "Trust, but verify."
> — Russian proverb, borrowed by a US president, overused by everyone since

The tests in `tests/` check run-plan's brief command, debug's procedure, and that the repo agrees
with itself. They can't check whether a skill makes a model *behave* the way
it should: ask numbered questions with a recommendation first, hold the gate
when the user says "sounds great, build it", measure a flaky test before
touching it, never push before the ask. That's what these cases are for.

Each case is a situation that once caught something real while a skill was
being built or tested. They run with Claude Code's own eval harness,
`claude plugin eval .`, which starts a fresh headless session per run with only
this plugin loaded, builds any fixture repo the case needs, and grades the
result.

## Running them

From the repo root. Run the cases for the skill you changed, before releasing
it.

```bash
claude plugin eval . --tag ship --ablation none --scaffold --trust-plugin --allow-tools Bash Write Edit \
  --judge-model sonnet --threshold 0.8 --no-publish
```

The `debug` and `run-plan` cases run their skill to the end, which includes
the retro step. The harness gives each case its own home folder, so the entry
lands in that home's `.foundry/retro.md` and never in yours (a
`FOUNDRY_RETRO_FILE` set in your shell doesn't reach the session). `--keep-temp`
keeps that folder if you want to read what the session wrote.

- `--tag brainstorm | run-plan | debug | ship | agents` picks a skill's cases;
  `--case 'debug-*'` works too.
- `--ablation none` skips the no-plugin baseline arm the harness otherwise
  adds whenever it finds the plugin at the target path. These cases tell the
  session to load the plugin's own skills, which a session without the plugin
  can't do, so that arm only adds cost.
- `--scaffold` lets a case run its `scaffold.sh` to build its fixture repo.
  Those scripts are ours; read one before you trust it.
- `--allow-tools Bash Write Edit` is needed by the cases that work in a repo
  (debugging a planted bug, a scratch release). Each case's `allowed_tools`
  still narrows what it gets.
- `--runs N` overrides each case's run count (2 by default here). Model
  behavior varies between runs, so a case that passes once and fails once is
  telling you something; read both before deciding which.
- `--threshold 0.8` lets a case lose one grader in five or so without
  failing. The decision-point cases have a grader per situation, and the
  judge still gets one wrong now and then; a real regression usually breaks
  several, or trips one of the exact checks below. The default, 1.0, fails a
  case on any miss.
- `--max-cost-usd 10` is a ceiling checked before a run starts. It doesn't
  stop a run in flight, and a run that breaches it skips the paid graders
  (`keep-report` among them, in the expensive cases below). `-j 4` runs four
  at once.
- `--judge-model sonnet` matters. With the default judge (haiku), the first
  trial failed correct answers on long, multi-part replies, sometimes by a
  unanimous vote. With sonnet the same answers pass, for about 10 to 20 cents
  of judging per run on the long cases.

Results land in `evals/results/<timestamp>/` (git-ignored): a table on
stdout, `aggregate-result.json`, and `report.html` with each run's prompt,
grader verdicts, and the evidence the judge saw.

**Cost.** A run is a full session on your own account. Measured on
2026-10-23: the whole library, one run per case with the sonnet judge, cost
$4.43 and took about four minutes at `-j 4`. Each case runs twice by default,
so a full run is about $9; a single skill's cases are $1 to $3.

## What's in it

| Tag | Cases | What they hold the skill to |
|---|---|---|
| `brainstorm` | small request, opening, numbered questions, phone batch, gate holds, writes design | Just does a fully specified change; one open question to start; numbered questions with the recommendation first; every question at once when the user's on a phone; nothing built on a passing "sounds great"; the design as a new numbered section of `docs/design.md` with anti-goals and the assistant's own calls marked |
| `run-plan` | decisions, resume | The fix-round cap, one writer at a time, rulings instead of stalls, production off limits, a finding `qa` only read checked (by running a real session if that's what settles it) before a fix is built on it; picking up after compaction without redoing finished tasks |
| `debug` | polluted test, wrong total, flaky pressure, user's fix is right, decisions, production report | Root cause before any fix, a failing test first, the fix in the right place (the polluting test, the parser, the test that raced), measuring before bumping a sleep, a polluter proven (the `ran-the-check` grader on debug-polluted-test) before it is named, agreeing when the user's fix is the right one, never running production commands, and handing over read-only ones, one per block |
| `ship` | asks before pushing, decisions, CI pending in the app | Preflight catches an unbumped version; the repo's own way of releasing; one ask before any push or tag; a bare "Done" isn't approval; the stuck-check re-run; waiting for the tag's build; handing the merge back when the PR monitor can't say CI passed |
| `agents` | qa spec check, architect plan format, implement test-first | qa's spec-check mode catches a floor that should be a ceiling, an unrequested database dependency, missing tests, and a report that overclaims; the architect's plan has its header block, `### Task N:` headings that run-plan's own brief command can split (checked by running it), exact Verify commands, and repo-relative paths; implement runs the failing test before it edits the code |

**Why only the hard lines are exact checks.** "Never ran `git push`", "never
ran `ssh`", and "wrote no code before the design was approved" are
`tool_used` and `regex` graders over the run's trace, so no judge can wave
them through. Everything about tone and judgment (numbered questions, a
recommendation first, one ask) is a rubric, because that's the only way to
grade it.

## Reading a failure

A failed case is a question, not a verdict. Open `report.html`, read what the
model actually did and what the judge saw, and decide which of three it is:

1. **The skill regressed** (it used to pass, an edit changed the behavior):
   fix the skill.
2. **The case is wrong** (the rubric asks for something the skill
   deliberately doesn't do, or the fixture is broken): fix the case, and say
   why in the commit.
3. **The judge got it wrong** (the evidence shows a pass): rerun with
   `--judge-model sonnet`, and tighten the rubric's wording if it keeps
   happening.

## The expensive cases: `evals-expensive/`

`evals-expensive/` holds the paid head-to-head for per-file investigation: a
generated test repo of 191 files with planted facts (48 of them), and a
comparison of today's `investigate` against 1.7.6's single-agent one. It sits
outside `evals/` so a routine run, which loads this folder, never starts it
by accident: one full sweep starts about 190 readers, and it runs only with
`--eval-dir evals-expensive`. `nesting-smoke` is the cheap check beside it,
that an agent can start an agent that starts an agent. The cases for a repo
read in parts, and the scripts that measure and score them, are under "A big
repo read in parts" below.

The exact commands (`WORK` is a scratch folder, as an absolute path, since the baseline command runs inside a `cd`; run them one after the other).
The first run of the new version:

```bash
git rev-parse HEAD:agents/investigate.md HEAD:agents/file-reader.md
claude plugin eval . --eval-dir evals-expensive --case investigate-head-to-head --ablation none --scaffold --trust-plugin --allow-tools Bash --model sonnet --judge-model sonnet --threshold 0 --runs 1 --no-publish --output-dir "$WORK/results/new-first"
python3 evals-expensive/compare.py --key evals-expensive/head-to-head-key.json --summary "$WORK/results/new-first/aggregate-result.json"
```

Then the baseline, built from the v1.7.6 tag, and the rest of the new arm:

```bash
BASE="${TMPDIR:-/tmp}/foundry-baseline-1.7.6"; rm -rf "$BASE"; mkdir -p "$BASE"
git archive v1.7.6 | tar -x -C "$BASE"
cp -R evals-expensive "$BASE/"
grep '"version"' "$BASE/.claude-plugin/plugin.json"; ls "$BASE/agents" | wc -l

(cd "$BASE" && claude plugin eval . --eval-dir evals-expensive --case investigate-head-to-head --ablation none --scaffold --trust-plugin --allow-tools Bash --model sonnet --judge-model sonnet --threshold 0 --runs 3 --no-publish --output-dir "$WORK/results/baseline")

claude plugin eval . --eval-dir evals-expensive --case investigate-head-to-head --ablation none --scaffold --trust-plugin --allow-tools Bash --model sonnet --judge-model sonnet --threshold 0 --runs 2 --no-publish --output-dir "$WORK/results/new-rest"

python3 evals-expensive/compare.py --key evals-expensive/head-to-head-key.json --new "$WORK/results/new-first/aggregate-result.json" "$WORK/results/new-rest/aggregate-result.json" --baseline "$WORK/results/baseline/aggregate-result.json"; echo "compare exit=$?"
```

The baseline should print `"version": "1.7.6"` and `9` agents.
The measured runs added `--max-cost-usd 25` to each of the three `claude
plugin eval .` commands. That ceiling is checked only before a run starts, so
it can't stop one in flight, and a run that breaches it skips the paid graders,
`keep-report` among them, so `compare.py` can't score it. The case's
`timeout_seconds: 3600` is what bounds a run.

**What it cost.** Measured on 2026-11-05, with the readers on Haiku (the
shipped setup) on the final 2.0.0 definition, a run took about $2.31 and 708
seconds on the 191-file test repo (the run before the checklist change cost
$2.62), against about $0.47 and 109 seconds for 1.7.6. The same sweep with every
reader on Sonnet, which is what led to the switch, cost $5.57 a run.

**How `compare.py` scores.** The harness's `aggregate-result.json` holds each
run's report, which `compare.py` reads and checks against
`head-to-head-key.json`. It counts, per run: facts found (of 48), facts missed,
and items made up (a route, `fxctl` command or ticket reference that isn't
real, or a decoy listed as live). A decoy the report marks dead, on its own
line, the next line, a parent bullet, a colon lead-in, a bold run-in label
ending in `.`, `!` or `?`, or the nearest heading or bold label, isn't counted as
made up. The bar is on the means across each arm's runs: found at least 90% of
the 48, missed at most half the baseline's, and made up no more than the
baseline's. Exit 0 prints `BAR MET`, exit 1 prints `BAR MISSED`, and exit 2
prints `CAN'T SCORE` with the reason (a missing report, too few runs, an
unreadable key); a crash while scoring is also exit 2, never 1. `--summary`
scores one result on its own and exits 0 when the run is scoreable, otherwise
2 with `CAN'T SCORE`.

**Why the `llm` grader.** The `keep-report` grader exists to store the
report, as its `evidence`, so `compare.py` has something to score. Its
verdict only checks that the reply looks like a report. The fact graders
(`fact-*`) apply the same found rule as `compare.py`.

### A big repo read in parts

`investigate` reads a repo with more than 450 tracked files to read, not
counting folders skipped whole such as vendored code, in parts (design §4),
and two kinds of case sit in `evals-expensive/` for it.

**`big-sweep-in-parts`** is the loop. Its scaffold generates a test repo of
990 tracked files (950 after the one folder it skips whole, 945 readable):
a flat `rules/` folder of 610 files that no subfolder can divide, files at
the root, a vendored folder, a few untracked files, and 33 planted facts
spread so every part holds some, the last included. The prompt plays the
session: it dispatches `investigate` with an onboarding brief that carries the
head-to-head's three requests (full route paths one to a line, commands as
`twctl <name>`, references quoted word for word), saves each
report to `parts/part-<n>.md`, sends back `CONTINUE SWEEP` while a report says
areas are unread, and asks the user nothing. It has a 3600-second timeout,
which is as high as the harness allows (it refuses a `timeout_seconds` over
3600). Its scaffold stops with exit 1 in a folder that isn't empty, and in an
empty folder inside a repo that has commits, so run it in an empty folder
outside any repo. An empty folder under an empty repo, which is what the
harness's workspace is, builds.

**`reply-size-150`, `-230`, `-320`, `-400`, `-450` and `-full`** are for
measuring how big a report can be and still reach the session whole, on the
same repo cut to that many files. Not all of them ran. In live sessions,
150, 230, 320, 450 and the full repo ran with the plain brief, before the
fixture grew to its present size, and 320 and the full repo ran again with
the full-path brief. In the harness, 320 and the full repo ran with the full-path
brief. `reply-size-400` never ran. They ask for a last line of `TAIL-MARK-6620` and say the user
approved the count, which was right for the definition they were written
against. They're kept as the record of how the part size was set, and they
aren't a check to re-run on today's definition.

Three scripts sit beside them. All run by hand, stay local and use no network;
none starts a model session.

- `sync_big_sweep.py` writes `big-sweep-key.json` and the cases' generated
  files from the scaffold, so they can't drift from the fixture. Run it after
  any change to the scaffold. `--check` writes nothing: it names the files
  that differ and exits 1, or exits 0 when none does.
- `measure_reply.py` takes `--transcript FILE --marker M` (a stream-json
  transcript from `claude -p`) or `--harness aggregate-result.json --marker M`.
  For each agent result it prints the bytes and whether it kept its last line:
  a result is whole only when the marker is its last non-blank line, so a
  marker in the middle of a cut-off report doesn't count. For a preview it
  reads the saved file behind it. Exit 0 when it parsed something, 2 with
  `CAN'T MEASURE:` when it didn't.
- `check_parts.py --key KEY --repo FIXTURE_DIR --parts DIR [--min-parts N]
  [--part-size N] [--transcript FILE]` scores the saved parts. From the parts
  it establishes that every tracked file (listed as the agent lists them, a
  line break in a path as `\001`) outside the folder skipped whole is in
  exactly one area; that the parts say unread and failed are 0 and their
  skipped and read numbers add up to the key's; that every area line rebuilds
  to its count and no area holds more than 165 files; that each block is the
  one before it minus the areas just read, with the Coverage lines, the block
  and the last lines in the right places; that every planted fact is found in
  the part that read its file; that no decoy appears; and, with
  `--part-size`, that no part holds more than that many files. With
  `--transcript` (the run's own `claude -p` transcript) it also checks that
  each readable file had one reader started and completed, that each later
  `investigate` brief is `CONTINUE SWEEP` plus the previous part's block, and
  that each part file is the report the agent returned. Without `--transcript`
  the summary says `readers: not checked`, and the read numbers are the parts'
  own. Two leads running at once, and a later part that names an untracked
  path, are notes, not failures. Exit 0 prints `LOOP PROVED`, exit 1 prints
  `LOOP FAILED` with a line for each failure, and exit 2 prints `CAN'T CHECK:`
  with the reason.

**How the part size was set.** Measured on 2026-11-23 in live headless
sessions (`investigate` on Sonnet, readers on Haiku). With the plain brief, a
report was 11.0KB for 150 files (425 seconds). With the brief asking for full
route paths, it was 19.6KB for 320 files (1,064 seconds) and 27.3KB for the
whole 645-file repo as it was then (1,840 seconds). Each was handed back
whole in the agent's result. In the harness, `reply-size-320` took 866 seconds
and cost $3.39, and `reply-size-full` took 1,157 seconds and cost $6.07; both
came back whole too. Previews start somewhere between 36KB and 54KB. The
450-file part the owner chose wasn't measured at 450 files; the part reports
of the loop runs are the nearest measurement. They ran 7.6KB to 29.1KB, the
largest for 340 files, and none came back as a preview. A full 450-file part
was 15.9KB (loop run 10), but a part of dense files can still land where
previews start. A part that does arrive as a preview is read from its saved
file, like any report. The commands, from the repo root (`WORK` and `M` are scratch
folders, as absolute paths; `N` is one of the sizes):

```bash
REPO=$(git rev-parse --show-toplevel)
mkdir -p "$WORK/measure"; D="$M/live-$N"; rm -rf "$D"; mkdir -p "$D" && (cd "$D" && bash "$REPO/evals-expensive/reply-size-$N/scaffold.sh" && claude -p "$(awk 'n>=2; /^---$/{n++}' "$REPO/evals-expensive/reply-size-$N/prompt.md")" --plugin-dir "$REPO" --setting-sources project --model sonnet --allowedTools Agent,Read,Glob,Grep,Bash --output-format stream-json --verbose > "$WORK/measure/live-$N.jsonl"); echo "live $N exit=$?"
python3 "$REPO/evals-expensive/measure_reply.py" --transcript "$WORK/measure/live-$N.jsonl" --marker TAIL-MARK-6620

claude plugin eval . --eval-dir evals-expensive --case reply-size-320 --ablation none --scaffold --trust-plugin --allow-tools Bash --model sonnet --judge-model sonnet --threshold 0 --runs 1 --keep-temp --no-publish --output-dir "$WORK/results/reply-size-320"
python3 evals-expensive/measure_reply.py --harness "$WORK/results/reply-size-320/aggregate-result.json" --marker TAIL-MARK-6620
```

```bash
claude plugin eval . --eval-dir evals-expensive --case reply-size-full --ablation none --scaffold --trust-plugin --allow-tools Bash --model sonnet --judge-model sonnet --threshold 0 --runs 1 --keep-temp --no-publish --output-dir "$WORK/results/reply-size-full"
python3 evals-expensive/measure_reply.py --harness "$WORK/results/reply-size-full/aggregate-result.json" --marker TAIL-MARK-6620
```

`--keep-temp` keeps each harness run's workspace under `/private/tmp/e-*`,
with the session's own `home/` and `tmp/` sealed inside it.

**Previews and the harness.** In this project's live session, the architect's
56KB reply arrived as a 2KB preview with the full text in a saved file, which
the session read. None of the report-size or loop runs came back as a
preview, so the harness's handling of a saved file wasn't tried again. On
2026-11-05 the harness handed a 35.6KB report back whole and a 53.7KB one as
a preview whose saved file the sandbox blocked, and that one run is the only
evidence that the harness can't read one. The loop is proved in headless live
sessions for that reason, and the harness run is recorded beside them.

**Proving the loop.** Two headless runs, then one harness run. `REPO`, `WORK`
and `M` are as above; run it for R in 1 and 2:

```bash
mkdir -p "$WORK/loop"; D="$M/loop-$R"; rm -rf "$D"; mkdir -p "$D" && (cd "$D" && bash "$REPO/evals-expensive/big-sweep-in-parts/scaffold.sh" && claude -p "$(awk 'n>=2; /^---$/{n++}' "$REPO/evals-expensive/big-sweep-in-parts/prompt.md")" --plugin-dir "$REPO" --setting-sources project --model sonnet --allowedTools Agent,Read,Glob,Grep,Bash,Write --output-format stream-json --verbose > "$WORK/loop/loop-$R.jsonl"); echo "loop $R exit=$?"
grep -c 'SWEEP IN PARTS' "$WORK/loop/loop-$R.jsonl"
python3 "$REPO/evals-expensive/measure_reply.py" --transcript "$WORK/loop/loop-$R.jsonl" --marker 'INVESTIGATE REPORT ENDS'
python3 "$REPO/evals-expensive/check_parts.py" --key "$REPO/evals-expensive/big-sweep-key.json" --repo "$D" --parts "$D/parts" --min-parts 3 --part-size 450 --transcript "$WORK/loop/loop-$R.jsonl"; echo "check exit=$?"

claude plugin eval . --eval-dir evals-expensive --case big-sweep-in-parts --ablation none --scaffold --trust-plugin --allow-tools Bash Write --model sonnet --judge-model sonnet --threshold 0 --runs 1 --keep-temp --no-publish --output-dir "$WORK/results/loop-harness"
```

A pass is `LOOP PROVED` with exit 0 on both headless runs, all 33 facts found.
A nonzero `grep` count shows the new definition ran, since the old one never
printed that line. In `measure_reply.py`'s output the `top` lines should show
one first brief followed by `CONTINUE SWEEP` briefs and nothing else, and the
final message should ask the user nothing. In the harness, a session that
stops and says reports this size can't be handed back is the right outcome if
the parts arrive as previews it can't read.

**The results, on the text before the review's batch (2026-11-24).** Both headless runs scored
`LOOP PROVED` with `--min-parts 3 --part-size 450 --transcript`, each with all
33 facts, no decoy, and `read: 945 of 945` with `readers: 945 of 945, once
each`. Each ran as three parts (one first brief, two `CONTINUE SWEEP`
dispatches), every result whole, and nothing asked.

| Run | Seconds | Files in the parts | Part reports |
|---|---|---|---|
| Headless 9 | 2,992 | 412, 366, 172 | 18.6KB, 11.3KB, 13.9KB |
| Headless 10 | 2,974 | 404, 450, 96 | 20.9KB, 15.9KB, 7.6KB |
| Harness | 2,541 ($9.80) | 368, 366, 216 | 22.3KB, 12.3KB, 14.3KB |

In the harness all six graders passed and no result came back as a preview.
Its kept workspace seals the session's folder, so the three parts were
rebuilt from the Write calls in the kept trace and scored against a freshly
built fixture, with the trace as the transcript: `LOOP PROVED`, no notes.

It took fix rounds to get there. By run 10, ten headless runs were started
and nine finished (run 8 was stopped by a safety classifier while the session
saved part 2, and isn't counted). Four of the nine failed the scorer before
the wording settled, and every failure was a line's format or a number in a
report (an area line with notes inside its count, a wrong sum, a count of 8
areas over a block of 7). None was a file left unread or a sweep that
stopped. Each got a sentence in the agent's text, in three batches, besides
the final review's.

**The results, on the review's batch (2026-11-24).** The batch changed every
command the model runs, so the proofs ran again on it. Three headless runs
(13, 14 and 15) and one harness run: in all four the sweep ran to the end in
three parts without asking, every one of the 945 readable files had one reader
started and completed (the transcript check), and the model used the new
command forms and none of the old. As the case defines a proof, the saved
parts scored with the transcript:

- Run 14 (2,793 s): `LOOP PROVED`, 33 of 33 facts, `readers: 945 of 945, once
  each`.
- Runs 13 and 15 (2,892 s and 3,065 s) aren't proofs. A safety classifier
  stopped the session's write of the last part, and the session stopped and
  said so. Both score `LOOP PROVED` on the reports as the agent returned them.
- The harness run (2,361 s, $9.58, all six graders passed): `LOOP FAILED`.
  Part 1 reported three files unread after an area lead summarised its
  checklist in groups. The transcript shows every one of them was read.

So two headless proofs in a row, the bar the plan set, was met on the text
before the batch, and once on the text after it. Counting every headless run,
fifteen were started: six proved, four failed the scorer, three were stopped
by the classifier (8, 13 and 15), and two (11 and 12) were stopped by me and
not used, when a bug came in.

**The smoke and the head-to-head, on the text before the review's batch.**
`nesting-smoke` passed 8 of 8 graders in 59 seconds ($0.42), and its report
ended with `INVESTIGATE REPORT ENDS`. That one report opened with
`SWEEP IN PARTS: 0 areas not read`, because the smoke's brief said to read its
six files "exactly as you would above the size limit". The head-to-head ran 3
times in 2,004 seconds ($7.50 by the harness), every grader passed in all
three, and no stored report holds a `SWEEP IN PARTS` line. `compare.py`
against the stored 1.7.6 baseline: the new version found 48, 48 and 48 of 48,
missed 0 and made up 0, and scored `BAR MET`. One of the three passes run
during the build scored `BAR MISSED`: `compare.py` read `fxctl X`, a
placeholder inside a quoted docstring, as a made-up command. The scorer wasn't
changed, and the pass on the final text met the bar.

**The smoke and the head-to-head, on the review's batch.** The smoke's brief
now says to run it as one area with one area lead, as for a repo of more than
about 150 files, and that it still comes back as one report, not a sweep in
parts. `nesting-smoke` passed 8 of 8 graders in 50 seconds ($0.39), and the
report is one ordinary report again: it opens `Mode: full sweep, 1 area lead`
and has no `SWEEP IN PARTS` block. The head-to-head ran 3 times in 2,045
seconds ($7.79) and scored `BAR MET`. It found 48, 48 and 45 of 48 and made up
nothing. The third run read every file and left out the three references
planted as "runbook section" ones. It's the first run on the branch to miss a
planted fact; the nine before found 48 of 48.

**After a change to `investigate`,** run the nesting smoke and the
head-to-head again, on top of the loop. They use a repo under 200 files, so
they show the one-report case still works, not that parts do:

```bash
claude plugin eval . --eval-dir evals-expensive --case nesting-smoke --ablation none --scaffold --trust-plugin --allow-tools Bash --model sonnet --judge-model sonnet --threshold 0 --runs 1 --no-publish --output-dir "$WORK/results/smoke"
claude plugin eval . --eval-dir evals-expensive --case investigate-head-to-head --ablation none --scaffold --trust-plugin --allow-tools Bash --model sonnet --judge-model sonnet --threshold 0 --runs 3 --no-publish --output-dir "$WORK/results/h2h-new"
python3 evals-expensive/compare.py --key evals-expensive/head-to-head-key.json --new "$WORK/results/h2h-new/aggregate-result.json" --baseline "$WORK/results/baseline/aggregate-result.json"; echo "compare exit=$?"
```

The smoke passes when all 8 graders pass and its last message holds
`INVESTIGATE REPORT ENDS`. The head-to-head passes on `BAR MET` with exit 0,
and its `control-new-area-leads` grader passing shows the 181-file repo still
comes back as one report. The baseline is the results of the 1.7.6 run
described above; point `--baseline` at where you kept them.

## How a case is built

```
evals/<case>/
  prompt.md          # front matter (runs, tags, max_turns, timeout_seconds,
                     #   allowed_tools, disallowed_tools) and the prompt
  case.yaml          # only when there's a fixture: points at scaffold.sh
  scaffold.sh        # builds the fixture in the run's throwaway workspace
  graders/*.md       # one grader per file
```

Grader types, as this version of Claude Code accepts them (unknown keys are
rejected, which makes a typo loud):

- `llm` with `focus: last_message` (default) or `focus: trace`, and the
  rubric as the body. Write rubrics as "PASS only if ... FAIL if ...".
- `regex` with `target: last_message | trace | files`, a `pattern`
  (JavaScript syntax; case-insensitive is `flags: i`, not `(?i)`), and
  `match: contains | not_contains | count:N`. `files` matches the *paths* of
  files the run created, not their contents; to check what was written,
  match the `trace`, which records every Write and Edit.
- `tool_used` with `tool`, an optional `input_match`, and `min`/`max`. "Never
  ran it" is `min: 0` and `max: 0` (`min` defaults to 1).
- `file_exists` with `path`.

Two sandbox quirks the fixtures work around:

- **git:** on macOS the `git` on `PATH` is Apple's `xcrun` wrapper, which the
  sandbox blocks. A fixture that needs git leaves a `./bin/git` wrapper
  pointing at a real binary (found by the scaffold, which runs outside the
  sandbox), and the case's prompt says to use it.
- **pytest:** the sandbox's Python has no pytest, so the planted-bug fixtures
  use the standard library's `unittest`.

Cases that need the user to answer mid-conversation are written as "here's
the conversation so far; send your next message", because the harness can't
play the user. That's also how they were tested by hand, so nothing is lost.
