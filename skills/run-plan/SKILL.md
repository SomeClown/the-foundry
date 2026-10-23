---
name: run-plan
description: Execute a multi-task implementation plan (usually an architect plan saved in docs/plans/) task by task with Foundry agents. Per task, implement or frontend builds it, test-engineer runs an adversarial round, failures loop back with a cap, and the project's gate must pass with a real exit code before the task is committed. Ends with a qa review of the whole branch, fix batches, and docs. Use when a plan has three or more tasks, or whenever the user says "run the plan", "execute the plan", or "build it" after a plan is approved.
---

# Run the Plan

> "Plans are worthless, but planning is everything."
> — Dwight D. Eisenhower

This skill is for the orchestrating session. It turns an approved plan into
committed, tested work without depending on the session remembering how the
last release was built. The orchestrator briefs, checks, commits, and keeps
the record; agents do the building and the testing. You don't fix code
yourself here: a fix you make skips the adversarial round and fills your
context with code you'll carry for the rest of the run.

Helper script, relative to this skill's base directory:
`scripts/task-brief PLAN_FILE N OUT_DIR` copies Task N out of the plan into
`OUT_DIR/task-N-brief.md` and prints the path.

---

## 1. Before Task 1

1. **Find the plan and its design.** Usually `docs/plans/YYYY-MM-DD-<topic>.md`,
   implementing a numbered section of `docs/design.md`. Read the plan once,
   end to end. Read the design section it cites; when the plan and the design
   disagree, the design is the authority and the plan is its argument.
2. **Settle open owner decisions first.** If the plan lists decisions for the
   user that haven't been answered, ask them all in one numbered message
   (options, recommendation first) before any code is written. Nothing else
   in this skill needs to stop for the user before Task 1.
3. **Get on a branch.** If you're on the default branch, create the one the
   plan names (or `feat/<topic>`). Never start a plan's work on `main`.
4. **Note the gate.** The plan should name it (the one command chain that
   proves the project is healthy: lint, format check, tests). If it doesn't,
   take it from the project's CLAUDE.md or CI config, and write it into the
   plan's build log.
5. **Make the work directory** for briefs, reports, and diff packages:
   `"$(git rev-parse --git-dir)/foundry-run/<plan-basename>/"`. Inside the git
   directory, it's never tracked and needs no `.gitignore` entry, it survives
   compaction and new sessions (a session scratchpad doesn't), and each
   worktree gets its own. Write its path into the build log header.
6. **Make the rules file.** Copy the plan's global rules verbatim (hard rules,
   tripwires, "no new dependencies", voice rules, files nobody may read) into
   `<work dir>/rules.md`. Every dispatch points at it.
7. **Check task sizes once.** Every task should be one implement or frontend
   dispatch that leaves the gate green. Split a task that isn't; merge a run
   of tiny same-shape tasks (section 3). Record either as a ruling.
8. **Start or resume the build log** (section 6).

## 2. The loop, per task

Narrate each step in one short line; the build log and git carry the detail.
Don't stop between tasks to ask whether to continue. The user asked for the
plan to run, so run it. Section 5 lists the only reasons to stop.

### Step 1: Record the base

`BASE=$(git rev-parse HEAD)`. Check `git status` is clean first (apart from
the plan file's build log). Stray changes the build log doesn't explain mean
the last task wasn't committed, or the user is editing too; ask which before
going on. Changes the build log does explain are a task in progress: see
"Resuming" in section 6.

### Step 2: Write the brief

```
<skill dir>/scripts/task-brief <plan> <N> <work dir>
```

The brief is the task's requirements. Exact values (names, limits, messages,
signatures) live in the brief and nowhere else; don't paraphrase them into the
dispatch, where they'll drift.

### Step 3: Dispatch the builder

`the-foundry:implement`, or `the-foundry:frontend` for UI work (with the
`uiux` spec path if the plan has one). The dispatch carries, and nothing else:

- one line on where this task fits ("Task 4 of 12: the official reader")
- the brief path: "Read this first. It's your requirements; use its exact
  values verbatim."
- the rules file path
- plan sections the brief cites, by heading ("also read §3.6 of the plan"),
  so the agent reads those and not the whole plan
- interfaces from earlier tasks the brief can't know about: names,
  signatures, file paths. A few lines, not a history of the run.
- your resolution of anything ambiguous in the brief
- any parked finding from the build log in the area it touches
- the report contract: "Write your full report to `<work dir>/task-N-report.md`.
  Reply with only: status (DONE, DONE_WITH_CONCERNS, NEEDS_CONTEXT, or
  BLOCKED), files changed, the gate's exit code, and any concerns. Don't
  commit, and don't dispatch other agents."

Keep the agent's id from the result; fix rounds resume it.

Handle the status:
- **DONE**: go on.
- **DONE_WITH_CONCERNS**: read the concerns. Correctness or scope concerns get
  settled before testing; observations go in the build log.
- **NEEDS_CONTEXT**: answer, and resume the same agent.
- **BLOCKED**: something has to change before a retry: more context, a
  smaller task, a stronger model (`model: "opus"`), or a ruling on a plan
  defect. Never re-send the same dispatch unchanged.

### Step 4: Package the diff, and spec-check when it earns its cost

Package the task's diff every time; the adversarial round uses it too:

```
git add -A
{ git diff --cached --stat $BASE; git diff --cached -U10 $BASE; } > <work dir>/task-N-diff.txt
```

Staging first matters: builders don't commit, and a plain `git diff` leaves
out new files. The tree was clean at step 1, so everything new is this
task's, but look at `git status --short` before `git add -A`: caches, build
output, or anything the plan's rules say never to commit get staged by name
instead (`git add <paths>`), and the build log notes that the project needs a
`.gitignore` line. Rebuild the package after each fix round.

For a task that later tasks build on, or one with exact contracts (a schema, a
public API, a message format), dispatch `the-foundry:qa` in **spec-check
mode** with the brief, the builder's report, and the package. A small task's
spec check can run on `model: "sonnet"`. Gaps go back to the
builder (step 6) before the adversarial round. For other tasks, the final qa
pass does the spec check across the branch.

### Step 5: Adversarial round

Dispatch `the-foundry:test-engineer` with the brief, the builder's report, the
diff package, and the rules file. Its job is to break this task's behavior,
not to admire it: the brief's edge cases, error paths, boundary values, and
every exact value the brief specifies. It writes tests only, reports failing
tests as bugs with the test name and what the code did, writes its report to
`<work dir>/task-N-tests.md`, and replies with a short status.

A failing test is either a bug in the code or a test that misread the brief.
You decide which, against the brief, and record each call as a ruling in the
build log, not just in the work directory. Misread tests go back to
test-engineer; real bugs go to step 6.

### Step 6: Fix rounds (cap: three)

- **Rounds 1 and 2:** resume the original builder (SendMessage to its id)
  with the failing tests or spec gaps, verbatim, and the tests to re-run.
- **Round 3:** dispatch a fresh builder on `model: "opus"`, with everything
  step 3 lists, plus the open failures and this framing: "Two earlier rounds
  didn't fix this; read the report for what was tried." Its report contract
  says *append* to the report file, so it doesn't overwrite rounds 1 and 2.
- **After round 3,** stop and ask the user (section 5). Don't start round 4.

A round is one builder dispatch to fix failures. Answering a NEEDS_CONTEXT
question, or sending a misread test back to test-engineer, doesn't use one.

Every fix appends to the same report file. When a round's result comes back,
re-run the failing tests yourself, then update the task's progress line in
the build log (`Task N: fix round R/3 done; open: <tests>`). Writing it after
the result, not before the dispatch, means a resumed session never mistakes a
round that was sent for one that finished. If the fix touched something the
adversarial tests didn't cover, a short second test-engineer round on the fix
is worth it.

### Step 7: Run the gate

