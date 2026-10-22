---
name: debug
description: Find the root cause of a bug, failing or flaky test, hang, crash, or production misbehavior before anyone fixes it. Use whenever something is broken or behaving unexpectedly and the cause isn't already proven, including "just bump the timeout" or "quick fix" requests. Asks the user what they saw, reproduces the failure on demand, tests one hypothesis at a time, pins the cause with a failing test, and only then routes the fix through implement. Stops and rethinks after three failed fixes.
---

# Debug

> "It is a capital mistake to theorize before one has data."
> — Sherlock Holmes, *A Scandal in Bohemia*

This skill runs in the main session, because the fastest evidence is usually
the user's: what they saw, where, and since when. It does the thinking and the
evidence-gathering itself, and hands the legwork to agents: `investigate` for
reading code paths and history, `test-engineer` for a reproducing test,
`implement` for the fix.

**The rule: no fix without a root cause.** Before any fix is written, you can
say in one sentence what is wrong and why, and point to the evidence that
shows it. "The timeout is too short" is a cause only once you've seen how long
the work actually takes on the machine that fails. Until then it's a guess,
and a guessed fix that happens to pass hides the bug until it comes back
somewhere worse.

Fixing symptoms is still allowed in one case: production is on fire. Then
stop the bleeding (roll back, disable the feature), say plainly that it's a
stopgap, and come back here for the cause.

Techniques referenced below are in `references/techniques.md` in this
skill's directory; read the one you need when you need it.

---

## 1. Ask what they saw

Skip anything the report or a quick reproduction already answers (if that's
everything, ask nothing), and ask the rest in one numbered message, with options where the answer is likely one of a few:

```
1. Where does it happen?
   A. Only on your Mac   B. Only in CI   C. Both   D. Production
2. How often?
   A. Every time   B. Some runs (roughly how many in ten?)   C. Once so far
3. Does it happen when the test runs alone?
4. When did it start, and what changed around then (a merge, a dependency bump, a new machine)?
5. The exact output: paste the error, or tell me where the log is.
```

Those fit a failing or flaky test. For a wrong result, what matters is the
exact input, the output they got, and the output they expected; for a crash,
the full error and what they were doing. Ask what fits the bug, not the list.

**When the user has already named the fix** ("just bump the sleep"), say in
one sentence why you're measuring first and roughly how long it'll take, then
measure. If the evidence says their fix is right (the work really does take
longer than the timeout, and should), use it and say so. Their guess isn't
wrong for being a guess; it's unproven.

Don't wait on the answers for anything you can find out yourself: if you can
reproduce it in seconds, ask and carry on. If the user is away or on their
phone, send every question at once and start on whatever doesn't need the
answers.

**Production.** The user runs every production command. Give them the exact
commands to paste (read-only ones first: logs, `ps`, status), one per block,
and say what you're looking for in the output. Anything that opens an editor
uses `vi`. Never change production state to investigate it.

## 2. Reproduce it on demand

A bug you can't trigger is a bug you can't prove fixed.

- **Baseline the gate first.** Run the project's gate before changing
  anything and note what already fails. Failures that were there before you
  started aren't yours to absorb into this fix, and without the baseline you
  can't tell them from breakage you caused.
- **Read the whole error.** The full traceback, every warning above it, the
  exit code. The line that matters is often not the last one.
- **Find the smallest trigger.** One test, one command, one input.
- **Intermittent?** Measure it before touching it: run it in a loop and count
  (`for i in $(seq 20); do <cmd> >/dev/null 2>&1 || echo fail; done | sort | uniq -c`).
  For one test inside the full suite, count that test's own outcome, not the
  suite's exit code (with pytest:
  `pytest -q -rA 2>&1 | grep -E '^(PASSED|FAILED|ERROR) tests/test_x.py::test_y'`).
  "Fails 6 in 20" is a baseline you can later prove you've changed. Then
  compare: alone versus the whole suite, your Mac versus CI, fixed order
  versus random order, idle machine versus loaded.
- **A hang gives no evidence, so make it fail instead.** Put a timeout on it
  that dumps every stack (thread or async task) when it fires; the stack names
  the wait that never returned. See *Hangs* in the techniques file.
- **Can't reproduce after real effort?** Say so, add the logging or
  watchdog that will catch it next time, and stop there. Don't fix what you
  can't see.

## 3. Narrow it down

Use whichever of these fits; most bugs fall to one or two.

- **What changed.** `git log` since the last known-good point; `git bisect`
  when there's a good and a bad commit and a command that tells them apart.
  Dependency and environment changes count (lock files, Python version, CI
  image).
- **Working versus broken.** Find the closest case that works (the same
  test alone, the previous release, the sibling function that handles the
  same thing) and list every difference, including the ones that "can't
  matter".
- **Passes alone, fails in the suite.** Either another test leaves state
  behind (pollution: find it with `scripts/find-polluter`), or load changes
  the timing (a race: force the interleaving). The techniques file covers
  both.
