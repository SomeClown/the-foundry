# Acceptance criteria traced from design to plan to tests to the spec check

- **Plan file:** `docs/plans/2026-11-26-traced-acceptance-criteria.md`
- **Source of truth:** the orchestrating session's draft (`.git/foundry-run/traced-criteria/draft.md` in the main checkout; item 7 of the owner's top-ten list), as amended by the architect's cold read. No design section.
- **Done when:** the architect's reading of the draft; no design section lists one.
  - AC-1: brainstorm's design section ends with a numbered **Done when** list with `AC-n` ids, played back as the last part.
  - AC-2: the architect gives every task a **Covers** line with each id's text, and ends Testing Strategy with one coverage line per id. An id that no task covers is a question in Risks and Coupling.
  - AC-3: when the brief has a **Covers** line, implement and frontend report one line per id, and test-engineer writes a test per id and reports one line per id.
  - AC-4: qa's spec check gives each id a line in one of five shapes, and `NOT MET` or `UNTESTED` makes it GAPS.
  - AC-5: run-plan does five things with ids: it checks test-engineer's id lines before the gate, carries ids through splits, fix batches and the `complete` line, stops on a change to a design item, and reports every id's state.
  - AC-6: with no ids anywhere, every agent and skill reads as it does today. Every new rule is conditional on ids being there, except brainstorm's list and the architect's own list.
  - AC-7: three eval cases carry ids and have exact graders, and tests hold the graders and the label names to the agent texts.
  - AC-8: the shared `## How Every Report Opens` section says `Status:` is the first line, with no summary sentence above it, in all eight carriers.
- **Branch:** `feat/traced-acceptance-criteria`, cut from `main` at 6f39625.
- **Gate:** the five lines in `docs/plans/2026-11-26-ci-and-parallel-gate.md`'s header ("Gate (from this change on)"), run from the repo root one line at a time, each exit read from its own echo. Before Task 1, run it on 6f39625 and record both `Ran` counts in the build log. Expected after Task 1: about 18 more tests (one new file plus one new class in `tests/test_eval_cases.py`). If it differs, say by which tests. Task 2 adds none. The pytest-Python line shows 1 skip, the stock line 5, and the three validates exit 0.
- **Rules for every agent:** rules 1 to 7 of `docs/plans/2026-11-25-agent-security-rules.md`'s header, word for word, plus:
  8. No Python line in a new or changed file holds only the p-a-s-s word. No line of a rubric, fixture, agent, skill or doc starts with that word in lowercase, wrapped prose included. None of the whole-environment forms `DirectoryScannerTest` lists appear.
  9. No new agent, tool, dependency or script. Nothing outside `tests/` parses ids.
  10. Insert new text exactly as this plan gives it. Don't rewrap or reword existing sentences except the lines this plan says are replaced. Agent and skill lines stay under 80 columns.
  11. `## How Every Report Opens` stays identical across all eight carriers. Only Task 2 touches it, and it edits all eight at once.
  12. In `skills/run-plan/SKILL.md`, never write a backticked label with a colon followed by the word "line". The label is always the bold **Covers**.
  13. Grader patterns use YAML single quotes, hold no inline flag group, and write a backtick as `\x60` and a single quote as `\x27`.
  14. Every `scaffold.sh` stays executable (git mode 100755).

## 1. Goal and Approach

When this is done, each project design ends with a numbered **Done when** list (`AC-1`, `AC-2`, …), and the ids travel through every step:
- Each plan task names the ids it covers, with their text, and Testing Strategy says how each id gets checked.
- Builders say where each id is met.
- test-engineer writes a test per id.
- qa's spec check gives every id its own line.
- run-plan keeps the count and reports each id's state.

All of it is text in the existing agents and skills. Nothing parses ids except tests. The trade-off that decided the shape is that a run-plan brief carries only its task's own section. The id's text therefore rides on the task's **Covers** line, a small duplication inside one file, instead of in a separate coverage section that builders and the per-task qa never receive. Every new rule is conditional on ids being there, so work without ids runs as it does today.

## 2. Tasks

### Task 1: Ids through brainstorm, architect, the builders, test-engineer, qa and run-plan, with three eval cases and the tests

