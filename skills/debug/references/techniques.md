# Debugging techniques

Read the one you need. Examples are Python and pytest, because that's where
most of these came from; the ideas carry to any stack.

## Contents

- Pollution: passes alone, fails in the suite
- Races: when load changes the order
- Waiting on a condition, not a clock
- Hangs: make them fail with evidence
- Tracing a bad value back to its source
- Bisecting history
- Mac versus CI versus production
- Guarding the layers

---

## Pollution: passes alone, fails in the suite

Some earlier test leaves state behind: a module-level cache, a patched
global that wasn't restored, an environment variable, a file in a shared
directory, a row in a shared database, an event loop policy.

1. Confirm the shape: the victim passes alone and fails after the full set.
   If it fails alone too, it isn't pollution.
2. Find the polluter with `scripts/find-polluter` in this skill's directory.
   It runs the victim after halves of the candidate list, keeps the half that
   still breaks it, and narrows to one file, then (with `--tests`) to one
   test:

   ```
   python3 <skill dir>/scripts/find-polluter tests/test_digest.py::test_order --python .venv/bin/python
   python3 <skill dir>/scripts/find-polluter tests/test_digest.py::test_order --tests tests/test_cache.py --python .venv/bin/python
   ```

   It assumes pytest and runs tests in the order given (it disables
   `pytest-randomly` if present). For another runner, pass `--cmd` with a
   `{tests}` placeholder. Use `--runs N` when the victim only fails some of
   the time even after the polluter.
3. Read what the polluter changes and doesn't undo. The fix usually belongs in
   the polluter (restore what it changed, use a fixture that cleans up), not
   in the victim.

If no single file breaks it, but the whole set does, it may be two tests
together, or it's load, not state: see Races.

## Races: when load changes the order

"Fails about one run in five, never alone, never in CI" is the signature of
two things that usually happen in one order and occasionally don't. A full
suite on a busy laptop is exactly the load that flips them.

1. Name the two parties and the order that breaks it: "if B posts before A
   reads 'posted today?', A takes the other branch."
2. **Force that order.** Hold each party at the critical point with an event
   or a barrier (`threading.Event`, `threading.Barrier`, `asyncio.Event`,
   `asyncio.Barrier` on 3.11+) and release them in the bad order. The race
   becomes a test that fails every time.
3. Then decide what's wrong. Either the code mishandles that order (fix the
   code), or the code is right and only the test assumed an order it can't
   guarantee (fix the test). Both happen; the second is easy to miss.
4. Prove it with repetition against the old baseline: the forced test, plus
   the original trigger in a loop ("30 of 30, was 6 in 20").

Never "fix" a race with a sleep. A sleep moves the odds; it doesn't remove
the race.

## Waiting on a condition, not a clock

A test that sleeps a fixed time and then checks is guessing how long the work
takes. A slow CI runner, a loaded laptop, or a cold cache makes the guess
wrong.

- **Poll for the condition, with a deadline:**

  ```python
  def wait_for(predicate, timeout=10.0, interval=0.01):
      deadline = time.monotonic() + timeout
      while time.monotonic() < deadline:
          if predicate():
              return
          time.sleep(interval)
      raise AssertionError(f"condition not met within {timeout}s")
  ```

  The deadline is generous because it's only reached on failure; a passing
  run returns as soon as the condition holds.
- **Budgets in time, not counts.** "Give up after 300 checks" is a time budget
  only if each check takes a known time. If the checks only yield, a fast
  machine spends 300 of them in microseconds and gives up early. Use a
  wall-clock deadline (`time.monotonic()`), or make the count huge and let a
  deadline decide.
- **Per-item timeouts on a busy runner** (a tenth of a second per server)
  are the same guess. Make them comfortably longer than the slowest
  realistic case, and put the tight bound on the whole operation if one is
  needed.
- Better still, don't wait at all: have the code under test signal when it's
  done (an event, a future, a callback) and wait on that.

## Hangs: make them fail with evidence

A hung test shows nothing, and killing it shows only the main thread parked
in `select`. Make the hang fail and print where everything was waiting:

- **Synchronous code:** `faulthandler` dumps every thread's stack after a
  timeout. In pytest, `faulthandler_timeout = 120` in the config, or
  `pytest-timeout` with `timeout_method = "thread"`.
- **Async code:** a thread's stack only shows the loop waiting. Dump the
  *tasks*: a watchdog that, after N seconds, prints
  `task.print_stack()` for every `asyncio.all_tasks(loop)`, cancels the test,
  and fails it with that dump. The stack names the `await` that never came
  back.
- **A live process:** `py-spy dump --pid <pid>` shows where a running Python
  process is stuck, without stopping it.

Once the dump names the wait, the question becomes "why did nothing ever set
that?", which is answerable.

## Tracing a bad value back to its source

The error appears where the bad value is used, which is rarely where it was
made.

1. At the point of failure, write down the bad value and where it came from
   (the argument, the attribute, the row).
2. Go one step up: who passed it? Check the value there. Repeat until you
   find the step where a good value became a bad one.
3. When the call chain is long or dynamic, instrument instead of reading:
   log the value (and `traceback.format_stack()` if needed) at each boundary
   it crosses, run once, and read where it changed.
4. Fix it at that step. A check where it surfaced only hides the next bad
   value from the same source.

## Bisecting history

When it worked at some commit and doesn't now, and a command tells good from
bad:

```
git bisect start <bad> <good>
git bisect run <command that exits 0 when good, 1 when bad>
git bisect reset
```

For an intermittent bug, the command has to repeat the trigger enough times
to be trusted (a loop that exits 1 on any failure). Exit 125 tells bisect to
skip a commit that can't be tested.

## Mac versus CI versus production

When it fails in one place only, list what differs and test the likely ones:

- Python (or runtime) version and dependency versions: compare the lock file
  with what's actually installed (`pip freeze`)
- CPU count and speed: timing bugs, and anything sized by `os.cpu_count()`
- Time zone and locale: dates, sorting, number formats
- File system: case sensitivity (macOS usually isn't), path separators, temp
  directory location
- Environment variables: colour forcing, CI flags, proxy settings, secrets
  present or absent
- Network: CI may block it, a test guard may fake it, production has it
- Data: production has years of real rows; tests have five tidy ones

## Guarding the layers

Once the cause is fixed, ask where the bad value or state *could* have been
caught: where it entered the system, where business logic accepted it, where
it was stored. A cheap check at the entry point stops the next one. Don't
validate the same thing at every layer; pick the boundary where a check is
simplest and closest to the source.
