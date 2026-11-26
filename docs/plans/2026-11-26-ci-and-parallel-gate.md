# CI for the Foundry's repo, and a gate that runs the test files side by side

- **Plan file:** `docs/plans/2026-11-26-ci-and-parallel-gate.md`
- **Source of truth:** this file. The owner picked improvements 3 and 4 on 2026-11-26 ("Do 3 and 4"). The calls are the orchestrating session's draft as amended by the architect's cold read. A small change, sized in chat; no design section.
- **Branch:** `chore/ci-and-parallel-gate`, cut from `main` at a0d4d75 (2.4.0)
- **Gate (before this change):** the five-line block in `docs/plans/2026-11-25-agent-security-rules.md`. Baseline on a0d4d75: Ran 2115, OK on both Pythons (1 and 5 skips), validates 0/0/0.
- **Gate (from this change on):** from the repo root, one line at a time, every exit read from its own echo:

```
set -o pipefail; { FOUNDRY_PYTEST_PYTHON=$HOME/dev/discord-newsbot/.venv/bin/python PYTHONDONTWRITEBYTECODE=1 python3 tests/run_tests.py; } 2>&1 | grep -E '^(FAIL|ERROR):|^Ran |^OK|^FAILED'; echo "tests exit=$?"
set -o pipefail; { PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 tests/run_tests.py; } 2>&1 | grep -E '^(FAIL|ERROR):|^Ran |^OK|^FAILED'; echo "stock python exit=$?"
claude plugin validate --strict . >/dev/null 2>&1; echo "validate exit=$?"
claude plugin validate --strict .claude-plugin/plugin.json >/dev/null 2>&1; echo "manifest exit=$?"
claude plugin validate --profile directory . >/dev/null 2>&1; echo "directory exit=$?"
```

  For this change only, the old block's two `discover` lines run as well, and each Python's `Ran` count must equal the new form's.
- **Rules for every agent:** rules 1 to 7 in `docs/plans/2026-11-25-agent-security-rules.md`'s header, word for word, plus:
  8. No Python line in any new or changed file may hold only the p-a-s-s word (the scanner test reads `tests/` too; use a docstring or `self.assertTrue(True)`), and none of the whole-environment forms `DirectoryScannerTest` lists may appear. Child processes inherit the environment by getting no `env=`.
  9. The workflow pins every action by its full commit, holds `permissions: contents: read` and nothing broader, and never references a secret or starts a model session.

## 1. Goal and Approach

The gate takes 283 s because it runs 23 test files one after another, though they share nothing. Measured on 2026-11-26: the slow tests are the ones that run git, shells and the scorer scripts (`test_big_sweep_fixture` 58 s, `test_check_parts` 55 s, `test_area_commands` 43 s, `test_directory_release` 39 s, `test_debug_pollution_procedure` 19 s); the wording and structure tests are under 25 s together. Run eight files at a time, the same 2,115 tests took 84 s, and the architect's five further runs (8, 3 and 16 at a time, both Pythons) were clean.

`tests/run_tests.py` runs each file as its own `unittest discover` process, several at a time, with the working directory and test ids exactly as `discover` sets them, and ends with the summary the gate already greps. No test is removed, skipped or rewritten.

A GitHub Actions workflow runs on macOS on every push to `main` and every pull request: the runner on `/usr/bin/python3` and on a current Python, one single-process `discover` leg (it still catches a test that leaves state behind for another file), and the three validates. It is read-only and holds no secrets.

## 2. Tasks

### Task 1: The parallel runner, the CI workflow, and the docs and tests they make untrue

**Builder:** implement. One test-engineer round follows (section 5).

**`tests/run_tests.py` (new; standard library; Python 3.9)**

