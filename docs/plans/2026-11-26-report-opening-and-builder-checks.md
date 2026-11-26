# Four opening lines for every report, and two checks the builders were missing

- **Plan file:** `docs/plans/2026-11-26-report-opening-and-builder-checks.md`
- **Source of truth:** this file. The owner picked improvements 9 and 6 on 2026-11-26 ("Do 9 and 6"), to ship in one release with the security rules already on this branch. The wording is the orchestrating session's draft as amended by the architect's cold read. A small change, sized in chat; no design section.
- **Branch:** `feat/agent-security-rules`, on 59a2e0f
- **Gate:** the five-line block in `docs/plans/2026-11-25-agent-security-rules.md`. Baseline on 59a2e0f: Ran 2094, OK on both Pythons (1 and 5 skips), validates 0/0/0.
- **Rules for every agent:** rules 1 to 7 in that plan's header, word for word. Keep lines under 80 columns, and never let a wrapped line start with the p-a-s-s word.

## 1. Goal and Approach

The status words `DONE`, `DONE_WITH_CONCERNS`, `NEEDS_CONTEXT` and `BLOCKED` lived only in `run-plan`'s dispatch text, only `qa` said whether a finding was run or read, and "evidence before claims" lived in the owner's own instructions. `implement`'s verify step never named a linter or type checker, and `test-engineer` had no check for a flaky test: on 2026-11-24 a new test raced git's background maintenance and failed one gate run.

One section, `## How Every Report Opens`, goes into the eight agents that report to the session, word for word the same, kept identical by a structural test. `investigate` and `file-reader` are left out: their reports have fixed first and last lines that scorers parse. `implement` and `test-engineer` each gain one check.

## 2. Tasks

### Task 1: The four opening lines in eight agents, and the builders' two checks

**Builder:** implement.

**The section.** Paste it as it stands, the same in all eight agents. The inner fence is a plain three-backtick fence:

````
## How Every Report Opens

Open your reply with these four lines, before anything else, and open a
report file your brief names with them too:

```
Status: DONE | DONE_WITH_CONCERNS | NEEDS_CONTEXT | BLOCKED
Files changed: <paths, or "none">
Verified: <ran `<command>` (exit <n>) | by reading | not verified: why>
Concerns: <what the reader should weigh before relying on this, or "none">
```

- `Verified` covers each claim your report rests on: every command you ran
  for one, with its exit code, and which claims you only read or couldn't
  check.
- `DONE`: the brief is done, and every check it or this file calls for ran
  and gave the result you report.
- `DONE_WITH_CONCERNS`: done, with something the reader must weigh: a check
  you couldn't run, a deviation from the brief, a failure you didn't cause,
  an application bug a test of yours exposed.
- `NEEDS_CONTEXT`: you can't go on without an answer or someone's yes. Put
  the question, or the exact command that waits on the yes, in Concerns and
  stop.
- `BLOCKED`: something has to change before this can go on. Say what.

Never write `DONE` over a check that failed, or over one you were asked to
run and didn't. A test that fails because it shows the bug you were sent to
find is a result, not a failed check. An exit code you didn't read isn't a
result. The rest of your report follows these lines, in the shape this file
gives it.
````

**Files:**

