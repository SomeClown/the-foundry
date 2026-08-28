# A Feature, Start to Finish

> "The first 90 percent of the code accounts for the first 90 percent of the
> development time. The remaining 10 percent accounts for the other 90 percent."
> — Tom Cargill's ninety-ninety rule, still undefeated

This is a worked example of one feature flowing through the full Foundry
pipeline. The feature is genericized but real-shaped: it's the kind of request
that actually lands in a session, with the kind of complications that actually
surface. Nothing here is hypothetical in structure — only the project details
have been filed off.

**The scenario:** a Flask web app that generates event schedules. The user
asks: *"Admins need to be able to add blackout dates to a season — days when
no events can be scheduled. Existing schedules should regenerate around them."*

Your orchestrating session is the narrator here. Everything below is what it
does, in order.

---

## Stage 1: investigate

You could skip this if the session already knows the codebase cold. This one
doesn't — it's a fresh session, and guessing at a data model from vibes is how
you end up with two sources of truth and a Saturday gone.

**The briefing** (what the orchestrator passes to the `investigate` agent):

> Investigate this project with focus on: the season/schedule data model, how
> schedules are generated and stored, the existing admin CRUD patterns, and
> the migration mechanism. A feature is coming that adds per-season blackout
> dates which the schedule generator must respect.

**What comes back** (condensed): the report identifies the stack (Flask +
SQLAlchemy + SQLite), the models involved (`Season`, `Match`, a scheduling
module with a date-mapping function), the fact that the project uses a custom
`flask db-migrate` command rather than Alembic, and — this is the part that
pays for the whole stage — a coupling warning: the date-mapping logic is also
used by the export code, so blackout handling must live in the generator, not
be bolted on in the route handler.

## Stage 2: architect

**The briefing:**

> Here is the investigation report [attached]. Plan the blackout-dates
> feature: new model, admin CRUD, generator changes so schedules skip
> blackout dates, and regeneration of existing schedules. Respect the custom
> migration mechanism the report describes.

**What comes back** (condensed): a six-step plan. New `BlackoutDate` model
with a season foreign key; a migration entry for the custom migrate command;
date-mapping change in the scheduler (skip blackout dates and extend the
season tail-ward); two admin routes (add, delete) following the project's
existing CRUD pattern; a regenerate action; and a verification command per
step. The plan explicitly flags one decision for the human: should
regeneration preserve already-played matches or rebuild the whole schedule?
The architect doesn't guess on questions like that — it asks. The user says
preserve. Good thing, too, because rebuilding would have been the easier
implementation and the wrong product.

## Stage 3: implement

**The briefing:** the plan, verbatim, plus the user's preserve-played-matches
decision.

**What comes back:** the model, migration entry, generator change, and routes,
implemented step by step with the project's own idioms, each step verified
(module imports, app boots, migration runs clean on a scratch copy). One
deviation reported honestly: the plan's step 4 assumed a helper function that
didn't exist, so the agent flagged the conflict and used the project's actual
pattern instead of silently improvising a new design. That flag-don't-improvise
behavior is the difference between a deviation report and a surprise you find
in production three weeks later.

*(If this feature had visible UI beyond a plain form — say, a calendar picker —
the orchestrator would split the work: `uiux` produces the control-selection
spec, `frontend` builds it and verifies in the browser. For a standard admin
form matching existing patterns, `implement` handles it.)*

## Stage 4: test-engineer

**The briefing:**

> New feature just landed [summary + files]. Write tests: blackout dates are
> skipped by generation, season extends correctly, played matches survive
> regeneration, and the admin routes enforce authorization. Suite baseline
> first.

**What comes back:** baseline suite green, then new tests, including one that
fails — regeneration was dropping byes for teams idle in the final round. An
edge case nobody briefed, found because the test agent tests behavior, not the
plan. The bug report goes back to the orchestrator, which routes the fix to
`implement` (the test agent never touches application code, even when the fix
is one obvious line — *especially* when the fix is one obvious line, because
"obvious" is how the last three bugs got in). Fix lands, suite green.

## Stage 5: qa

**The briefing:**

> Review this change set [file list] plus its interaction with existing
> routes. Security and correctness focus: these are admin-only mutations.

**What comes back:** ranked findings. One MEDIUM — the delete route fetched
the blackout record by ID without verifying it belonged to the given season
(an IDOR, minor here but free to fix). Two LOWs. The orchestrator routes the
MEDIUM to `implement`, judges one LOW worth fixing, and consciously declines
the other, on the record. Declining a finding on purpose is fine; discovering
it again in six months with no memory of the decision is not.

## Stage 6: devops

**The briefing:** deploy per the project's documented runbook; the change
includes a migration.

**What comes back:** the runbook executed in order, database backed up before
migrating (it's SQLite — a timestamped copy costs nothing and has saved
someone's bacon on every project old enough to shave), service restarted,
post-deploy verification against the live app, rollback procedure stated. The
deploy isn't reported done when the commands finish; it's done when the
service answers correctly.

## Stage 7: docs

**The briefing:**

> Blackout dates feature shipped [summary]. Sync CLAUDE.md, README, and the
> roadmap. The migration command list changed.

**What comes back:** docs updated in place, in each file's existing voice, plus
one piece of drift found and fixed — the README still described schedule
generation as immutable-after-creation, which stopped being true about an hour
ago. This matters more than it looks: the next fresh session's `investigate`
run reads these files first, and it will believe them.

---

## The scorecard

Seven stages, four of which caught something a straight-line single-agent
implementation would likely have shipped: the coupling warning (investigate),
the preserve-vs-rebuild question (architect), the dropped-byes bug
(test-engineer), and the IDOR (qa). None of those catches required brilliance.
They required *separation* — a reader with no stake in the plan, a planner with
no ability to cut corners in code, a tester who can't quietly fix what it
finds, a reviewer who runs the suite instead of admiring the diff.

Skip stages freely when they don't apply — a one-line fix does not need an
architecture review, and nobody's handing out medals for ceremony. But when a
stage would have caught something and you skipped it, you'll know exactly
which one it was. You'll know because you'll be reading the bug report.