- **Usage:** `python3 tests/run_tests.py [-j N | --jobs N] [--timeout S] [file ...]`. It works from any working directory: `TESTS = Path(__file__).resolve().parent`, `ROOT = TESTS.parent`.
- **Which files:** by default `sorted(TESTS.glob("test*.py"))`, run in that order. Positional arguments accept `test_x`, `test_x.py` or `tests/test_x.py`. An unknown name exits 2 with `error: no test file tests/<name>.py` on stderr. If any subfolder of `tests/` holds `__init__.py`, exit 2 with `error: tests/<dir> is a package; discover would run it and this runner does not`. No test files at all: exit 2.
- **Options** (argparse, so a bad value exits 2): `--jobs`, an int of 1 or more, default `min(8, os.cpu_count() or 1)`; `--timeout`, an int of 1 or more, seconds per file, default 900.
- **Each file runs as** `[sys.executable, "-m", "unittest", "discover", "-s", str(TESTS), "-t", str(TESTS), "-p", name + ".py", "-v"]`, with `cwd=ROOT`, `stdin=DEVNULL`, stdout to a `tempfile.TemporaryFile()`, `stderr=STDOUT`, `start_new_session=True`, and no `env=`.
- **Timeout:** SIGTERM to the process group, 5 s grace, SIGKILL, then reap. A `ThreadPoolExecutor(max_workers=jobs)`; only the main thread prints.
- **Parsing a file's output:** the last line matching `^Ran (\d+) tests? in [\d.]+s$`, and the last status line, `^(OK|FAILED)(?: \((.*)\))?$` or `^NO TESTS RAN$`. Counts for `failures`, `errors`, `skipped`, `expected failures` and `unexpected successes` come from `=(\d+)`.
- **A file is good only if** it exits 0, has a `Ran` line with n of 1 or more, and has an `OK` status. Otherwise it failed, for one of: `exit <code>`, `timed out after <S>s`, `no summary`, `no tests ran`.
- **Output to stdout, flushed:**
  - One line per file as it finishes: `module <name>: ok, <n> tests[, <k> skipped], <secs>s` or `module <name>: failed (<reason>), <n> tests, <secs>s` (no `<n> tests` when there is no `Ran` line).
  - After all files finish, for each failed file in name order: a 70-character `=` line; `module <name> output:`; its captured output without its last `Ran` line and its last status line; then, if that output holds no line starting `FAIL: ` or `ERROR: `, the line `ERROR: <name> (<reason>)`, counted as one error.
  - Then `runner: <M> test files, <J> at a time, <F> failed`.
  - Then unittest's own closing lines: a 70-character `-` line, `Ran <total> test[s] in <wall:.3f>s`, a blank line, and the status line in unittest's key order with zeros left out: `OK`, `OK (skipped=1)`, or `FAILED (failures=1, errors=2, skipped=1)`.
  - No progress line may start with `FAIL:`, `ERROR:`, `Ran `, `OK` or `FAILED`, so the gate's grep shows exactly one `Ran` line and one status line.
- **Exit codes:** 0, every file good; 1, any file failed; 2, usage error; 130, Ctrl-C, after killing every running file's process group.

**`.github/workflows/ci.yml` (new), in full:**

```yaml
# The Foundry's own gate, on GitHub's macOS machines: the tests side by side
# on the stock /usr/bin/python3 and on a current Python, once in one process,
# and the plugin validates. Read-only: no secrets, no model sessions.
name: CI

on:
  push:
    branches: [main]
  pull_request:

permissions:
  contents: read

concurrency:
  group: ci-${{ github.ref }}
  cancel-in-progress: ${{ github.event_name == 'pull_request' }}

defaults:
  run:
    shell: bash

jobs:
  tests:
    name: tests (${{ matrix.label }})
    runs-on: macos-15
    timeout-minutes: 30
    strategy:
      fail-fast: false
      matrix:
        include:
          - label: stock python, side by side
            python: stock
            how: runner
          - label: current python, side by side
            python: current
            how: runner
          - label: current python, one process
            python: current
            how: discover
    env:
      PYTHONDONTWRITEBYTECODE: "1"
      WHICH_PYTHON: ${{ matrix.python }}
      HOW: ${{ matrix.how }}
    steps:
      - name: Check out the repo with its whole history
        uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          fetch-depth: 0
          persist-credentials: false

      - name: Give the checkout a local main for the changelog tests
        run: git show-ref --verify --quiet refs/heads/main || git branch main refs/remotes/origin/main

      - name: Set up a current Python
        id: setup
        uses: actions/setup-python@6d4fd22b20465ccc0f7354476588e8df7c9ca0e0 # v7.1.0
        with:
          python-version: "3.14"

      - name: Put pytest in a venv of its own, for the debug procedure's tests
        env:
          CURRENT: ${{ steps.setup.outputs.python-path }}
        run: |
          "$CURRENT" -m venv "$RUNNER_TEMP/pytest-venv"
          "$RUNNER_TEMP/pytest-venv/bin/python" -m pip install --disable-pip-version-check --quiet pytest==9.2.0 pytest-randomly==5.1.0
          echo "FOUNDRY_PYTEST_PYTHON=$RUNNER_TEMP/pytest-venv/bin/python" >> "$GITHUB_ENV"

      - name: Pick the interpreter and show the tools the tests run
        env:
          CURRENT: ${{ steps.setup.outputs.python-path }}
        run: |
          if [ "$WHICH_PYTHON" = stock ]; then PY=/usr/bin/python3; else PY="$CURRENT"; fi
          echo "PY=$PY" >> "$GITHUB_ENV"
          "$PY" --version
          /usr/bin/python3 --version
          bash --version | head -n 1
          zsh --version
          awk --version
          git --version
          sw_vers
          if [ "$WHICH_PYTHON" = stock ]; then
            "$PY" -c 'import sys; sys.exit(0 if sys.version_info[:2] == (3, 9) else "the stock python is not 3.9, the floor the tests promise")'
          fi

      - name: Run the tests
        run: |
          if [ "$HOW" = discover ]; then
            "$PY" -m unittest discover -s tests -q
          else
            "$PY" tests/run_tests.py
          fi

  validate:
    name: plugin validate
    runs-on: macos-15
    timeout-minutes: 15
    env:
      DISABLE_UPDATES: "1"
      DISABLE_TELEMETRY: "1"
      CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC: "1"
    steps:
      - name: Check out the repo
        uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          persist-credentials: false

      - name: Set up Node for the CLI
        uses: actions/setup-node@949feb2413d6458794dcd2491c4babbbce0c15c1 # v7.1.0
        with:
          node-version: "22"

      - name: Install the Claude Code CLI
        run: npm install --global --no-fund --no-audit @anthropic-ai/claude-code@2.1.318

      - name: Validate the plugin
        run: |
          if ! command -v claude >/dev/null 2>&1; then
            echo "::error::claude is not on PATH after the install step"
            exit 1
          fi
          claude --version
          status=0
          claude plugin validate --strict . || status=1
          claude plugin validate --strict .claude-plugin/plugin.json || status=1
          claude plugin validate --profile directory . || status=1
          exit "$status"
```