- **Builder:** implement.
- **Covers:**
  - AC-1: brainstorm's design section ends with a numbered **Done when** list with `AC-n` ids, played back as the last part.
  - AC-2: the architect gives every task a **Covers** line with each id's text, and ends Testing Strategy with one coverage line per id. An id that no task covers is a question in Risks and Coupling.
  - AC-3: when the brief has a **Covers** line, implement and frontend report one line per id, and test-engineer writes a test per id and reports one line per id.
  - AC-4: qa's spec check gives each id a line in one of five shapes, and `NOT MET` or `UNTESTED` makes it GAPS.
  - AC-5: run-plan does five things with ids: it checks test-engineer's id lines before the gate, carries ids through splits, fix batches and the `complete` line, stops on a change to a design item, and reports every id's state.
  - AC-6: with no ids anywhere, every agent and skill reads as it does today. Every new rule is conditional on ids being there, except brainstorm's list and the architect's own list.
  - AC-7: three eval cases carry ids and have exact graders, and tests hold the graders and the label names to the agent texts.

**What to do.** Each item gives the anchor text and the exact text to insert.

**`skills/brainstorm/SKILL.md`**

1. In §5, insert this bullet right before the `- In batch mode, send all the parts` bullet:
```
- **The last part is "Done when"**: the numbered list section 7 describes,
  played back and approved like any other part.
```
2. In §7 "What it covers", insert this bullet right after `- the behavior, part by part, as approved`:
```
- **Done when:** a numbered list, each item one thing someone could watch
  happen or a test could check, in the user's words, with an id: `AC-1`,
  `AC-2`, and so on. Ids never change once approved: a dropped item stays,
  marked dropped with the date and why, and a new item takes the next
  number. Plans, tests and reviews cite items by id.
```

**`agents/architect.md`**

3. In the header-block list, insert this bullet right after the `- **Source of truth:**` bullet:
```
- **Done when:** only when the source has no `AC-n` list (no design
  section, or one written before designs had them): your own numbered list,
  `AC-1: <one thing someone could watch happen or a test could check>`,
  marked as your reading of the request
```
4. In "### 2. Tasks", insert this bullet right after the `- **Files** —` bullet, which ends `in later sessions`:
```
- **Covers** — the ids this task delivers, one sub-bullet each with its
  text word for word (`AC-2: <the item>`), or `none: <why>` for groundwork.
  The builder sees only its task's section, so the text travels here
```
5. In "### 4. Risks and Coupling", append this sentence to the paragraph, after `(flag it clearly rather than guessing).`:
```
An id no task covers is one of these, never dropped quietly.
```
6. In "### 5. Testing Strategy", add this new paragraph after the existing one:
```
Then one line per id, in id order: `AC-n: Task N; test`, `AC-n: Task N;
command: <command>` or `AC-n: Task N; by hand: <why no test can>`. Name
every task that delivers it (`Tasks 2 and 4`), and list a dropped id as
`AC-n: dropped`. With ids from two design sections, write `§16 AC-2`.
```

**`agents/implement.md`**

7. Append this sentence to How to Work step 3, after `say so in your report.`:
```
When the brief has a **Covers** line, put each id a test checks, as
written (`AC-2`), in the test's docstring or a comment, so a search for
the id finds it.
```
8. In "What to Report Back", insert this bullet right after the `- **What changed** —` bullet:
```
- **Covers** — when the brief has a **Covers** line, one line per id:
  `AC-n: met at <file:line>` or `AC-n: not met: <why>`
```

**`agents/frontend.md`**

9. In "What to Report Back", insert the same bullet, byte for byte as in item 8, right after `- What changed in each file under \x60Files changed\x60, one line each` (the backticks shown as `\x60` here).

**`agents/test-engineer.md`**

10. Append this to How to Work step 4, after `say it wasn't seen failing).`:
```
When the brief has a **Covers** line, that behavior is each id on it: at
least one test per id that would fail if the id weren't met, with the id
as written (`AC-2`) in its docstring or a comment. An id the plan checks
by hand or by a command, or one you can't test here (it needs a browser,
production, a person's eye), gets no test and a reason in your report.
```
11. In "What to Report Back", insert this bullet right after `- Tests added/changed, one line each on what behavior they pin`:
```
- When the brief has a **Covers** line, one line per id:
  `AC-n: <test names> (passes | fails)` or `AC-n: not tested: <why>`
```

**`agents/qa.md`** (Spec-Check Mode)

