# A Feature, Start to Finish

> "The first 90 percent of the code accounts for the first 90 percent of the
> development time. The remaining 10 percent accounts for the other 90 percent."
> — Tom Cargill's ninety-ninety rule, still undefeated

This is a worked example of one feature flowing through the Foundry: the four
skills your orchestrating session runs itself, and the agents it dispatches.
The feature is genericized but real-shaped, the kind of request that actually
lands in a session, with the kind of complications that actually surface. Only
the project details have been filed off, and the test counts, hashes, and file
names are invented. The shape of each step is the real one.

**The scenario:** a Flask web app that generates event schedules. The user
asks: *"Admins need to be able to add blackout dates to a season — days when
no events can be scheduled. Existing schedules should regenerate around them."*

Your orchestrating session is the narrator here. Everything below is what it
does, in order.

```
brainstorm → investigate → architect → run-plan → ship
                           (implement, test-engineer, qa, docs run inside it)
         debug: whenever something breaks and the cause isn't proven
```

---

## Stage 1: brainstorm

That request reads like a finished thought. It isn't. "Existing schedules"
hides matches already played, "blackout dates" could mean a day or a week, and
"regenerate" could land on a schedule the players have already seen. A builder
would pick an answer to each, quietly, and I'd find out which at the worst
possible moment. So the session starts with `brainstorm`.

**The opening** is a line saying the user can skip the questions, and one open
question: *"Walk me through the last time a day was off the table and the
schedule put events on it anyway."* The user describes a venue closing for floor
repairs and four matches moved by hand. After a few reads of the code (no
permission needed), the session adds that matches have a played flag and
seasons a published flag: different states, different answers.

**The questions** come as one numbered message, recommendation first:

```
1. A new blackout covers days that already have matches. What happens?
   A. Played matches stay; only unplayed ones move (recommended: a played
      match is history, and moving it rewrites results)
   B. Everything moves   C. Refuse if a played match is in the way
2. How big can a blackout be?
   A. One day (recommended: simplest)   B. Start and end date, whole days
   C. Part of a day
3. What does regenerating do to a published schedule?
   A. Builds a draft beside it for an admin to publish (recommended: players
      have seen the published one; moving their match silently gets emails)
   B. Overwrites it and tells everyone   C. Overwrites it
```

Who can set blackouts isn't on the list. The project's other season settings
are admin-only, so that's a default the session states instead of asking. The
answer is `1A, 2B, 3A`. Note that 2B isn't the recommendation. The user is
allowed to disagree, and it cost two characters.

**One design part played back,** with guesses marked as guesses:

```
Part 2 of 4: what happens to matches on a blackout day

Played matches never move. If a new blackout covers days with played matches,
the admin sees a notice listing them. Unplayed matches on those days move to
the next open dates, and the season's last date moves out by the days that
took. Every team keeps one entry per round: a match or a bye.

Guesses I made: "next open date" means the next non-blackout day the season
already allows. What's wrong or missing?
```

**The gate holds.** The user replies *"looks right, just build it."* That
approves Part 2, and might also mean "stop asking," so the session doesn't
guess. It asks in one line whether to skip the remaining parts (stating its
calls on them) or see them first. The user says show me. Nothing gets built
meanwhile: no scaffolding, no `implement`, no `run-plan`.

**The design lands** as a new numbered section of `docs/design.md`,
`## 14. Blackout dates (v2.4.0, approved 2026-10-23)`: owner decisions, goals
and non-goals, the behavior part by part, and a **Calls I made** list. Before
the user reads it, a fresh `general-purpose` subagent reads §14 cold and lists
only what it would have to guess at. Whether the season end moves when a
blackout pushes the final round past it is minor, and goes into Calls I made.
Whether deleting a blackout puts the days back changes what gets built, so it
goes to the user, who picks "nothing changes until someone regenerates." Then
they approve §14, and it's committed on its own, on a new
`feat/blackout-dates` branch, which is where the whole build will live.

## Stage 2: investigate