**Other files:**

- `tests/test_structure.py`: `DirectoryFileRulesTest.DEV_ONLY` becomes `("tests/", "evals/", "evals-expensive/", "docs/plans/", ".github/")`. The pinned line in `test_contributing_builds_dist_without_exactly_the_dev_only_folders` ends `... docs/plans .github`.
- `tests/test_directory_release.py`: `DEV_DIRS` gains `".github"`; add `DEV_PREFIXES = tuple(d + "/" for d in DEV_DIRS)` and use it in `expected_dist_files` and `leaked` in place of the two literal tuples. `default_files` gains `".github/workflows/ci.yml": "c\n"` and a lookalike `".github-old/notes.md": "n\n"`. `test_normal_build_makes_dist_without_dev_only_folders` asserts `.github-old/notes.md` is in dist. In `RefusedGuardTest`, `.github-old/x.sh` and `.githubx/x.sh` join the lookalikes and `.github/workflows/x.sh` joins the exempt list.
- `CONTRIBUTING.md`:
  - Process step 2's block: the first line becomes `python3 tests/run_tests.py`; the three validate lines stay byte for byte.
  - After the block, add: "`tests/run_tests.py` runs each test file as its own process, the smaller of 8 and your core count at a time (`-j N` sets it, `--timeout S` the limit per file, 900 by default), and ends with the summary `unittest` prints. `python3 -m unittest discover -s tests -q` still runs the same tests in one process, which also catches a test that leaves state behind for another file. GitHub Actions runs `.github/workflows/ci.yml` on every push to `main` and every pull request: the tests on macOS on `/usr/bin/python3` and a current Python, side by side and once in one process, and the three validates. It holds no secrets and writes nothing back."
  - The file-type sentence's folder list gains `.github/`.
  - Releasing: "`main` without `tests/`, `evals/`, `evals-expensive/`, `docs/plans/`, and `.github/`", and the `git rm` line becomes `git rm -r -q -f --cached --ignore-unmatch tests evals evals-expensive docs/plans .github`. No other edit in the release section, which must keep exactly two bash blocks.
- `README.md`: in "The tests and evals." bullet, after its first sentence: "So does `.github/workflows/ci.yml`, which runs `tests/` on GitHub's machines for every push to `main` and every pull request; it never runs on yours." In the "tests itself, too" paragraph, after the first sentence: "GitHub Actions runs them on every push and pull request."
- `CHANGELOG.md`: a new `## [Unreleased]` above `## [2.4.0]`, one paragraph: the test files now run side by side (`tests/run_tests.py`, about 85 s where it took 283 s); CI runs the gate on macOS for every push to `main` and every pull request; `dist` also drops `.github/`. It must not hold the words `SWEEP IN PARTS`. No numbered entry changes; no version bump.