Run it yourself and read the **real exit code**:

```
set -o pipefail; { <gate command>; } 2>&1 | tail -40; echo "gate exit=$?"
```

The braces send the whole chain's output through `tail`, and `pipefail`
makes the exit code the gate's; without it you'd read `tail`'s. Known expected failures (the plan's "expect only the 2 xfails") are
fine; anything else is a failure and goes back to step 6. The one exception
to "you don't fix code": if the only failure is something the project's own
auto-fixer handles (`ruff format`, `prettier --write`, `gofmt -w`), run it,
re-run the gate, and note it in the log line. Long gates can run
in the background; don't start the next task's builder until this one's gate
is green.

### Step 8: Commit and log

Check `git status` for anything the task shouldn't have touched. Replace the
task's progress line with its `complete` line (section 6), stage the task's
files and the plan, and commit them together with a subject that starts
`Task N:`. The log line names the base, not the new commit (a commit can't
contain its own SHA); the subject is how to find the commit later. Local
commits only: pushing waits for the user.

## 3. Shape rules

- **One writer at a time.** implement, frontend, test-engineer, and docs all
  write files; never run two of them at once on the same branch. Read-only
  agents (qa, investigate, architect) can run in parallel with each other.
- **Batch small same-shape work.** Five tasks that each add one config key, or
  one rename across eight files, go to one builder as one dispatch, with one
  adversarial round and one gate.
- **Hand over files, not text.** Briefs, reports, diffs, and rules travel as
  paths. Everything pasted into a prompt, or printed back by an agent, stays in
  your context for the rest of the run. Read a report only as far as you need
  to decide the next step.
- **Don't re-brief history.** Task 9's dispatch doesn't need tasks 1 to 8,
  just the interfaces it touches.
- **Models.** The Foundry agents carry their own tiers. Override only to
  escalate (round 3, a BLOCKED for reasoning) or to downshift a small review.

## 4. After the last task

### The qa pass

Package the whole branch:

```
MB=$(git merge-base <default branch> HEAD)
{ git log --oneline $MB..HEAD; git diff --stat $MB HEAD; git diff -U10 $MB HEAD; } > <work dir>/branch-diff.txt
```

Then dispatch `the-foundry:qa` with the
package, the design section, the plan, and the build log's parked items to
triage. qa runs in spec-check mode first (does the branch build what the
design describes?), then its usual review.

For a big change (roughly ten or more tasks, or anything touching auth,
money, user data, or scheduling), dispatch two or three qa reviewers **in one
message**, each with a lens, for example: security; data, concurrency, and
scheduling; the feature's behavior against the design. Each gets the same
package and its own lens line.

### Fix batches

You decide which findings get fixed; declining one deliberately is fine, as
long as it goes in the build log with the reason. Group the accepted findings
by area into batches. Each batch is one builder dispatch, then its own
adversarial round, then the gate, then a commit with its log line, exactly as
a task. Findings that live only in test files go to test-engineer, folded into
that batch's adversarial round, since builders own application code and
test-engineer owns tests. When the original builder of the affected code is
still reachable, resume it for the fix (it knows the code). Record "From the
qa pass (fix batch K)" in the build log. Anything qa says only the user can
decide goes into the final report as a question, not into a fix batch.

### Docs

Dispatch `the-foundry:docs` with the design section, the plan, and the build
log. It updates the project's CLAUDE.md, README, and runbooks, and adds an
`### As built (YYYY-MM-DD)` subsection to the design section recording what
changed during the build, drawn from the build log's decisions. A plan rule
like "don't edit docs/design.md" is meant for the builders; tell the docs agent
it may add the "As built" subsection and nothing else. Commit, then
run the gate one last time, so the exit code you report is for `HEAD`.

### Report to the user

One message:
- what was built, in two or three sentences
- tasks and fix batches completed, with the commit range
- the final gate's command and exit code, quoted
- **Decisions I made**: every ruling from the build log, each with what it
  costs if it's wrong, so the user can check them