You could skip this if the session already knows the codebase cold. This one
doesn't, and guessing at a data model from vibes is how you end up with two
sources of truth and a Saturday gone.

**The briefing** (what the orchestrator passes to the `investigate` agent):

> Investigate this project with focus on: the season/schedule data model, how
> schedules are generated and stored, the existing admin CRUD patterns, and
> the migration mechanism. A feature is coming (docs/design.md §14) that adds
> per-season blackout dates which the schedule generator must respect.

**What comes back** (condensed): Flask + SQLAlchemy + SQLite, a custom
`flask db-migrate` command rather than Alembic, and the part that pays for the
whole stage: the date-mapping logic is also used by the export code, so
blackout handling must live in the generator, not the route handler.

## Stage 3: architect

**The briefing:** the path to §14, its number, and the investigation report.
The architect is read-only, so the orchestrator saves the plan it returns as
`docs/plans/2026-10-23-blackout-dates.md`, which opens with a header:

```
Plan file: docs/plans/2026-10-23-blackout-dates.md
Source of truth: docs/design.md §14
Branch: feat/blackout-dates
Gate: ruff check . && ruff format --check . && pytest -q (expect: all green)
Rules for every agent:
- No new dependencies.
- Schema changes go through a flask db-migrate entry, never db.create_all().
- Generation never modifies or deletes a played match.
- tests/test_export.py passes unmodified (it pins the shared date mapping).
```

Then five tasks, each under a `### Task N:` heading, because `run-plan` pulls
each one out by that heading:

```
### Task 2: Generator skips blackout dates
What to do: the date-mapping function skips dates inside the season's
blackout ranges and extends the season's last date by the days skipped. Every
team keeps one entry per round, a match or a bye. Ranges outside the season
are ignored.
Files: app/scheduling.py (mapping change); tests/test_scheduling.py
Verify: pytest tests/test_scheduling.py -q passes; the gate exits 0
Builder: implement
```

The old version of this walkthrough had the architect stopping to ask whether
regeneration should preserve played matches. Now the plan lists no open owner
decisions, because brainstorm got them answered. The architect's job is order
and size: the model and migration come first, so every later gate runs against
a real table, and the generator and the regenerate-as-draft are separate tasks.

## Stage 4: run-plan

A plan with three or more tasks goes to `run-plan`, which replaces the separate
implement and test-engineer stages. The session stays on `feat/blackout-dates`
(never `main`), makes a work directory inside the git directory
(`.git/foundry-run/2026-10-23-blackout-dates/`, so it's never tracked and
survives a compaction), copies the plan's rules into a `rules.md` there, and
starts the build log as the plan's last section. Then, per task, using Task 2:

1. *Brief and build.* Record `BASE=$(git rev-parse HEAD)`; the `task-brief`
   script copies Task 2 into `<work dir>/task-2-brief.md`, where its exact
   values live and nowhere else. `implement` gets a short dispatch: where the
   task fits, the brief and rules paths, the Task 1 interfaces it needs, and
   the report contract (full report to a file, a short reply, no commits). It
   works test-first and replies `DONE`.
2. *Spec check, where it earns it.* Later tasks build on this one, so `qa` runs
   in spec-check mode on a small model with the brief, the design section, the
   report, and the diff: `Spec: MATCHES`. Task 3 (regenerate as a draft) and
   Task 5 (a plain form) skip this; the final qa pass covers them.
3. *Adversarial round.* `test-engineer` tries to break the task: twelve tests,
   two fail. A team idle in the final round loses its bye once a blackout
   shifts the rounds, which is a real bug nobody briefed. The other test
   expects an error for a blackout before the season starts, when the brief
   says such ranges are ignored. That one misread the brief.
4. *Rulings.* The session decides which is which, against the brief, and logs
   both. The misread goes back to `test-engineer`. For the bug, the session
   resumes the original `implement` with the failing test verbatim. It doesn't
   make the one-line fix itself, however obvious, because its fix would skip
   the adversarial round, and "obvious" is how the last three bugs got in.