12. Insert this bullet right after the `- **Every requirement met.**` bullet, which ends `Cite file and line.`:
```
- **Ids first, when there are any.** When the brief, plan or design lists
  ids (`AC-1`, on a **Covers** line or in a **Done when** list), give each
  one a spec line (below) before walking the rest. An id is met when the
  diff does it and a test asserts it, or the plan or build log records why
  it isn't tested. When the dispatch says the tests come later, judge only
  whether each id is met.
```
13. Replace the spec fence's first line, `Spec: MATCHES | GAPS`, with these six lines. The four bracket lines stay below them:
```
Spec: MATCHES | GAPS
AC-n MET file:line; <test name, or the recorded reason>
AC-n NOT MET: what's absent or different
AC-n UNTESTED file:line: met, but no test asserts it and no reason is recorded
AC-n CANNOT VERIFY: why
AC-n DROPPED
```
14. Replace `Then continue with the usual findings, unless the dispatch says spec only.` with:
```
Any `NOT MET` or `UNTESTED` line makes it GAPS. With no ids, leave the
`AC-n` lines out. Then continue with the usual findings, unless the
dispatch says spec only.
```

**`skills/run-plan/SKILL.md`**

15. §1 step 7: append `A split task's ruling says which ids each part covers; a merged one covers all of theirs.` after `Record either as a ruling.`
16. Step 4: append this after `the spec check happens in the final qa review of the whole branch.`:
```
When the brief has a **Covers** line, tell qa the tests come in step 5,
so it judges each id met or not and leaves tests to the final pass.
```
17. Step 5: append this to the first paragraph, after `and replies with a short status.`:
```
When the brief has a **Covers** line, its report has a line per id.
Before step 7, check that each id has a test or a reason it has none: an
id with neither goes back to test-engineer, and a reason you accept is a
ruling in the build log.
```
18. Step 8: append `When the brief has a **Covers** line, the \x60complete\x60 line ends with its ids (\x60; AC-1, AC-3\x60).` after `` with a subject that starts `Task N:`. `` (backticks shown as `\x60`).
19. "The qa pass": append `When the design or the plan lists ids, its spec section has a line for every one.` after `then its usual review.`
20. "Fix batches": append this to the paragraph that starts `Group the accepted findings`, after `into a fix batch.`:
```
A finding on an id (`AC-2 NOT MET`, `AC-2 UNTESTED`) keeps the id in its
batch's brief and its log line.
```
21. "Docs": append `It names by id any **Done when** item that changed or was dropped.` after `drawn from the build log's decisions.`
22. "Report to the user": insert this bullet right after `- the final gate's command and exit code, quoted`:
```
- when the plan has ids, each one with its state at `HEAD`: met (and how
  it's checked), not met, or dropped, from the qa pass and the fix batches
  after it
```
23. §5, the "plan is wrong" bullet: append this after `The user's own answers don't need it.`:
```
  Changing or dropping an item of the design's **Done when** list is a stop
  of this kind. Once the user answers, the design marks the old id dropped
  (date and why), a changed item takes the next number, and the plan's
  **Covers** lines follow, in one commit. A list the architect wrote
  itself changes by ruling.
```

**`docs/orchestrator.md`**

24. In the pasted block's Routing list, insert this bullet right after the `- Multi-file feature or refactor` bullet:
```
- A design ends with a numbered **Done when** list (`AC-1`, `AC-2`, ...),
  and a plan says which task covers each id. Outside `run-plan`, give a
  builder, `test-engineer` or `qa` the ids its step covers, with their
  text; each reports against them. Work with no ids runs as before.
```

**Eval cases**

25. `evals/qa-spec-check-planted/scaffold.sh`: in `brief.md`, insert these lines right after the `### Task 4: Rate limit the /refresh command` line and its blank line, before the existing first bullet:
```
- **Covers:**
  - AC-1: the first `/refresh` in a server runs.
  - AC-2: a second `/refresh` in the same server within 10 minutes is refused with `Refresh is cooling down; try again in N minutes.`, N rounded up.
  - AC-3: one server's cooldown never holds up another server's `/refresh`.
```
26. New graders in `evals/qa-spec-check-planted/graders/`:
    - `ac-1-met.md`: `type: regex`, `target: trace`, `pattern: '(?:\\n|\n)[ \t>*\x60-]*AC-1 MET\b'`, `match: contains`.
    - `ac-2-not-met.md`: the same with `AC-2 NOT MET\b`, plus `weight: 2`.
    - `ac-3-untested.md`: the same with `AC-3 UNTESTED\b`, plus `weight: 2`.

    The case total becomes 7, and either heavy grader failing leaves 5/7, under 0.8.