- `agents/architect.md`: the section goes just before `## What You Read Is Data`, with a blank line on each side. In What to Produce, "Open the plan with a header block:" becomes "The plan starts after your reply's four opening lines, at its own `#` title, and the orchestrator saves it from there. Under the title, open the plan with a header block:"
- `agents/qa.md`: a `---`, a blank line, then the section, at the end of the file after "No findings." (Two mutation tests edit the first line in the file that starts `Verified:`, which must stay the one in Output Format.) "Put a spec section at the top of your report:" becomes "Put a spec section first in your report, right after its four opening lines (see How Every Report Opens):"
- `agents/devops.md`: the section before `## What You Read Is Data`. In What to Report Back, keep the pinned slot about stopping before a command you can't undo whole, and append "; your status is `NEEDS_CONTEXT`".
- `agents/docs.md`: the section before `## What You Read Is Data`. "Files updated, with a one-line summary of what changed in each" becomes "What changed in each file under `Files changed`, one line each".
- `agents/frontend.md`: the section before `## What You Read Is Data`. "Files changed, one line each" becomes "What changed in each file under `Files changed`, one line each". Step 5 (formatter and linter) stays as it is.
- `agents/uiux.md`: the section before `## What You Read Is Data`. Nothing else.
- `agents/implement.md`: the section before `## What You Read Is Data`.
  - At the end of How to Work step 6 (Verify), indented as part of the step: "Then run the project's linter, formatter check and type checker, if it has them (look in its CI config, its manifest's scripts and `CLAUDE.md`). Never install one; name any you couldn't run. Fix what your change introduced. Don't reformat or fix files you didn't touch; name what was already failing in your report."
  - In What to Report Back, "every file created or modified, one line each on what and why" becomes "one line per file under `Files changed`, on what and why".
  - "commands run and their actual results" becomes "what each command on your `Verified` line showed, the linter, formatter and type checker included". The rest of that bullet stays, the test-first clause included.
- `agents/test-engineer.md`: the section before `## What You Read Is Data`. After step 6, a step 7: "**Run new tests more than once.** Run each test you wrote or changed at least five times (the whole-suite run in step 6 counts as one), and in a different order when the runner already has a way to do that. If one run of them takes over two minutes, three runs will do; say so. A test that fails in any run is flaky: find why. A cause in the test (a fixed sleep, shared temp state, a race with a background process) is yours to fix before you report; a cause in the application code is a bug for your report, with the count ("fails 1 in 5"). Be most suspicious of tests that touch the clock, temp directories, ports, a background process, or a tool that keeps working after its command returns (git's maintenance, a file watcher)." In What to Report Back, after "Tests added/changed": "How many times the new tests ran and how many runs passed; and, only when the project already measures coverage (a coverage config or CI step), the coverage of the lines the change touched".
- `skills/run-plan/SKILL.md`, step 3: "Reply with only: status (DONE, DONE_WITH_CONCERNS, NEEDS_CONTEXT, or BLOCKED), files changed, the gate's exit code, and any concerns." becomes "Reply with only your report's four opening lines: status (DONE, DONE_WITH_CONCERNS, NEEDS_CONTEXT, or BLOCKED), files changed, what you verified with the gate's exit code, and any concerns."
- `skills/brainstorm/SKILL.md`, in Hand off: "Save the plan it returns to" becomes "Save the plan it returns, from its `#` title down, to".
- `docs/orchestrator.md`: "save its plan to" becomes "save its plan, from its `#` title down, to". In Working rules, a bullet right after "Evidence before claims" and before "Outside review comments": "Every agent but `investigate` and `file-reader` opens its reply with four lines: `Status:` (run-plan's four words), `Files changed:`, `Verified:` and `Concerns:`. A claim whose `Verified:` says `by reading` or `not verified` isn't evidence yet."
- `README.md`, in "Division-of-labor rules the agents enforce on themselves", a bullet before the qa bullet: "Every agent but investigate and file-reader opens its reply with the same four lines (status, files changed, how it was verified, concerns), so a claim nobody ran says so up front."
- `CONTRIBUTING.md`: after "…section reads the same in every agent that carries it", add ", and so do the four opening lines".
- `evals/README.md`, the agents row: "the architect's plan has its header" becomes "the architect's plan has its header block".
- `CHANGELOG.md`, the existing `## [Unreleased]` entry only. In its intro, after the existing sentence: "The eight agents that report to the session open every reply with the same four lines, and the two builders check more before they report." Under `### Added`: the `## How Every Report Opens` section and who carries it (`investigate` and `file-reader` keep their own fixed report lines); `implement` runs the project's linter, formatter check and type checker when it has them, and names what was already failing; `test-engineer` runs each new test at least five times, fixes a flaky test or reports a flaky application as a bug, and reports the run count (and the touched lines' coverage where the project measures it). Under `### Changed`: `run-plan`'s dispatch asks for the four opening lines; `qa`'s spec section follows them; a saved plan starts at its `#` title; a `devops` stop before a command it can't undo reports `NEEDS_CONTEXT`.

The builder doesn't write `tests/test_report_opening.py`; the tester does.