5. *The gate, with a real exit code:*

   ```
   $ set -o pipefail; { ruff check . && ruff format --check . && pytest -q; } 2>&1 | tail -40; echo "gate exit=$?"
   ...
   87 passed in 6.4s
   gate exit=0
   ```

   The agent's "tests pass" is a claim. This is the evidence.
6. *Commit and log.* The subject is `Task 2: Generator skips blackout dates`,
   plan file included, and the progress line becomes:

   ```
   - Task 2: complete (from 3fa91c2; gate exit 0; adversarial: 12 tests, 1 bug fixed in round 1)
   ```

Rulings go in the build log, not just the work directory. In Task 4,
`implement` comes back `DONE_WITH_CONCERNS`: the plan assumed a `season_or_404()`
helper that doesn't exist, so it flagged the conflict and used the project's
actual pattern. That's the difference between a deviation report and a surprise
three weeks later.

```
- Ruling (Task 2): test_idle_team_keeps_bye_in_final_round is a real bug; the
  brief says every team has an entry in every round, bye included.
- Ruling (Task 2): test_blackout_before_season_start_raises misread the brief.
- Ruling (Task 4): no season_or_404() exists; use the inline get_or_404 the
  other admin routes use. If wrong: one route to tidy later.
```

The run doesn't stop to ask "shall I continue?" Three failed fix rounds on one
task, a plan wrong enough to change what gets built, anything irreversible, or
a secret would stop it. None came up. Commits stay local; pushing waits.

**The qa pass.** The session packages the whole branch against its merge base.
It touches scheduling and admin mutations, so two `qa` reviewers run in one
message, one with a security lens and one on scheduling behavior against the
design. Both do the spec check first, and one finds:

```
Spec: GAPS
[MISSING] design §14 Part 2: the notice listing played matches when a new
          blackout covers them. Not in any task brief.
```

The plan dropped something the design said, and it would have belonged to Task
3, one of the two that skipped the per-task check. Where the plan and the
design disagree, the design wins. Then the ranked findings. One MEDIUM: the delete route fetched the
blackout by ID without checking it belonged to the given season (an IDOR,
minor here but free to fix). Two LOWs: the form accepts an end date before the
start, and the blackout list isn't paginated. The session fixes the gap, the
MEDIUM, and the first LOW as fix batch 1, resuming the original `implement`
(it knows the code), with its own adversarial round, gate, and commit. It
declines the other LOW, on the record, because discovering a finding again in
six months with no memory of the decision is the bad outcome:

```
### From the qa pass (fix batch 1)
- Declined: blackout list isn't paginated (LOW). A season has a handful;
  revisit if one ever has fifty.
```

**Docs.** `docs` gets §14, the plan, and the build log. It updates CLAUDE.md
and the README, and adds an `### As built (2026-10-23)` subsection to §14 (the
one place it may touch the design): the notice came in with fix batch 1, and
Task 4 used the inline lookup. It also finds drift: the README still described
schedule generation as immutable after creation. The next fresh session's
`investigate` reads these files first and believes them. Then the gate runs
once more, so the exit code in the final report (with every ruling and what it
costs if wrong) is for `HEAD`.

## Stage 5: ship

The user says "ship it." The `ship` skill reads the project's runbook and
history first and follows what it finds: here, PRs with squash merges,
annotated `v` tags, and an image build triggered by the tag. Preflight comes
before the ask. The session runs the gate itself (exit 0) and greps for the
old version string, which finds the packaging bump and also a fallback
constant still saying 2.3.1. That gets fixed through the usual agents. It also
names the migration: it adds a table to production, so the user needs a backup.

**The one ask,** every step listed, so one "go ahead" covers them:

```
Ready to ship v2.4.0. If you say go, I'll:
1. Push feat/blackout-dates and open the PR.
2. Merge it (squash) once CI is green.
3. Build and check the image locally (Docker Desktop on, then off again).
4. Tag v2.4.0 and push the tag, then wait for the tag's image build.
5. Give you the deploy commands.
Go ahead?
```

