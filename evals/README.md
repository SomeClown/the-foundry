# Behavior tests for the skills (and one agent)

> "Trust, but verify."
> — Russian proverb, borrowed by a US president, overused by everyone since

The tests in `tests/` check the Foundry's scripts and that the repo agrees
with itself. They can't check whether a skill makes a model *behave* the way
it should: ask numbered questions with a recommendation first, hold the gate
when the user says "sounds great, build it", measure a flaky test before
touching it, never push before the ask. That's what these cases are for.

Each case is a situation that once caught something real while a skill was
being built or tested. They run with Claude Code's own eval harness,
`claude plugin eval`, which starts a fresh headless session per run with only
this plugin loaded, builds any fixture repo the case needs, and grades the
result.

## Running them

From the repo root. Run the cases for the skill you changed, before releasing
it; running everything costs real money (see below).

```bash
claude plugin eval . --tag ship --scaffold --allow-tools Bash Write Edit \
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
- `--max-cost-usd 10` caps the spend. `-j 4` runs four at once.
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
| `debug` | polluted test, wrong total, flaky pressure, user's fix is right, decisions, production report | Root cause before any fix, a failing test first, the fix in the right place (the polluting test, the parser, the test that raced), measuring before bumping a sleep, agreeing when the user's fix is the right one, never running production commands |
| `ship` | asks before pushing, decisions, CI pending in the app | Preflight catches an unbumped version; the repo's own way of releasing; one ask before any push or tag; a bare "Done" isn't approval; the stuck-check re-run; waiting for the tag's build; handing the merge back when the PR monitor can't say CI passed |
| `agents` | qa spec check, architect plan format, implement test-first | qa's spec-check mode catches a floor that should be a ceiling, an unrequested database dependency, missing tests, and a report that overclaims; the architect's plan has its header, `### Task N:` headings that run-plan's own brief script can split (checked by running the script), exact Verify commands, and repo-relative paths; implement runs the failing test before it edits the code |

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