- **A wrong value deep in the stack.** Trace it backwards, caller by caller,
  to where it first went wrong, and fix it there, not where it surfaced.
- **Legwork.** For a long trace through unfamiliar code or history, dispatch
  `the-foundry:investigate` with the symptom, the evidence so far, and the one
  question to answer ("where does `guild_id` become None before
  `record_post`?"). It's read-only and reports back.

## 4. One hypothesis at a time

Write the hypothesis down before testing it: "I think X, because Y; if I'm
right, Z will happen when I do W." Then do the smallest thing that tells you
whether Z happens: a print, an assertion, a forced ordering, one changed
value. One variable at a time; a test that changes three things can't tell
you which one mattered.

- **Confirmed:** go to section 5.
- **Refuted:** that's progress. Cross it off, form the next one from what you
  just learned. Don't stack a second change on top of the first.
- **Out of ideas:** say "I don't know why X yet" to the user, with what's been
  ruled out. Guessing in silence is how sessions burn an afternoon.

For a hunt that runs long (past a compaction, or across sessions), keep the
hypotheses and results in
`$(git rev-parse --git-dir)/foundry-run/debug-<slug>.md`, one line each, so
nothing gets tested twice.

## 5. Pin it, then fix it

1. **A failing test that reproduces the cause, every time.** Not "sometimes,
   under load": deterministic. Force a race with events or a barrier, freeze
   or fake the clock, feed the exact bad input. Watch it fail for the reason
   you identified. A test you never saw fail proves nothing. An existing
   test that already fails every time, for exactly this reason, is the pin;
   don't write a second one.
   `implement` writes it with the fix (it works test-first), or
   `test-engineer` writes it first when the fix will take a while.
   For pollution, the pin can be a guard that fails any test leaving the
   state changed; it catches the next leak where it happens.
2. **Decide what's actually wrong.** Sometimes the code is right and the test
   is the bug: a test that raced, a fixed sleep, a budget measured in
   iterations instead of time, a test that leaks state. Then the fix belongs
   in the test, and `test-engineer` writes both the pin and the fix, not
   `implement`. The pin then looks like this: a test that forces the bad
   condition (work slower than the old sleep, the leaking test run first)
   written the old way, watched failing, then switched to the fixed way and
   watched passing.
3. **Fix the root cause, nothing else.** Dispatch `the-foundry:implement`
   (or `test-engineer`, when step 2 found the test at fault) with the
   one-sentence cause, the evidence, the failing test, and the
   instruction to change only what the cause requires. No refactoring on the
   way past.
4. **Prove it.** The pinned test passes. For an intermittent bug, the
   original trigger passes in the same loop that measured it ("30 of 30",
   against the baseline's "6 in 20"). The project's gate passes, or fails
   only where the baseline already did, and you read its real exit code
   yourself. When the cause has a documented bound (a latency range, a size
   limit), check the worst case once too, even if it's too slow to keep in
   the suite.
5. **Guard the layers it slipped through,** where that's cheap: if a bad
   value crossed three functions unnoticed, a check at the boundary where it
   entered stops the next one. Skip this when it would mean validating the
   same thing four times.

## 6. Three failed fixes: stop

If three fixes for the same bug haven't held, the next one won't either. That
pattern (each fix moves the problem, or reveals a new piece of shared state)
usually means the design is wrong, not the last line touched. Stop fixing,
and bring the user one numbered message: what was tried and why each failed,
what that suggests about the design, and two or three ways forward with a
recommendation (one of which is often "redesign this piece, here's the
smallest version").

## 7. Close it out

- **The commit body tells the story:** the symptom, the root cause, why it
  only showed up where it did, and how the test pins it. The next person to
  hit something similar will read it. If the user has a writing-style skill,
  the commit message follows it.
- **A trap others will hit** (a fixture that leaks, a runner that's slower
  than you think) goes to `the-foundry:docs` for the project's CLAUDE.md, in
  a line or two.
- **Other bugs you tripped over** on the way (a second flaky test, a
  pre-existing failure) get named with their evidence and offered as their
  own hunts, one at a time. Fixing them inside this one muddies what this
  fix proved.
- **Report to the user:** the cause in plain words, the evidence, the fix,
  the proof (the loop count and the gate's exit code), and anything left
  open. Commits and pushes follow the project's usual rules.

---

## Red flags

| Thought | What to do instead |
|---|---|
| "It's obviously the timeout; I'll bump it" | Measure how long the work takes where it fails. Then decide. |
| "It passed once after my change, so it's fixed" | Run it as many times as the baseline needed to fail. |
| "I'll add a retry and move on" | A retry hides the cause. Find it, or say you couldn't. |
| "Let me try a few changes at once" | One variable per test, or you won't know which one mattered. |
| "I'll fix it, then write the test" | Pin it first. A test written after the fix may not fail without it. |
| "The handler must be wrong" | Check the test too. Sometimes the test is the bug. |
| "One more fix will do it" (after three) | Stop and question the design with the user. |
| "I'll just ssh in and look" | The user runs production commands. Hand them the command. |