A step that isn't on the list needs its own ask.

**A detour: debug.** CI goes red on `test_regeneration_keeps_played_matches`,
which passed locally. The user says "just re-run it." The session says in one
sentence that it's measuring first, because a re-run that goes green teaches
nothing. Alone, the test passes 20 of 20. The whole suite in random order (CI
does that; my machine doesn't) fails it 6 times in 20, so the baseline smells
like state left behind. The skill's `find-polluter` script names the culprit:
`test_export_custom_start` sets `app.config["SEASON_START"]` directly and never
puts it back. The code is right and the test is the bug, so `test-engineer`
writes the pin (polluter first, watched failing) and the fix (`monkeypatch`,
watched passing), and the proof is the same loop, 20 of 20 against 6 in 20.
The trap goes to `docs` as one line in CLAUDE.md, and since a second push wasn't
on the ask's list, the session asks before pushing the fix.

**Back to the ship.** The session has a PR monitor bound, which wakes it when
CI *fails* and not when it passes, so it says CI is still running and ends the
turn with the merge as the next step. Waiting for a "passed" notice would mean
waiting forever. When the user returns it reads the status, sees green, and
squash-merges with `--delete-branch`. Then it pulls `main` and does the local
image check (starts, reports 2.4.0, has its license files, `docker ps` empty,
Docker quit). Only then `git tag -a v2.4.0 -m "v2.4.0: blackout dates"` and
the push. A tag has no PR, so the monitor won't see its build either, and
this app doesn't let the session poll for it. So it finds the run, tells the
user it usually takes about fifteen minutes, and checks it when they're back.
The deploy commands wait for that build, because commands handed over early
pull an image that doesn't exist yet.

**The deploy hand-off.** The user runs every production command; the session
gives them one per block. The project has a runbook, so `devops` isn't
dispatched. First, since there's a migration, a backup (it's SQLite, so a copy
costs nothing), then the version bump:

```
sudo cp /opt/app/data/app.db /opt/app/data/app.db.pre-2.4.0
```

```
sudo sed -i 's/^TAG=2\.3\.1$/TAG=2.4.0/' /opt/app/.env && sudo grep '^TAG=' /opt/app/.env
```

Then the runbook's deploy script (it refuses to run during league night, so
the session checks the clock first), the status command and what to expect,
and the rollback in one line: put 2.3.1 back *and* restore the database copy,
because the migration added a table. The deploy is done when the user says so,
not when the commands finish. They paste "deployed and healthy," the status
docs get updated (the CLAUDE.md status line with version, date, and rollback),
and the session asks one line: *Push both?*

---

## The scorecard

Each step caught something a straight-line single-agent run would likely have
shipped:

- **brainstorm:** played versus published, settled in three letters instead of
  discovered after a rebuild; and what deleting a blackout does.
- **investigate:** the date mapping shared with export.
- **architect:** task order and size, and a `Verify` on each, so none could be
  "done" by assertion.
- **implement and test-engineer:** the flagged helper, and the dropped byes,
  found by testing behavior, not the plan.
- **qa:** the spec gap the plan dropped, and the IDOR.
- **debug:** a polluting test, found by measuring when the easy answer was a
  re-run.
- **ship and docs:** the stale version constant, the backup, the wait for the
  tag, and the README sentence that stopped being true an hour earlier.

None of those catches required brilliance. They required *separation*: a
reader with no stake in the plan, a planner who can't cut corners in code, a
tester who can't quietly fix what it finds, a reviewer who checks the work
against what was agreed, and an orchestrator that runs the gate itself instead
of taking anyone's word for it.

Is this too much ceremony? For a small change, yes, and the skills say so: a
fully specified request just gets done, and a one-line fix doesn't need an
architecture review. But when a stage would have caught something and you
skipped it, you'll know exactly which one it was. You'll know because you'll be
reading the bug report, which is where the other 90 percent lives.