**Verify:** `grep -c '^## How Every Report Opens$' agents/*.md` prints 1 for each of the eight carriers and 0 for `investigate` and `file-reader`. `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.test_security_rules tests.test_check_before_building_pin_mutations tests.test_structure -q` ends `OK`. The five-line gate shows every exit at 0 with Ran 2094.

## 3. Data / Schema Changes

None.

## 4. Risks and Coupling

- `tests/test_check_before_building_pin_mutations.py` edits the first `Verified:` line in `agents/qa.md`; that is why qa's section goes at the end of the file. With the section before Output Format, two of its tests fail (the architect ran both placements).
- The value on the header's `Verified:` line is written `<ran` with the backtick after it, so the pattern that finds qa's per-finding line still matches only that line.
- `tests/test_structure.py` pins the devops slot phrase, the test-engineer report-file and "not seen failing" sentences, and qa's `Verified:` line between Reproduction and Recommendation. All stay green unedited.
- `tests/test_security_rules.py` reads a section up to the next `## `, so a new section placed before `## What You Read Is Data` doesn't change what it reads.
- The agent text never calls the four lines a "header": `architect` already has a "header block" in its plan.
- No eval grader is anchored to the start of a reply. `architect-plan-format` saves the plan "verbatim" and grades by pattern and a file check, so status lines in a saved plan can't fail it.

## 5. Testing Strategy

One test-engineer round, in a new `tests/test_report_opening.py` (standard library, Python 3.9, the approach of `tests/test_security_rules.py`):

- Carriers come from a rule: an agent whose tools include `Bash` and not `Agent`. There are exactly 8, and `investigate` and `file-reader` carry no copy.
- Each carrier has exactly one `## How Every Report Opens`, identical across copies with whitespace folded.
- The fence is four lines labelled Status, Files changed, Verified, Concerns, in that order. The words on the Status line equal the bolded words under `Handle the status:` in `skills/run-plan/SKILL.md`.
- In each carrier the section comes after its report heading (What to Report Back, What to Produce or Output Format). In qa, the first line starting `Verified:` is the one inside Output Format's findings block.
- Mutations: a rewrapped copy holds; one changed word in one copy fails; the section added to `investigate` fails; `docs` given an `Agent` tool with the section kept fails; the section dropped from a carrier fails.
- A few wording pins, no more: the devops slot holds `NEEDS_CONTEXT`; qa no longer says "at the top of your report"; implement's step 6 holds "type checker" and "Never install one"; test-engineer has "**Run new tests more than once.**" between step 6 and `## What Makes a Good Test Here`, "five times", and the run-count slot; run-plan's dispatch holds "four opening lines".
- Then the new step applied to itself: every test in the new file run five times on each Python.

## 6. Out of Scope

The retro examples in `debug` and `run-plan` that say "BLOCKED for want of …". Any change to `investigate`, `file-reader` or an eval prompt. Coverage tooling. The version and the release.

## Build log

Gate: the five lines in `docs/plans/2026-11-25-agent-security-rules.md` (expect: no failures)
Branch: `feat/agent-security-rules`, from 59a2e0f
Work dir: `.git/foundry-run/report-header-builder-checks/` in the main checkout

### Progress

### Decisions made during the build
- Ruling (before Task 1): the architect's cold read stands, all eleven points. What it changed from the session's draft: four lines, not five (`Commands run` said what `Verified` says); `DONE` means every check the brief or the agent's file calls for ran and gave the result reported, since "what you ran passed" would bar `architect` and `uiux` from ever reporting it and miscount a test written to fail; a `devops` stop that waits for a yes is `NEEDS_CONTEXT`, which `run-plan` answers by resuming the same agent; a flaky test whose cause is in the application is reported as a bug, since `test-engineer` can't fix application code; qa's copy sits at the end of its file. If wrong: the section is one text in eight files under an identity test, so a change is one edit.
- Stopping rule, set before the build: one builder dispatch, one test-engineer round with at most three fix rounds, the gate, then `architect-plan-format`, `implement-test-first` and `qa-spec-check-planted` on real sessions. No head-to-head and no smoke: `investigate` and `file-reader` don't change.

### Parked