The builder doesn't write `tests/test_run_tests.py` or `tests/test_ci_workflow.py`; the tester does.

**Verify:**

- `PYTHONDONTWRITEBYTECODE=1 python3 tests/run_tests.py test_structure test_directory_release; echo "exit=$?"` prints exit 0, and the same with `/usr/bin/python3`.
- The new gate block prints OK twice with Ran 2115 and the validates 0/0/0.
- The old block's two `discover` lines print OK with the same `Ran` count on each Python.
- `git diff --stat main` lists only the files named here and this plan. `git diff main -- CHANGELOG.md` shows only added lines above `## [2.4.0]`.

## 3. Data / Schema Changes

None.

## 4. Risks and Coupling

- The first CI runs can only be proved on GitHub: the runner image's tools (the workflow asserts the stock Python is 3.9), pip reaching PyPI, the CLI install, and `claude plugin validate` running with no login (it exits 0 here with an empty home folder; the docs don't say). Fixes for what the first runs show go in one batch, with one ask before each push.
- `test_head_to_head`'s 2-second timing guard is the likeliest flake on a loaded 3-core runner. Not touched here; if it flakes, that is a tester's finding.
- A shallow checkout quietly weakens three tests (`test_task_brief_adversarial` reads `SKILL.md` at commit 75ad32e and drops that half of its check when the commit is missing; two changelog tests compare with `main`). Hence `fetch-depth: 0` and the step that makes a local `main`.
- The dist block is pinned by `tests/test_directory_release.py`, which runs it under bash and zsh. The only edit to it is the folder name appended to the `git rm` line, and `DEV_ONLY` must change in the same task.
- CI installs two pinned packages from PyPI into a venv of its own (pytest and pytest-randomly), so the debug procedure's tests run with no skips there: `Ran` on CI is the local count plus 1. No file in the repo imports them.
- Don't set a git identity in CI: every test that commits sets its own, and a clean runner keeps proving that.

## 5. Testing Strategy

**Runner tests (`tests/test_run_tests.py`).** Each test copies `tests/run_tests.py` into `<tmp>/tests/` beside small fixture modules and runs it with `sys.executable`; the file finishes in about 30 s. Cover:
- All good: decorator skips, a `setUpClass` SkipTest and a module-level SkipTest are counted; exit 0; the only gate-grep lines are one `Ran N tests in` line and one `OK (skipped=k)` line.
- One failing test: exit 1; `FAIL: test_a (...)` appears; exactly one `Ran` line and one `FAILED (failures=1)` line; the other files' counts are still summed.
- An import error and a syntax error: each gives an `ERROR:` line, `errors=1`, exit 1.
- A file that exits with `os._exit(3)` mid-run: `ERROR: <name> (exit 3)` or `(no summary)`.
- An empty file: `ERROR: <name> (no tests ran)`, exit 1 on both Pythons (3.9 prints `Ran 0 tests` and exits 0; 3.12 and later exit 5).
- A hang under `--timeout 2`: a test that starts `sleep 300` with inherited stdout, writes its pid to a file, then sleeps. The runner returns in under 20 s with `ERROR: <name> (timed out after 2s)`, and the sleep's pid is gone within 5 s; cleanup kills it if not.
- Parity with `discover`: the fixture has a file that imports a sibling module and a test asserting the working directory is the fixture root. The runner, run from an unrelated working directory, and `python -m unittest discover -s tests` from the root give the same `Ran`, failures, errors and skipped.
- Concurrency by handshake: two files each create a flag and wait up to 5 s for the other's; `-j 2` exits 0, `-j 1` exits 1.
- Arguments: a named subset runs only that file; `-j 0`, `--timeout 0`, an unknown file and a package folder each exit 2.

**Workflow checks (`tests/test_ci_workflow.py`).** Standard library, line-based, no YAML parser; each check is a function of the file's text with a mutation test showing it fails on a broken copy: no tabs; top-level keys exactly `name on permissions concurrency defaults jobs`; the `permissions` block is exactly `contents: read`, no other `permissions:` line, no `write` value; the `on` block's children are exactly `push` (with `branches: [main]`) and `pull_request`; none of `pull_request_target`, `workflow_run`, `secrets.`, `github.event.`, `GITHUB_TOKEN`, `claude -p`, or the plugin's e-v-a-l subcommand (`plugin eval .` and the like); every `uses:` is `owner/repo@<40 hex>`; `persist-credentials: false` once per checkout; `fetch-depth: 0` present; each job has `timeout-minutes` and a `runs-on: macos-` line; `tests/run_tests.py`, `/usr/bin/python3` and `unittest discover -s tests` are all run; a step named exactly `Install the Claude Code CLI` whose install names an exact version; each of the three `claude plugin validate` lines in CONTRIBUTING's Process block appears in the workflow.