- parked findings and declined qa findings, with reasons
- questions only the user can answer, numbered, with options and a
  recommendation
- the next step (push, PR, release) as a question. Shipping waits for their
  yes, and then the `ship` skill takes it from there.

## 5. When to stop and ask

Only these stop the run:

- **A fix cap was hit** (three rounds on one task or batch). Bring the failing
  tests, what was tried, and two or three ways forward with a recommendation.
- **The plan is wrong in a way that changes what gets built**, and the design
  doesn't settle it.
- **Anything irreversible or outside the branch**: production, a migration on
  real data, deleting anything that isn't the run's scratch, a push, a merge,
  a tag, a release.
- **A secret or credential** would have to be read, written, or created.

Everything else (an ambiguous brief, a misread test, a task to split, a qa
finding to decline) you decide, log as a ruling, and keep going. A ruling the
user can see and reverse costs less than a run parked on a question. When you
do stop, ask everything that's open in one numbered message, with options,
and log the stop in the build log. The run waits for the answer; don't start
other tasks around it unless the user says to.

## 6. The build log

The run's memory lives on disk, because conversation memory doesn't survive
compaction. Keep it as the plan's last section, so it's committed with the
work and feeds the docs task:

```
## Build log

Gate: `<command>` (expect: <known expected failures>)
Branch: feat/<topic>, from <base sha>
Work dir: <path>

### Progress
- Task 1: complete (from a1b2c3d; gate exit 0; adversarial: 14 tests, 1 bug fixed in round 1)
- Task 2: fix round 2/3 done; open: test_expiry_dst, test_empty_reward

### Decisions made during the build
- Ruling (Task 2): <what you decided>. Why: <reason>. If wrong: <cost>.
- Ruling (Task 2): test_empty_reward is a real bug, not a misread; the brief says an empty reward reads "reward unknown".

### Parked
- Task 3: <finding>, parked because <reason>.

### From the qa pass (fix batch 1)
- ...
```

**Resuming.** After compaction, a restart, or a new session: read the build
log and `git log`, and trust them over your memory. A task with a `complete`
line is done; don't redo it (its commit is the one whose subject starts
`Task N:`). For the task in progress, BASE is `HEAD`, since its commit hasn't
happened yet.

**Check for a dispatch still running first.** A background agent sent before
compaction may still be working, and its result will arrive on its own.
Look for one (the agents your session lists as running, or a report file
changed in the last few minutes) before dispatching anything; two writers on
the branch is worse than a short wait. A round that landed without a log line
still counts toward the cap: if the report file has a section for round R+1,
log it as done.

Then:

- **Its line says `fix round R/3 done`:** re-run its open tests first, since
  a round may have landed just before the interruption. Still failing: the
  next round is R+1 (or a stop, if R was 3). Passing: carry on from step 7.
- **Uncommitted changes with no progress line:** an interrupted first
  dispatch. Check them against the brief, then either carry on from step 4 or
  discard them with the user's okay.
- **The work directory is gone** (a reboot, a cleaned git directory): make it
  again, rebuild the brief and rules from the plan, and tell the next builder
  that the earlier report is lost and the working-tree diff is the record of
  what was tried. The builder's agent id is gone too, so the next round is a
  fresh dispatch.

---

## Red flags

| Thought | What to do instead |
|---|---|
| "It's a two-line fix; I'll just make it" | Resume the builder. Your fix skips the adversarial round. |
| "Tests passed in the agent's report" | Run the gate yourself and read the exit code. |
| "Should I keep going?" | Yes. Stop only for section 5. |
| "One more fix round will do it" | Three is the cap. Stop and ask. |
| "I'll paste the plan so the agent has context" | Brief path, rules path, cited sections. Not the plan. |
| "test-engineer and implement can run together to save time" | One writer at a time. |
| "That qa finding is wrong; I'll skip it" | Decline it in the build log, with the reason. |
| "I'll push so CI can check it" | Pushing waits for the user. |