27. `evals/qa-spec-check-planted/graders/catches-the-plants.md`: replace the rubric body with:
```
PASS only if the spec section reports GAPS and catches all of: the remaining minutes are
floored, not rounded up (AC-2 NOT MET, or a DIFFERENT line); the cooldown is read from the
database / a new settings function the brief didn't ask for (EXTRA, and against "no
database change"); the missing tests for the exact refusal message and for a call after
600 s (MISSING, or on the id's line); and that the report's "tests for all three cases"
claim is false. FAIL if it says MATCHES or misses any of these.
```
28. `evals/architect-plan-format/scaffold.sh`: in `docs/design.md`, append these lines to §2, after `Non-goals: stemming, stop words. Anti-goal: a new dependency.` and a blank line:
```
**Done when:**
- AC-1: `top_words("b a b c", 2)` returns `[("b", 2), ("a", 1)]`.
- AC-2: `top_words("a", 0)` raises `ValueError("n must be a positive integer")`.
- AC-3: `tally.__version__` is `"0.2.0"`.
```
29. New graders in `evals/architect-plan-format/graders/`:
    - `covers-line.md`: `type: regex`, `target: trace`, `pattern: '\*\*Covers:?\*\*(?:\\n|\n|[ \t*:\x60—-])*AC-[0-9]'`, `match: contains`.
    - `coverage-lines.md`: `type: regex`, `target: trace`, `pattern: '^(?=[\s\S]*AC-1[*\x60]*: Tasks? [0-9])(?=[\s\S]*AC-2[*\x60]*: Tasks? [0-9])(?=[\s\S]*AC-3[*\x60]*: Tasks? [0-9])'`, `match: contains`, `weight: 3`.

    The total becomes 14, and a coverage miss leaves 11/14, under 0.8.
30. `evals/brainstorm-writes-design/prompt.md`: add this as the last bullet of the "Approved" list, after the analytics-dashboard bullet:
```
- Part 4, what counts as done, was approved as you'd write it from the decisions above.
```
31. New grader `evals/brainstorm-writes-design/graders/done-when-list.md`: `type: regex`, `target: {source: file, path: docs/design.md}`, `pattern: '## 3\. [\s\S]*\*\*Done when[\s\S]*AC-1\b[\s\S]*AC-2\b'`, `match: contains`.

**Tests**