**Then attack:** a test that prints `OK` or `Ran 5 tests in 0.1s` on a line of its own; `-v` docstring lines; the 3.9 and 3.14 status wordings; an unexpected success; a test that ignores SIGTERM; Ctrl-C; two runners at once; a test file name with an odd character. New tests run at least five times on each Python. At most three fix rounds; fixes go to implement.

## 6. Out of Scope

A Linux job (the awk line was never tried on gawk or mawk; parked). Branch protection. Splitting `test_big_sweep_fixture` or `test_check_parts` by class. Tiering or skipping any test, and any change to the wording pins (the owner is deciding that from an audit). Hashed pip installs. A version bump or release.

## Build log

Gate: the old five-line block and the new one above, both, for this change (expect: no failures, equal counts)
Branch: `chore/ci-and-parallel-gate`, from a0d4d75
Work dir: `.git/foundry-run/ci-and-test-tiers/` in the main checkout

### Progress
- Task 1: complete (from c77784f; gate exit 0 in both forms; adversarial: 100 tests in `tests/test_run_tests.py` and `tests/test_ci_workflow.py`, 4 bugs fixed in round 1/3). Final gate, read before this line was written. New form: Ran 2215, OK on python3 (1 skip), exit 0, 83 s; Ran 2215, OK on /usr/bin/python3 (5 skips), exit 0, 87 s; validates 0/0/0. Old one-process form: Ran 2215, OK, exit 0 on both (309 s and 313 s). The counts agree.
- The four bugs the adversarial round found in `tests/run_tests.py`, all fixed: a file whose tests were all skipped was failed as "no tests ran"; a test that printed its own `Ran` and `OK` lines unflushed could replace the real summary, and a failing file that printed `OK` lost its failure count (the runner now takes the last `Ran` line followed by a blank line and a status line); an ASCII stdout crashed the runner on a failed file's output; two handler bodies held only the word the scanner test forbids, which showed once the file was tracked.
- A mistake of the session's: the plan as first committed put the e-v-a-l word directly before a backtick, which fails the scanner test on the plan file itself. The builder reported it as its blocker. Reworded before the tester's round.

### Decisions made during the build
- Ruling (before Task 1): the architect's cold read stands, all seventeen points. What it changed from the session's draft: each file runs through `discover -p <file>` from the repo root, not `-m unittest <module>` from inside `tests/`, so the working directory and test ids can't differ from today's; a file that ran no tests is a failure on both Pythons; a hang is killed by process group with output captured to a file, since a pipe would block on a stray child; CI gets a third leg that runs everything in one process, to keep catching a test that leaves state behind; CI checks out the whole history and makes a local `main`, or three tests quietly check less; CI installs pinned pytest so the debug procedure's tests don't skip. If wrong: each is a line or two in one script or one workflow.
- Ruling (before Task 1): the CLI install step is filled in, not left as a placeholder. From Claude Code's setup docs (read 2026-11-26): an npm global install of `@anthropic-ai/claude-code` on Node 22 or later, with `DISABLE_UPDATES`, `DISABLE_TELEMETRY` and `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC` set. Pinned to 2.1.318, the version the local gate runs (the registry has it; newest is 2.1.332). The docs don't document `--profile` or say whether `plugin validate` needs a login; both work here, the second with an empty home folder. The job fails if either doesn't hold on the runner. The three action commits were checked against GitHub with `git ls-remote` by the session (checkout v7.0.1, setup-python v7.1.0, setup-node v7.1.0). If wrong: the validate job is red on its first run and says why.
- Stopping rule, set before the build: one builder dispatch, one test-engineer round with at most three fix rounds, the gate both ways on both Pythons. Then the owner is asked before the branch is pushed, since the workflow is only proved by running on GitHub.
- Ruling (adversarial round): a file that fails only by an unexpected success still gets the runner's `ERROR: <name> (<reason>)` line, for the gate's grep, but the line adds to the error total only when the file's own summary carries no failures, errors or unexpected successes. So the totals equal `discover`'s. A test file whose name `discover` would ignore fails the runner as "no tests ran": louder is right. If wrong: one condition in `summarize`.

### Parked
- Not asserted by any test: the runner's default `-j` and its 900 s default timeout; the workflow's matrix, env block and step order. The first CI run can only be proved on GitHub.
