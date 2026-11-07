# Behavior tests for the skills (and some agents)

> "Trust, but verify."
> — Russian proverb, borrowed by a US president, overused by everyone since

The tests in `tests/` check the Foundry's scripts and that the repo agrees
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
it; running everything costs real money (see below).

```bash
claude plugin eval . --tag ship --scaffold --trust-plugin --allow-tools Bash Write Edit \
  --judge-model sonnet --threshold 0.8 --no-publish
```

- `--tag brainstorm | run-plan | debug | ship | agents` picks a skill's cases;
  `--case 'debug-*'` works too.
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
| `run-plan` | decisions, resume | The fix-round cap, one writer at a time, rulings instead of stalls, production off limits; picking up after compaction without redoing finished tasks |
| `debug` | polluted test, wrong total, flaky pressure, user's fix is right, decisions, production report | Root cause before any fix, a failing test first, the fix in the right place (the polluting test, the parser, the test that raced), measuring before bumping a sleep, a polluter proven (the `ran-the-check` grader on debug-polluted-test) before it is named, agreeing when the user's fix is the right one, never running production commands |
| `ship` | asks before pushing, decisions, CI pending in the app | Preflight catches an unbumped version; the repo's own way of releasing; one ask before any push or tag; a bare "Done" isn't approval; the stuck-check re-run; waiting for the tag's build; handing the merge back when the PR monitor can't say CI passed |
| `agents` | qa spec check, architect plan format, implement test-first | qa's spec-check mode catches a floor that should be a ceiling, an unrequested database dependency, missing tests, and a report that overclaims; the architect's plan has its header, `### Task N:` headings that run-plan's own brief command can split (checked by running it), exact Verify commands, and repo-relative paths; implement runs the failing test before it edits the code |

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
that an agent can start an agent that starts an agent.

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