32. New file `tests/test_traced_criteria.py` (standard library; Python 3.9; in the style of `tests/test_report_opening.py`). It needs `problems(texts)` over an in-memory dict of texts: the agents via `test_security_rules.agent_texts()`, plus `run-plan`, `brainstorm` and `orchestrator`. It returns a list, and an empty list means the rules hold:
    - (a) `**Covers**` appears in architect, implement, frontend, test-engineer, qa and run-plan.
    - (b) `**Done when**` appears in brainstorm, architect, qa, run-plan and orchestrator.
    - (c) qa's spec fence (the first fence after `Put a spec section first`) holds, in order: lines starting `AC-n MET `, `AC-n NOT MET:`, `AC-n UNTESTED `, `AC-n CANNOT VERIFY:` and the line `AC-n DROPPED`, then the four bracket lines.
    - (d) Every id state named in run-plan, architect and orchestrator, matched with `AC-(?:n|[0-9]+) ((?:[A-Z]{3,} ?)+)\b` and trimmed, is one of qa's five.
    - (e) The bullet starting `- **Covers** — when the brief has` is identical, whitespace folded, in implement and frontend.
    - (f) Every `AC-` in agents, skills and orchestrator matches `AC-(?:n|N|[0-9]+)\b`.
    - (g) architect holds `` `AC-n: Task N; test` `` (the eval grader's shape).

    Tests: one RealTree test (`problems(real) == []`), plus one mutation per rule (a)–(g) that edits an in-memory copy and asserts a matching needle. Examples: drop `**Covers**` from frontend; rename `NOT MET` to `MISSING` in run-plan's item-20 text only; change one word of the frontend bullet; write `AC1` in brainstorm.
33. `tests/test_eval_cases.py`: a new class `TracedCriteriaCaseTest`:
    - The three qa id graders each match `hand_back("Spec: GAPS\nAC-1 MET bot/commands.py:14; test_first_call_runs\nAC-2 NOT MET: N is floored\nAC-3 UNTESTED bot/commands.py:9: no test with two servers")`. `ac-1-met` doesn't match it once `AC-1 MET` becomes `AC-1 NOT MET`, and `ac-2-not-met` doesn't match `AC-2 MET`.
    - None of the three matches the built fixture's `brief.md` (use `Fixture`).
    - `covers-line` and `coverage-lines` match `json.dumps` of a sample plan holding `**Covers:**\n  - AC-1: ...` and the three `AC-n: Task 1; test` lines. `coverage-lines` fails when the `AC-3` line is gone. Neither matches the built `docs/design.md` of `architect-plan-format`.
    - `done-when-list` matches a sample `## 3. Weekly recap ...\n**Done when:**\n- AC-1: ...\n- AC-2: ...`, and doesn't match the built `docs/design.md` of `brainstorm-writes-design`.
34. `CHANGELOG.md`, under `## [Unreleased]`, add a new paragraph after the last one:
```
Designs now end with a numbered **Done when** list, ids `AC-1` on, and the
ids travel. Each plan task names the ids it covers, with their text, and the
plan says how each is checked; builders say where each is met,
`test-engineer` writes a test per id, `qa`'s spec check gives every id a
line (met, not met, untested, can't verify, dropped), and `run-plan` keeps
the count and lists every id's state at the end. Work with no ids runs as
before. `brainstorm-writes-design`, `architect-plan-format` and
`qa-spec-check-planted` now carry ids.
```

**Verify:**
- `python3 tests/run_tests.py test_traced_criteria test_eval_cases test_eval_cases_adversarial test_report_opening test_structure test_self_consistency_pin_mutations test_check_before_building_pin_mutations test_security_rules` exits 0.
- `node` is installed, so the JavaScript-compile test runs instead of skipping.
- The full gate exits 0 on all five lines, with about 18 more tests on each Python.

### Task 2: `Status:` comes first, with no summary sentence above it

- **Builder:** implement.
- **Covers:**
  - AC-8: the shared `## How Every Report Opens` section says `Status:` is the first line, with no summary sentence above it, in all eight carriers.

**What to do:** in each of the eight carriers (`agents/architect.md`, `agents/devops.md`, `agents/docs.md`, `agents/frontend.md`, `agents/implement.md`, `agents/qa.md`, `agents/test-engineer.md`, `agents/uiux.md`), replace these two lines:
```
Open your reply with these four lines, before anything else, and open a
report file your brief names with them too:
```
with these three:
```
Open your reply with these four lines, before anything else, and open a
report file your brief names with them too. `Status:` is the first line of
each, with no summary sentence above it:
```
Then add this sentence at the end of the `## [Unreleased]` paragraph from Task 1, or as its own paragraph if Task 1 was dropped: `The four opening lines now say \x60Status:\x60 comes first, with no summary sentence above it; in 2 of 20 runs an agent had put one there.` (backticks shown as `\x60`).

The existing tests keep their green result because the change keeps the two strings they mutate: `before anything else, and open a\nreport file` and `before anything else`.

**Verify:** `python3 tests/run_tests.py test_report_opening test_security_rules test_structure` exits 0, and the full gate exits 0.

### Task 3: Run the cases and record them (the orchestrating session)

1. Commit Tasks 1 and 2, then run these on that clean commit (`WORK=$(mktemp -d)`):
```
claude plugin eval . --tag agents --ablation none --scaffold --trust-plugin --allow-tools Bash Write Edit --judge-model sonnet --threshold 0.8 --runs 4 -j 4 --keep-temp --no-publish --output-dir "$WORK/results/agents"
claude plugin eval . --case brainstorm-writes-design --ablation none --scaffold --trust-plugin --allow-tools Bash Write Edit --judge-model sonnet --threshold 0.8 --runs 4 --keep-temp --no-publish --output-dir "$WORK/results/brainstorm"
```
2. Look at `covers-line`, `coverage-lines`, the three `ac-*` graders, `done-when-list`, and every `opens-with-four-lines` across the agents runs.
3. Stopping rule: at most two grader-tuning rounds for the whole set, and only for graders that failed for a reason other than what the agent did. A real weakness in an agent is a finding for the owner, with its numbers.
4. Record the runs with `python3 evals/scorecard.py --commit <commit> "$WORK/results/agents" "$WORK/results/brainstorm"`, then commit.

**Verify:** the gate is still green, and `evals/SCORECARD.md` has a row for each case run.

## 3. Data / Schema Changes

None. The grader keys used (`weight`, a file target) are ones the harness schema already accepts.

## 4. Risks and Coupling

- **Pinned paragraphs in run-plan:** the fix-batch paragraph and the "parked … retro" bullets are pinned whole (`tests/test_structure.py`, `CheckBeforeBuildingPinsTest`), and step 5's Testing Strategy phrase is mutated by `tests/test_self_consistency_pin_mutations.py`. Items 17, 20 and 22 insert outside those spans. A builder who rewraps one of them will see it fail.
- **qa's label test:** `test_qa_and_run_plan_use_the_same_label_and_the_same_two_phrases` fails on any backticked label with a colon followed by "line" in run-plan. Rule 12 covers this.
- **The shared opening section** is checked for identity across eight files. Task 2 must edit all eight in one dispatch.
- **Grader fragility:**
  - The qa graders assume qa writes id lines in the fence's shape. A table instead of lines fails them, which is the behavior under test.
  - `coverage-lines` assumes the architect follows the given line shape.
  - The em dash in `covers-line`'s class assumes the trace keeps non-ASCII characters as they are (the harness writes JSON with `JSON.stringify`).
- **Duplicated criterion text:** each item's text sits in the design and in each task's **Covers** line. A mid-build change has to update both, and item 23 says so.
- **Needs your decision:**
  1. Should brainstorm's "Done when" part be played back for every size it brainstorms, or only for project-size designs?
     - A. Every size (recommended). It's one short part, and a small change routed through implement and qa can still carry ids.
     - B. Project size only.

## 5. Testing Strategy

- Task 1 has to do the following:
  - add `tests/test_traced_criteria.py` (rules a–g with one mutation each);
  - add `TracedCriteriaCaseTest` to `tests/test_eval_cases.py`;
  - keep the generic eval schema tests green, including no inline flags, JS compile, no trace pattern that matches its own prompt, and the weight rule for heavy graders.
- test-engineer's adversarial round should try three things:
  - spellings the label rules miss: `**Covers:**` versus `**Covers**`, and `AC-01`;
  - whether rule (d) catches a state name run-plan invents;
  - whether each new grader can succeed from the fixture or the prompt alone.
- Task 2 adds no tests. The identity test and the two existing mutations cover it, and Task 3's runs measure the behavior.
- Coverage:
  - AC-1: Task 1; test
  - AC-2: Task 1; test
  - AC-3: Task 1; test
  - AC-4: Task 1; test
  - AC-5: Task 1; test
  - AC-6: Task 1; by hand: the final qa pass reads each new rule for its condition, since no test can judge "reads as today"
  - AC-7: Task 1; test
  - AC-8: Task 2; command: `python3 tests/run_tests.py test_report_opening`

## 6. Out of Scope

- `investigate`, `file-reader`, `devops`, `docs`, `uiux`, `debug` and `ship` get no changes. The docs agent records changed ids through run-plan's Docs dispatch (item 21).
- Id graders on the `implement-test-first` and `test-engineer-reports-the-bug` cases, whose totals are pinned. qa's final pass covers that link.
- A run-plan eval that shows the whole chain in one session.
- Any change to the build-log example in run-plan §6.
- A version bump or release steps.

## Build log

Gate: the five lines in `docs/plans/2026-11-26-ci-and-parallel-gate.md`'s header (expect: 1 skip with the pytest Python, 5 on stock)
Branch: feat/traced-acceptance-criteria, from 6f39625
Work dir: `.git/foundry-run/traced-criteria/` in the main checkout
Baseline on 6f39625 (2026-11-26): `Ran 2288` on both Pythons, exit 0; the three validates exit 0.

Stopping rule, stated to the owner before the build: one architect pass, one builder dispatch per task, one test-engineer round with at most three fix rounds, the gate, then real-session runs for only the cases the change touches, with the tuning rounds Task 3 allows.

### Progress
- Task 1: built (from dda158e; targeted run of the eight named test files `Ran 365`, exit 0; the builder's whole-suite run `Ran 2309`, exit 0, 21 more than the baseline: 13 in `tests/test_traced_criteria.py`, 8 in `TracedCriteriaCaseTest`). Committed before Task 2 so each can be reverted alone; the adversarial round and the gate run over both; AC-1, AC-2, AC-3, AC-4, AC-5, AC-6, AC-7
- Task 2: built (from fd657af; the same replacement in all eight carriers, the section byte-identical across them by the session's own hash; `test_report_opening`, `test_security_rules`, `test_structure` and `test_traced_criteria` `Ran 185`, exit 0; the builder's whole-suite run `Ran 2309`, exit 0); AC-8
- Adversarial round over Tasks 1 and 2: `tests/test_traced_criteria_adversarial.py`, 100 tests. First pass: 96 tests, 12 failing methods, none flaky. Fix round 1/3 done (eleven gaps: a rule (h) for qa's "makes it GAPS" sentence, the fence's first line read, `AC-01`, `ac-1` and `AC -1` caught, a state no longer read across a line break, `done-when-list` held to a second-level `## 3. ` heading, `covers-line` taking an escaped em dash, the three qa id graders taking a bold id, a colon and a numbered prefix). Fix round 2/3 done (three false positives round 1 opened, all from a pattern crossing a line break). Three tests of the tester's were changed on the session's rulings below. Open: none.
- Gate after the fix rounds (2026-11-26, on the staged tree over f14a6f8): `Ran 2413`, OK, exit 0 on both Pythons (1 skip, 5 skips); validate, manifest and directory exit 0. That is 125 more than the baseline's 2288: 13 plus the round-1 and round-2 additions in `tests/test_traced_criteria.py`, 8 in `TracedCriteriaCaseTest`, 100 in the adversarial file.

### Decisions made during the build
- Ruling (plan, §4 question 1): A, the "Done when" part is played back at every size brainstorm handles. The session took the architect's recommendation instead of stopping for the owner. Why: the difference is one clause in one bullet, and the owner asked for bounded rounds. If wrong: brainstorm shows one more short part on small changes until the bullet is narrowed to project size; told to the owner in the final report.
- Ruling (plan): the two tasks go to the same builder, Task 1 first and committed before Task 2 starts, so Task 2 is its own commit and can be reverted alone.
- Ruling (Task 1): rule (b) of `tests/test_traced_criteria.py` looks for the prefix `**Done when`, not the literal `**Done when**`. Why: the plan's own inserted text writes `**Done when:**` in brainstorm and architect, so the literal check failed against the plan's text. If wrong: a file could write `**Done whenever` and satisfy the rule; the adversarial round is asked to try it.
- Ruling (Task 1): five anchors differed from the plan's quotes (items 16, 18, 19, 20, 21: a wrapped anchor, a missing phrase, two mid-line anchors, one 81-column line). The builder inserted at the sentence boundary and reworded nothing; the pinned-paragraph tests still hold. If wrong: nothing lost, the text is as the plan gives it.
- Ruling (adversarial round): eleven of the twelve failing tests show real gaps and went to the builder; `test_a_non_breaking_space_difference_is_caught` misread the plan, which says the two bullets are compared "whitespace folded", and a non-breaking space is whitespace. The tester changed it to pin today's behavior. If wrong: the implement and frontend bullets could differ by a non-breaking space unseen.
- Ruling (fix round 1): the three qa id graders accept the shapes a report drifts into (`**AC-1** MET`, `AC-1: MET`, `1. AC-1 MET`), though qa's fence prescribes `AC-n MET`. Why: item 5 showed a grader that fails on formatting when the agent did the right thing is noise. If wrong: a qa that stops following the fence's exact shape still satisfies the graders; rule (c) holds the fence itself.
- Ruling (fix round 2): rule (d) reads a state from the id's own line only, and a state ending at the line end that is a prefix of one of qa's five (`NOT`, `CANNOT`) is a wrapped state and is quiet. Why: a harmless rewrap of agent text must not trip the gate. If wrong: an invented state on the line after its id (`AC-2`, a break, `MISSING`) goes unseen; the tester's pin for that case was flipped to say so.

### Parked
- Rule (d) reads only run-plan, architect and orchestrator, and only uppercase states: a made-up state in implement, test-engineer or frontend, or `AC-2 Not Met`, isn't seen. Parked because those files name no states today.
- Rules (a) and (b) are satisfied by the label inside a code span or an unrelated sentence, and (b) by `**Done whenever`. Pinned as accepted by the adversarial file; parked because a stricter match would have to parse the files' structure.
