# Directory file and front-matter rules (v2.1.0): implementation plan

*Status: approved 2026-11-06, with every recommendation in §4. The probe ran
before Task 1 and came back clean (design §2).*

- **Plan file:** `docs/plans/2026-11-06-directory-file-rules.md`
- **Source of truth:** `docs/design.md` §2, "Directory file rules (v2.1.0)". **It doesn't exist yet.** The orchestrator writes it from the owner's answers to §4's questions, and the owner approves it before Task 1 (Q3). Until then, this plan's recommendations are only proposals. Leave the approved text of §1 alone. It already says plugin agents ignore `permissionMode`, which is still true.
- **Branch:** `feat/directory-file-rules`, from `main` at 341a16f (v2.0.1).
- **Gate:** run all four and read each exit code:

  ```
  set -o pipefail; { FOUNDRY_PYTEST_PYTHON=$HOME/dev/discord-newsbot/.venv/bin/python PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q; } 2>&1 | grep -E '^(FAIL|ERROR):|^Ran |^OK|^FAILED'; echo "tests exit=$?"
  claude plugin validate --strict .; echo "validate exit=$?"
  claude plugin validate --strict .claude-plugin/plugin.json; echo "manifest exit=$?"
  claude plugin validate --profile directory .; echo "directory exit=$?"
  ```

  **Baseline, run on 341a16f on 2026-11-06:** `Ran 389 tests`, `OK`, no skips, tests exit 0; validate 0; manifest 0; directory 0. The fourth line is new in this plan. It's free, and it exits 1 on the directory checks that Claude Code can run locally. It **doesn't** run the two checks that refused 2.0.1: on a fresh clone of 341a16f it reports nothing. So it's a floor, not the probe. Use it without `--strict`, because with `--strict` it fails on the git-ignored `.DS_Store` in the working tree. `FOUNDRY_PYTEST_PYTHON` stops mattering after Task 3 deletes the last pytest-driven test. It stays in the gate so the command text doesn't change in the middle of the build.

- **Rules for every agent:**
  1. **Expected gate results.** Green after every task: `OK`, no skips, and all four exits 0. Nothing else is allowed. The test count changes: Task 3 deletes the 36 `find-polluter` tests, and Tasks 1 to 4 and 6 add a few. The orchestrator records `Ran N` per task in the build log.
  2. **Who spends money.** Only the orchestrator runs real model sessions (`claude plugin eval .` with any case, or `claude -p`), and only in Task 5, with the owner's OK. Nothing in `tests/` may start one. Validate commands are free.
  3. **Stop point.** Task 5 is a stop named by this plan. It counts as a stop under `run-plan` section 5.
  4. **No program disguised as Markdown.** Never put a program into a Markdown file as a heredoc to write out and run. Never rename code to an allowed extension. Never add a file to a shipped path (anything outside `tests/`, `evals/`, `evals-expensive/`, `docs/plans/`) unless it's Markdown, text, JSON, YAML, or PNG/JPEG/GIF/WebP/ICO. `LICENSE` and `.gitignore` are the exceptions. Never add a front-matter key other than `name`, `description`, `tools`, `model` (agents) or `name`, `description` (skills).
  5. **Scanner text.** `test_no_known_scanner_triggers` reads every tracked file, including this plan and its build log. Never put the word e-v-a-l directly before a backtick. Always write the command as `claude plugin eval .`, with the dot. No line may start with the p-a-s-s word, and that includes wrapped prose and generated Python. Also banned: an n-p-x command, passing the whole environment to a subprocess, an environment lookup by a computed name, and the icon's file name.
  6. **Exact copy.** run-plan's brief command must stay byte-exact: what it writes is the plan's text, untrimmed. Don't change its output line (`<path> (<N> lines)`), because an eval grader matches on it.
  7. **Standard library only.** No new dependencies. No agent edits anything outside this repo, and that includes `~/.claude`.
  8. **No releases here.** No push, tag, merge, or `dist` branch. Builders don't commit. The orchestrator commits with a `Task N:` subject.

### 1. Goal and Approach

**Recommendation.** Keep the repo root as the plugin folder, and keep everything in this one repo. Make the plugin itself clean: both scripts become Markdown, and `permissionMode` goes. Then let the directory read a **`dist` branch**, built from `main` at each release, that leaves out `tests/`, `evals/`, `evals-expensive/`, and `docs/plans/`. Call this **Option C**. The brief asked for A and B, and C is a third option it didn't list. It wins because it keeps the submission's path (the repo root) and changes only the branch, which the brief says is allowed when the plugin isn't under review. Nothing about installs, tests, or eval commands changes. Its cost is one scripted release step, plus a branch that must only ever be built, never edited. If the owner turns C down, I recommend A over B (comparison below).

When this is done, the Foundry is 2.1.0:

- `run-plan` copies a task with a 16-line `awk` command written in its SKILL.md and run through Bash. It's byte-identical to the old script on every content case.
- `debug` finds a polluter with a written halving procedure that ends in a required check: the victim passes alone, and fails when run right after the polluter.
- No agent carries `permissionMode`.
- A structural test fails if a shipped path ever holds a file type, or a front-matter key, that the directory refuses.
- The directory reads a 27-file `dist` tree.

**What was checked for this plan (2026-11-06, Claude Code 2.1.318, all free).** Checked:

- **The inline `awk` command:** byte-identical to `task-brief` on all 12 tasks of `docs/plans/2026-11-05-per-file-investigation.md`, under bash and zsh. Run in a scratch copy, it passes all 19 content cases in `tests/test_task_brief.py`. Only the argument-checking test (exit 2) fails, and that test retires.
- **`claude plugin eval .`** refuses an eval dir outside the plugin folder. Its exact error: `Error: --eval-dir must stay inside the plugin root (no ..)`. This is what hurts Option A.
- **The probe-branch commands below,** rehearsed in a scratch clone: they produce a 27-file tree that passes `validate --strict` and `--profile directory --strict`.
- **The widened polluted-test fixture (Task 4):** discovers 8 tests, and only the victim fails.

**The options compared** (the brief's A and B, plus C):

| | A: plugin in `plugin/` | B: tests and evals in a second repo | **C: `dist` branch (recommended)** |
|---|---|---|---|
| Submission | New one: withdraw, then resubmit with path `plugin` | Unchanged | Same repo and root path, branch `dist` (unverified that the branch can change while the entry is refused; Q2) |
| Evals | `--eval-dir` can't use `..` (checked). Every run has to copy `plugin/` and the evals into a temp folder first, the way the 1.7.6 baseline does now | Need the dev repo checked out *inside* the plugin folder, git-ignored, for `--eval-dir dev/evals` (unverified that a nested path works) | Unchanged |
| Tests | Every path constant changes (`AGENTS`, `SKILLS`, `README`, `PLUGIN`, `ORCHESTRATOR`, `CHANGELOG`, `INVESTIGATE`, `READER`, the SKILL.md paths). `evals-expensive` paths don't | All move. `ROOT` comes from an env var or `parents[2]`, and the README pins check a checkout in another repo | Unchanged, plus the new guard |
| Installs | marketplace `source` becomes `./plugin`. GitHub installs should pick it up on update (unverified). The manual-install `cp` paths change | Unchanged | Unchanged |
| README and LICENSE | Two copies: a full `plugin/README.md` and a short root README, plus a test that their install lines agree and the LICENSEs are byte-equal | One of each | One of each |
| Ongoing cost | Staging for every eval run | Two repos for every change to a skill. No atomic commits, and the gate spans two repos | One release step that builds `dist` |
| Version | 3.0.0 (the manual-install paths are "a breaking change to how the plugin installs") | 2.1.0 | 2.1.0 |

**A in more detail** (in case the owner picks it):

- Move `agents/`, `skills/`, `.claude-plugin/plugin.json` and the icon, `README.md`, `LICENSE`, `PRIVACY.md`, `docs/orchestrator.md`, and `docs/walkthrough.md` into `plugin/`. The README links to the two docs.
- Root `.claude-plugin/marketplace.json` stays, with `"source": "./plugin"`. `privacyPolicyUrl` becomes `.../blob/main/plugin/PRIVACY.md`. `test_listing_links_point_at_real_files` already checks that link.
- Root `README.md` becomes about 15 lines (what it is, the two install commands, a link to `plugin/README.md`). `LICENSE` is kept in both places. New tests: root and plugin LICENSE are byte-equal, and both READMEs carry the same `/plugin marketplace add` and `install` lines.
- `evals/README.md`, `CONTRIBUTING.md`, and every plan header get a staging prefix:

  ```
  T=$(mktemp -d); cp -R plugin/. "$T"; cp -R evals evals-expensive "$T/"; claude plugin eval "$T" ... --output-dir evals/results/<stamp>
  ```

  The validate commands become `claude plugin validate --strict plugin`.
- The owner's local install points at a local marketplace in this folder, so it should follow `./plugin` on the next update (unverified). The global `~/.claude/CLAUDE.md` line ("installed ... from `~/dev/claude/the-foundry`") stays true, so no edit is needed. Only the owner edits that file anyway.
- Existing GitHub installs keep their cached copy until `claude plugin update`. The version bump then makes the plugin manager re-read `marketplace.json` and copy from `./plugin` (expected, unverified; a scratch install would check it but changes `~/.claude`, so it's the owner's call).

**B in more detail:**

- Create `SomeClown/the-foundry-dev` (the owner creates the GitHub repo) holding `tests/`, `evals/`, `evals-expensive/`, and `docs/plans/`. The plugin repo's `.gitignore` gains `/dev/`, and the dev repo is cloned to `the-foundry/dev/`.
- In the tests, `ROOT = Path(os.environ.get("FOUNDRY_PLUGIN_ROOT") or Path(__file__).resolve().parents[2])`. `DirectoryScannerTest` and `RepoSizeLimitTest` keep running `git -C ROOT ls-files` against the plugin repo.
- Evals run as `claude plugin eval . --eval-dir dev/evals`.
- Keeping the two in step means:
  - every skill change is two commits in two repos;
  - a `run-plan` build log lives in the dev repo while its `Task N:` commits land in the plugin repo;
  - the release preflight checks both;
  - the gate holds no record of which plugin commit it tested, unless the dev repo pins a SHA.

  For a project whose tests exist to hold the repo to its own README, that's the most expensive way to keep things in sync.

**Why C isn't gaming the rule.** People who install from the directory get the `dist` folder, and every file in it is checked, which is exactly the checklist's rule. The tests and evals aren't part of what users install. That's the same split B makes, kept in one repo. The GitHub marketplace (`source: "./"` on `main`) installs `main` as it does today (Q8).

### 2. Tasks

**Before Task 1: the probe (orchestrator and owner; about 10 minutes, free).** This learns whether the guesses (the 23 files and `permissionMode`) are the whole list, and whether the portal takes a non-default branch, which C needs. The probe tree is what every option's plugin folder would hold: today's `main` minus the four dev-only folders, minus the two scripts, minus the two `permissionMode` lines. It builds without touching the working tree:

```bash
G=$(git rev-parse --git-dir); export GIT_INDEX_FILE="$G/probe-index"
git read-tree main
git rm -r -q --cached tests evals evals-expensive docs/plans skills/debug/scripts skills/run-plan/scripts
for f in agents/architect.md agents/investigate.md; do
  B=$(git show "main:$f" | grep -v '^permissionMode: plan$' | git hash-object -w --stdin)
  git update-index --cacheinfo "100644,$B,$f"
done
TREE=$(git write-tree); unset GIT_INDEX_FILE; rm -f "$G/probe-index"
git update-ref refs/heads/probe/directory-rules "$(git commit-tree "$TREE" -p main -m 'Probe: the directory file and front-matter checks (not for merging)')"
git ls-tree -r --name-only probe/directory-rules | wc -l    # expect 27
```

Then:

1. **The owner approves** `git push origin probe/directory-rules`.
2. **The owner runs Validate in the portal:** Submit new → Plugin bundle → repo `SomeClown/the-foundry`, branch `probe/directory-rules`, path the repo root → **Validate**. Don't submit.
3. **The owner pastes the findings.** If the guesses are the whole list, the report has neither `LOCAL_CODE_FILE_TYPE` nor `LOCAL_CODE_FRONTMATTER_KEY`.
   - **`LOCAL_CODE_FILE_TYPE` remains:** a file in the 27 is refused. Stop. The listing below has every one, and the likeliest are the icon, `.gitignore`, and `LICENSE`.
   - **`LOCAL_CODE_FRONTMATTER_KEY` remains:** the key isn't `permissionMode`. Build `probe/directory-rules-2` with each agent's `tools` list removed too, and validate again. If that comes back clean, the key is `tools`, and that needs a design conversation (stop).
   - **The portal won't take the branch:** C is off. Go back to Q1 with A as the recommendation.
4. After the build, the owner approves `git push origin --delete probe/directory-rules`.

The 27 files: the icon, `marketplace.json`, `plugin.json`, `.gitignore`, `CHANGELOG.md`, `CONTRIBUTING.md`, `LICENSE`, `PRIVACY.md`, `README.md`, the 10 agents, `docs/design.md`, `docs/orchestrator.md`, `docs/walkthrough.md`, 4 SKILL.md files, and `skills/debug/references/techniques.md`.

Unverified: whether a push to a non-`main` branch triggers a directory rescan.

**Then:** the owner answers §4, the orchestrator writes `docs/design.md` §2 from the answers, and the owner approves it. The task text below assumes C. If the owner picks A or B, Tasks 1 to 5 stand as written, and Task 6 is replaced by the moves sketched in §1 (for A, two tasks: the file moves with every path constant, then the staging commands across `evals/README.md`, `CONTRIBUTING.md`, and the README's manual install).

### Task 1: Drop `permissionMode` and guard the front-matter keys

**What to do.**

(a) Delete the line `permissionMode: plan` from `agents/architect.md` (line 10) and `agents/investigate.md` (line 11). Change nothing else in either file.

(b) In `tests/test_structure.py`:

- Replace `test_plan_mode_agents_are_the_ones_the_readme_names` with two tests:
  - `test_front_matter_keys_are_the_ones_the_directory_takes`: every agent's keys are a subset of `{"name", "description", "tools", "model"}`, and every skill's keys are a subset of `{"name", "description"}`. Use subtests, and name the extra key in the failure message.
  - `test_readme_says_no_agent_carries_permission_mode`: the README, with whitespace flattened, contains ``No agent carries `permissionMode` ``.
- In the module docstring, change "which agents are locked into plan mode" to "which front-matter keys the agents use".
- Keep `test_file_reader_front_matter_keys_are_exactly_the_four`.

(c) In `README.md`, replace the permission policy from ``visitor doing errands). `investigate` and `architect` also carry`` (line 93) through the end of the paragraph at line 110 with:

> visitor doing errands). No agent carries `permissionMode`. Claude Code ignores it for agents that come from a plugin, as a deliberate security rule, and the plugin directory doesn't take the key in a plugin's agent files. So all five read-only agents (investigate, file-reader, architect, qa, uiux) rest on having no edit tools plus their instructions, which so far has held; `file-reader`'s boundary is its tool list alone, since it holds `Read` and nothing else. If you want the hard block plan mode gives (it blocks mutations even through Bash), copy `agents/investigate.md` and `agents/architect.md` into `~/.claude/agents/` and add `permissionMode: plan` to each copy's front matter; your copy overrides the plugin's. That copy gets plan mode for its own tool calls only, and only when your session itself is in default or plan mode: nothing it starts inherits it, since a subagent with no `permissionMode` takes the main session's mode. A copy of `investigate` still dispatches the plugin's `the-foundry:file-reader`, which worked on the first try when tested, and its area leads (above about 150 files) are the plugin's copy, without plan mode.

In the next paragraph (lines 112 to 122), change its first sentence to begin "Plan mode, added to your own copies, doesn't block `investigate` from spawning readers (tested 2026-11-05 with the line in place, ..." and keep the rest of the sentence and the paragraph.

In "What it runs, sends, and fetches", change the parenthetical at lines 305 to 307 to: "(Plan mode can enforce that for `investigate` and `architect` if you add it to your own copies; see the permission policy above.)"

**Files.** `agents/architect.md`, `agents/investigate.md`, `tests/test_structure.py`, `README.md`.

**Verify.**

- The gate is green.
- `git grep -n permissionMode -- agents skills` prints nothing and exits 1.
- Adding `permissionMode: plan` back to `agents/architect.md` in a scratch copy makes the keys test fail; check this in memory, without committing it.

**Builder.** implement.

### Task 2: run-plan's brief becomes a command in the skill

**What to do.**

(a) In `skills/run-plan/SKILL.md`, replace lines 18 to 20 (the "Helper script..." paragraph) with:

> The brief command in step 2 of the loop copies Task N out of the plan into
> `<work dir>/task-N-brief.md` and prints its path and line count.

(b) Replace the body of `### Step 2: Write the brief` (the fenced `task-brief` call at lines 70 to 72) with the text below. Keep the following paragraph ("The brief is the task's requirements...") unchanged.

````markdown
Set three shell variables: `PLAN` (the plan file), `N` (the task number), and
`OUT` (the work dir). Then run this exactly as written, in one Bash call:

```bash
mkdir -p "$OUT"; B="$OUT/task-$N-brief.md"
awk -v n="$N" '
  { match($0, /^ */); i = RLENGTH; s = substr($0, i + 1) }
  i <= 3 && match(s, /^(`+|~+)/) {
    c = substr(s, 1, 1); k = RLENGTH; r = substr(s, k + 1)
    if (!f) { if (k >= 3 && !(c == "`" && index(r, "`"))) { f = 1; fc = c; fk = k } }
    else if (c == fc && k >= fk && r ~ /^[ \t]*$/) f = 0
  }
  !f && /^#+[ \t]/ {
    match($0, /^#+/); h = RLENGTH
    if ($0 ~ ("^#+[ \t]+Task[ \t]+" n "([^0-9]|$)")) { p = 1; ph = h; print; next }
    if (p && ($0 ~ /^#+[ \t]+Task[ \t]+[0-9]/ || h <= ph)) p = 0
  }
  p
' "$PLAN" > "$B"
if [ -s "$B" ]; then echo "$B ($(wc -l < "$B" | tr -d ' ') lines)"; else rm -f "$B"; echo "no heading for Task $N in $PLAN" >&2; false; fi
```

It copies from the task's heading (`### Task N: ...`, at any heading level) up
to the next task heading, or the next heading at the same level or higher. It
skips headings inside fenced code blocks, so a `# comment` in a code sample
doesn't end the task early. It prints the brief's path and line count, or says
there's no heading for Task N. Don't write the brief by hand, and don't trim
it: it's the plan's own text, byte for byte.
````

(c) Delete `skills/run-plan/scripts/task-brief`. The `scripts/` folder goes with it.

(d) Rewrite `tests/test_task_brief.py` so it tests the command in the SKILL.md:

- `brief_command()` reads `skills/run-plan/SKILL.md` and returns the body of the one ```` ```bash ```` block between `### Step 2: Write the brief` and `### Step 3`. It fails if there are zero blocks or more than one.
- `run_brief(plan_text, n, shell="bash")` writes the plan to a temp dir and runs `[shell, "-c", command]`. For zsh, the argv is `["zsh", "-f", "-c", command]`. Pass `env={"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "PLAN": ..., "N": ..., "OUT": ...}`, naming each variable outright (Rule 5). It returns (exit code, brief text or None, stdout, stderr), as today.
- Keep every content test from `test_literal_backtick_sample_inside_fence` through `test_prints_path_and_line_count`, with unchanged plan texts and expected values.
- Replace `test_exit_3_when_task_missing` with `test_missing_task_fails_and_writes_nothing`: non-zero exit, no file, and `no heading for Task 2` on stderr.
- Replace `test_exit_2_on_bad_arguments` with `test_missing_plan_fails_and_writes_nothing`.
- Add:
  - `test_command_is_the_one_bash_block_in_step_2`: the block contains `awk -v n="$N"`.
  - `test_real_plan_round_trip`: for tasks 1, 2, and 12 of `docs/plans/2026-11-05-per-file-investigation.md`, the brief equals the file's own slice from `### Task N:` up to the next `### Task` or `### 3.` heading, byte for byte. Task 2 holds a four-backtick block with a `# File Reader` line in it.
  - `test_same_brief_under_zsh`: skip if `shutil.which("zsh")` is None; otherwise Task 2's round trip under zsh.

(e) `evals/architect-plan-format/prompt.md`, step 3 becomes:

> 3. Load the the-foundry:run-plan skill with the Skill tool. Step 2 of its loop gives a command
>    that copies one task out of a plan. Run it on the saved plan for Task 1 and for Task 2, with
>    `./briefs` as the work directory, and show its output lines.

The graders don't change. They match `task-N-brief.md (N lines)` in the trace, and the command keeps that output.

(f) `evals/README.md` line 69: change "that run-plan's own brief script can split (checked by running the script)" to "that run-plan's own brief command can split (checked by running it)".

(g) `docs/walkthrough.md` lines 166 and 167: change "the `task-brief` script copies Task 2" to "run-plan's brief command copies Task 2".

**Files.** `skills/run-plan/SKILL.md`, `skills/run-plan/scripts/task-brief` (deleted), `tests/test_task_brief.py`, `evals/architect-plan-format/prompt.md`, `evals/README.md`, `docs/walkthrough.md`.

**Verify.**

- The gate is green.
- `python3 -m unittest tests.test_task_brief -v` shows every test passing, with the zsh test run, not skipped.
- `git ls-files skills/run-plan` lists only `SKILL.md`.

**Builder.** implement, test-first. The rewritten test file fails until the block exists.

### Task 3: debug's polluter search becomes a written procedure

**What to do.**

(a) In `skills/debug/references/techniques.md`, replace the section `## Pollution: passes alone, fails in the suite` (lines 19 to 46, up to `## Races`) with:

````markdown
## Pollution: passes alone, fails in the suite

Some earlier test leaves state behind: a module-level cache, a patched
global that wasn't restored, an environment variable, a file in a shared
directory, a row in a shared database, an event loop policy.

Find it by halving the list of tests that run before the victim. Keep notes
in the debug file (section 4 of the skill): each step's half, and whether the
victim failed, so nothing gets run twice.

1. **Confirm the shape.** The victim passes alone and fails after the full
   set, both in a fixed order. If it fails alone too, it isn't pollution.
   Turn random ordering off for every run below (`-p no:randomly` if
   pytest-randomly is installed), or the halves mean nothing.
2. **List the candidates:** the test files that run before the victim's
   file, in the order the suite runs them (`pytest --collect-only -q`, or the
   sorted `tests/test_*.py` that `unittest discover` uses).
3. **Run one half, then the victim, in one process,** in that order, and
   read the victim's own result, not the run's exit code (a candidate can
   fail by itself without touching the victim):

   ```
   pytest -q -p no:randomly -p no:cacheprovider -rA <half> tests/test_x.py::test_y 2>&1 | grep -E '^(PASSED|FAILED|ERROR) tests/test_x.py::test_y'
   python3 -m unittest -v <half, as modules> tests.test_x.XTest.test_y 2>&1 | grep -E '^test_y '
   ```

   Both runners keep the order you give them. For another runner, use its
   way of running a list of tests in a given order in one process.
4. **Keep the half that breaks it.** If the victim fails after the first
   half, keep that half. If not, run the second half the same way, and keep
   it if the victim fails. Repeat until one file is left.
   - Neither half breaks it: it takes tests from both halves together, or
     it's load, not state (see Races). Stop halving and report the list
     you've narrowed to.
   - A victim that fails only some of the time even after the polluter:
     run each check five times, and count a half as breaking it if any run
     fails.
5. **Then inside that file,** the same way, with its tests as the
   candidates (`pytest --collect-only -q <file>`, or its `Class.test_name`
   ids for unittest). If the polluter is in the victim's own file, the
   candidates are only the tests that run before the victim.
6. **The check (required).** Before you name a polluter, run these two and
   show both commands and their results:
   - the victim alone: it passes;
   - the polluter, then the victim, in one run with nothing else: the
     victim fails.
   If either doesn't hold, it isn't the polluter: go back to the last step
   that did. For a victim that fails only some of the time, run each five
   times. The second run is also the shape of the pin (skill section 5).
7. **Read what the polluter changes and doesn't undo.** The fix usually
   belongs in the polluter (restore what it changed, use a fixture that
   cleans up), not in the victim.

If no single file breaks it, but the whole set does, it may be two tests
together, or it's load, not state: see Races.
````

(b) In `skills/debug/SKILL.md`, replace the bullet at lines 106 to 109 with:

> - **Passes alone, fails in the suite.** Either another test leaves state
>   behind (pollution: halve the tests that run before it until one is left,
>   then prove it with the check under *Pollution* in the techniques file), or
>   load changes the timing (a race: force the interleaving). The techniques
>   file covers both.

(c) Delete `skills/debug/scripts/find-polluter` (the `scripts/` folder goes with it) and `tests/test_find_polluter.py`.

(d) In `tests/test_structure.py`:

- Delete `test_every_script_is_tested`.
- In `test_files_a_skill_points_at_exist`, narrow the pattern to `` `(references/[\w./-]+) `` and drop the executable and shebang branch.
- Add `test_no_skill_ships_scripts`: `list(SKILLS.glob("*/scripts"))` is empty.
- Add a class `DebugPollutionProcedureTest`:
  - The techniques file's Pollution section (from its heading up to `## Races`), with whitespace flattened, contains `**The check (required).**`, `the victim alone: it passes`, `the polluter, then the victim, in one run with nothing else`, and `not the run's exit code`.
  - The debug SKILL.md contains `the check under *Pollution* in the techniques file`.
  - A mutation test deletes each phrase from the text in memory and shows that the check then fails, as `tests/test_investigate_batch1.py` does.

(e) `README.md` line 139, the debug row: change "(with a script that bisects the suite to find it)" to "(found by halving the suite until one test is left, then proved by running it right before the victim)".

(f) `docs/walkthrough.md` line 287: replace "The skill's `find-polluter` script names the culprit:" with "Halving the suite, as the skill's techniques file lays out, names the culprit, and the check proves it (alone, the victim passes; right after the culprit, it fails):".

(g) `CONTRIBUTING.md`:

- In the gate block (line 33), drop `FOUNDRY_PYTEST_PYTHON=/path/to/a/python/with/pytest ` from the start of the command.
- Delete the sentence at lines 41 to 43 that begins "The `find-polluter` tests need a Python with pytest", through "so a release needs it set."
- In the line before it, change "`tests/` holds the scripts' tests and the structural checks" to "`tests/` holds the brief command's tests and the structural checks".

**Files.** `skills/debug/references/techniques.md`, `skills/debug/SKILL.md`, `skills/debug/scripts/find-polluter` (deleted), `tests/test_find_polluter.py` (deleted), `tests/test_structure.py`, `README.md`, `docs/walkthrough.md`, `CONTRIBUTING.md`.

**Verify.**

- The gate is green, and `Ran N` is down by about 36 from Task 2's count. Record it.
- `git ls-files | grep -c /scripts/` prints 0.
- `git grep -n find-polluter -- skills README.md docs/walkthrough.md CONTRIBUTING.md` prints nothing. The CHANGELOG's history keeps its mentions.

**Builder.** implement.

### Task 4: Make the polluted-test case exercise the procedure

**What to do.** Today the case has one candidate before the victim, so halving never happens. Do this only if the owner says yes to Q4; otherwise skip the task and log the ruling.

(a) In `evals/debug-polluted-test/scaffold.sh`, before the `cat > CLAUDE.md` block, add five innocent test files. They sort around the polluter, so it's third of six candidates (`test_a0_parse`, `test_a1_empty`, `test_a_currency`, `test_b0_total`, `test_b1_dollar_sign`, `test_b2_rounding`, then the victim):

```bash
mk() {
  printf 'import unittest\n\nfrom farm import money\n\n\nclass %s(unittest.TestCase):\n    def %s(self):\n        self.assertEqual(%s)\n' "$2" "$3" "$4" > "tests/$1.py"
}
mk test_a0_parse ParseTest test_thousands_with_cents 'money.parse_amount("1,234.50"), 1234.5'
mk test_a1_empty EmptyTest test_no_lines_total_zero 'money.invoice_total([]), 0'
mk test_b0_total TotalTest test_three_at_two 'money.invoice_total([(3, "2.00")]), 6.0'
mk test_b1_dollar_sign DollarTest test_leading_dollar 'money.parse_amount("$5"), 5.0'
mk test_b2_rounding RoundingTest test_rounds_to_cents 'money.invoice_total([(1, "0.333")]), 0.33'
```

(b) Add `evals/debug-polluted-test/graders/ran-the-check.md`:

```markdown
---
type: llm
focus: trace
---

PASS only if, before naming test_euro_invoices_show_eur as the polluter, the trace shows
test_report_header_uses_dollars run on its own and passing, and run in one command right
after test_a_currency with no other test file in that command, and failing. FAIL if either
run is missing, or comes only after the polluter was named.
```

The prompt and the other three graders don't change.

**Files.** `evals/debug-polluted-test/scaffold.sh`, `evals/debug-polluted-test/graders/ran-the-check.md` (new).

**Verify.**

- The gate is green.
- Free fixture check, from the repo root:

  ```
  T=$(mktemp -d); (cd "$T" && bash "$OLDPWD/evals/debug-polluted-test/scaffold.sh" && python3 -B -m unittest discover -s tests -v 2>&1 | grep -E '\.\.\. |^Ran|^FAILED')
  ```

  It shows 8 tests, and only `test_report_header_uses_dollars` FAILs.
- Then, in the same `$T`: `python3 -B -m unittest tests.test_c_report` exits 0, and `python3 -B -m unittest tests.test_a_currency tests.test_c_report` exits 1.

**Builder.** test-engineer. It's an eval fixture, not application code. No adversarial round; log that as a ruling.

### Task 5: Measure the changed skills (orchestrator only; a stop)

**What to do.** This needs the owner's OK on Q5 first. Run these from the repo root on the branch, with Tasks 1 to 4 committed. `--ablation none` matters: on 2.1.318 the help text says the default adds a no-plugin arm whenever the target is a path, which would double the cost (unverified in a run).

```
claude plugin eval . --tag debug --runs 2 --ablation none --scaffold --allow-tools Bash Write Edit --judge-model sonnet --threshold 0.8 --no-publish --max-cost-usd 4
claude plugin eval . --case architect-plan-format --runs 2 --ablation none --scaffold --allow-tools Bash Write Edit --judge-model sonnet --threshold 0.8 --no-publish --max-cost-usd 2
claude plugin eval . --tag run-plan --runs 2 --ablation none --scaffold --allow-tools Bash Write Edit --judge-model sonnet --threshold 0.8 --no-publish --max-cost-usd 3
```

If the owner said yes to the baseline arm in Q4, run the widened case against v2.0.1 the way `evals/README.md` builds the 1.7.6 baseline:

```
BASE="${TMPDIR:-/tmp}/foundry-baseline-2.0.1"; rm -rf "$BASE"; mkdir -p "$BASE"; git archive v2.0.1 | tar -x -C "$BASE"; rm -rf "$BASE/evals"; cp -R evals "$BASE/"
(cd "$BASE" && claude plugin eval . --case debug-polluted-test --runs 2 --ablation none --scaffold --trust-plugin --allow-tools Bash Write Edit --judge-model sonnet --threshold 0.8 --no-publish --max-cost-usd 2 --output-dir "$WORK/results/baseline-2.0.1")
```

**Cost forecast.** These are per-run figures from `evals/results/2026-10-23T18-49-13-149Z` and `...T20-12-49-655Z` (Claude Code 2.1.303, sonnet judge). 2.1.318 may differ.

| Run | Cost per run |
|---|---|
| debug tag, 6 cases | about $1.46 (polluted test $0.29, wrong total $0.25, flaky $0.33, user's fix $0.19, decisions $0.24, production $0.17). Task 4's longer fixture and trace judge add about $0.10 |
| architect-plan-format | $0.44 to $0.49 |
| run-plan tag | about $0.80 |

| Item | Forecast |
|---|---|
| debug tag × 2 | about $3.10 |
| architect-plan-format × 2 | about $0.95 |
| run-plan tag × 2 | about $1.60 |
| **Recommended set** | **about $5.65** |
| Optional baseline arm | +$0.80 |
| Ceilings (`--max-cost-usd`) | $9 total, $11 with the baseline |

**The bar.** All three commands exit 0 at `--threshold 0.8`. `ran-the-check` passes in both polluted-test runs. In both architect-plan-format runs, `brief-script-finds-task-1` and `-2` pass. A miss on any of these stops the build: the numbers go to the owner, and nothing is retuned without their OK. A miss elsewhere is triaged per `evals/README.md`'s "Reading a failure", and the ruling goes in the build log.

**Record** in the build log: each command's cost, duration, per-case scores, and every failing grader's name. The CHANGELOG's numbers come from there.

**Files.** The plan's build log only.

**Verify.** The three exit codes, read from the output, and each `aggregate-result.json`'s `costUsd`.

**Builder.** None. The orchestrator runs it and stops for the owner.

### Task 6: The file-type guard, the `dist` release step, and the docs that describe them

**What to do.**

(a) Add a class `DirectoryFileRulesTest` to `tests/test_structure.py`:

- `DEV_ONLY = ("tests/", "evals/", "evals-expensive/", "docs/plans/")`.
- `ALLOWED_SUFFIXES = {".md", ".txt", ".json", ".yaml", ".yml", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico"}`.
- `ALLOWED_NAMES = {"LICENSE", ".gitignore"}`.
- `refused(paths)` returns the paths outside `DEV_ONLY` whose suffix (lower-cased) and name are both outside the allowed sets.
- `test_shipped_files_are_types_the_directory_takes`: `refused(<git ls-files>) == []`.
- `test_refused_can_fail`: on `["skills/x/scripts/y", "agents/a.md", "tests/t.py", "x.sh"]` it returns `["skills/x/scripts/y", "x.sh"]`.
- `test_contributing_builds_dist_without_exactly_the_dev_only_folders`: `CONTRIBUTING.md` contains the line `git rm -r -q --cached tests evals evals-expensive docs/plans`, and those four names equal `DEV_ONLY` with the slashes stripped.

Change `RepoSizeLimitTest`'s docstring to "The limits the plugin directory sets, held for the whole repo so `dist` can never exceed them."

(b) In `CONTRIBUTING.md`:

- Add two lines to the gate block after `claude plugin validate .`: `claude plugin validate --strict .claude-plugin/plugin.json` and `claude plugin validate --profile directory .`.
- Change the `evals/README.md` link to `https://github.com/SomeClown/the-foundry/blob/main/evals/README.md`, since `dist` doesn't carry it.
- Add to step 2: "Nothing outside `tests/`, `evals/`, `evals-expensive/`, and `docs/plans/` may be anything but Markdown, text, JSON, YAML, or an image, and agent and skill front matter takes only the keys the plugin directory accepts; the structural tests fail otherwise."
- Add a section after "Versioning":

````markdown
## Releasing to the plugin directory

The plugin directory takes only Markdown, text, JSON, YAML, and images, so it
reads the `dist` branch: `main` without `tests/`, `evals/`, `evals-expensive/`,
and `docs/plans/`. Build it from `main` after the release is tagged, and never
edit it by hand:

```bash
G=$(git rev-parse --git-dir); export GIT_INDEX_FILE="$G/dist-index"
git read-tree main
git rm -r -q --cached tests evals evals-expensive docs/plans
TREE=$(git write-tree); unset GIT_INDEX_FILE; rm -f "$G/dist-index"
MSG="dist: $(git describe --tags --exact-match main) from $(git rev-parse --short main)"
if git rev-parse -q --verify refs/heads/dist >/dev/null; then C=$(git commit-tree "$TREE" -p dist -m "$MSG"); else C=$(git commit-tree "$TREE" -m "$MSG"); fi
git update-ref refs/heads/dist "$C"
```

Then check the tree the directory will see, and push `dist` with the release:

```bash
T=$(mktemp -d); git archive dist | tar -x -C "$T"
claude plugin validate --strict "$T"; echo "validate exit=$?"
claude plugin validate --profile directory --strict "$T"; echo "directory exit=$?"
```
````

(c) In `README.md`, "What it runs, sends, and fetches":

- Line 295: change "the Foundry is Markdown and a few small scripts. It bundles no hooks," to "the Foundry is Markdown. It bundles no scripts, no hooks,".
- Replace the "**The scripts.**" bullet (lines 353 to 360) with:

  > - **Commands the skills give your session.** `run-plan` copies each task out of the plan with one `awk` command written in the skill, and `debug` finds a test that leaves state behind by running your own test runner on halves of the suite. Both run through your session's Bash, under your permissions, and neither touches the network.

- Replace the "**The tests and evals.**" bullet (lines 361 to 366) with:

  > - **The tests and evals.** They live on the repository's `main` branch, not in the copy the plugin directory installs. `tests/` holds the repo to its own README. The `evals/` cases run only when you invoke `claude plugin eval .` yourself; their `scaffold.sh` scripts, which build small fixture repos in the harness's temporary workspace, run only if you also pass `--scaffold`, and `evals-expensive/` runs only with `--eval-dir evals-expensive`. `evals-expensive/compare.py` and `evals-expensive/sync_case.py` (Python) are run by hand, read result JSON and the case files, and stay local; the `evals-expensive/` scaffold writes a `bin/git` wrapper into its scratch fixture. None of them touches the network. Installing from this GitHub repository's own marketplace brings them along; they still run only when you run them.

- In the paragraph at line 392, change "`tests/` checks the skills' scripts and holds" to "`tests/` checks run-plan's brief command and holds".

(d) In `PRIVACY.md`:

- Change lines 5 and 6, "It's Markdown instructions for Claude Code, a few small scripts that run on your machine, and their tests.", to "It's Markdown instructions for Claude Code. The repository's `main` branch also holds its tests and eval cases, which run only when you run them."
- Change the paragraph at lines 32 to 35 to begin "The skills ship no scripts: `run-plan` and `debug` give your session commands that run through its own Bash. On the `main` branch, `evals-expensive/compare.py` and", and keep the rest.

**Files.** `tests/test_structure.py`, `CONTRIBUTING.md`, `README.md`, `PRIVACY.md`.

**Verify.**

- The gate is green.
- Rehearse the release step in a scratch clone, never in this repo:

  ```
  S=$(mktemp -d); git clone -q . "$S/c"; cd "$S/c"; git tag v0.0.0-rehearsal
  ```

  Then run CONTRIBUTING's two blocks as written. Both validate lines print `exit=0`, and `git ls-tree -r --name-only dist | wc -l` prints 27.

**Builder.** implement.

### Task 7: Version 2.1.0 and the CHANGELOG

**What to do.**

- Set `.claude-plugin/plugin.json` `version` to `2.1.0`.
- Add `## [2.1.0] — <date>` to `CHANGELOG.md`:
  - **Changed:** run-plan's brief is a command written in the skill. debug's polluter search is a written procedure that ends in a required check. `architect` and `investigate` no longer carry `permissionMode: plan`; it never applied in a plugin install, and a manual install that wants it adds the line to its own copies (README).
  - **Added:** the structural guards for file types and front-matter keys, and the `dist` branch the plugin directory reads.
  - **Removed:** `find-polluter`, `task-brief`, and their tests.
  - **Measured:** Task 5's numbers, copied from the build log, never from memory.

  Say why: the plugin directory refused 2.0.1 on its file-type and front-matter checks.

**Files.** `.claude-plugin/plugin.json`, `CHANGELOG.md`.

**Verify.** The gate is green, and `test_version_matches_the_newest_changelog_entry` passes.

**Builder.** implement.

**After Task 7:** the qa pass, fix batches, and docs, as `run-plan` section 4 lays out. Docs adds the `### As built` subsection to §2. Then `ship` with one ask. The owner approves each step:

1. Fast-forward `main`, and tag `v2.1.0`.
2. Build `dist` per CONTRIBUTING and validate its export.
3. Push `main`, the tag, and `dist`, and create the GitHub Release.
4. In the portal, Validate on branch `dist`, then point the submission at `dist`. If the portal won't change the branch, withdraw and resubmit with the same repo, the root path, and branch `dist`.
5. Delete the probe branch on origin.

### 3. Data / Schema Changes

No data or schema changes. There's one new piece of repo state: the `dist` branch, created at release time by the commands in CONTRIBUTING (Task 6), with each commit's parent the previous `dist` commit. Its first commit has no parent, so `dist` carries no dev-only history. Plus a throwaway `probe/directory-rules` branch before Task 1, deleted after.

### 4. Risks and Coupling

**Owner questions** (recommendation first):

1. **Where the dev-only files go.** **C, the `dist` branch** (recommended); A, the `plugin/` subfolder; B, a second repo. If C is ruled out (the probe or the portal says no), I recommend A.
2. **The probe.** **Yes:** push `probe/directory-rules`, Validate in the portal, delete the branch afterwards. Also check whether the refused entry's branch can be changed now, or whether it needs a withdraw-and-resubmit (unverified either way).
3. **A design section first.** **Yes:** a short `docs/design.md` §2, written by the orchestrator from these answers, approved before Task 1. The repo's practice is design, then plan. No full brainstorm round is needed, because these questions are the open choices.
4. **The debug measurement.** **Widen the fixture and add `ran-the-check`** (Task 4), and **run a v2.0.1 baseline on it** (+$0.80), so "no worse than the script" is a measurement, not a guess. Or keep the case as it is and only re-run it.
5. **Eval spend.** **About $5.65 forecast** (Task 5), capped at $9, or $11 with the baseline arm.
6. **Version.** **2.1.0** under C or B; 3.0.0 under A.
7. **`permissionMode`.** **Drop it**, and have the README tell manual-install users to add it to their own copies. Or keep it and see whether the probe passes without dropping it (it can't: the probe drops it).
8. **GitHub marketplace source.** **Keep `"./"` on `main`.** Installs from the repo stay as today, including the owner's local install, which reads the working folder. Or point it at `dist` with a GitHub source and ref, which gives GitHub installs the clean tree but makes the owner's local install fetch from GitHub.
9. **Non-blocking warnings.** **Leave them**, except what the move fixes anyway:
   - The credential warning on `tests/test_head_to_head.py`, the image warning on `tests/test_structure.py`, and the registry-redirect line in `docs/plans/` all leave the shipped tree under C (and under A).
   - The README's download-and-run command is unverified, but it's most likely the install commands, which users need.
   - The `plugin.json` credential warning has no visible cause, since the file holds no credential.
   - The listing fields need nothing.
   - If the probe report names a line, revisit then.

**Risks:**

- **The guesses may be incomplete.** The portal named neither the files nor the key. The probe settles this before any code changes.
- **A reviewer may read the 16-line `awk` block as a program disguised in Markdown.** It's run directly, and it's shorter and plainer than the script. Skills that give the session commands to run are normal, and run-plan already gives `git` blocks. If the directory objects anyway, the fallback is a plain-English copy rule, which the orchestrator ruled out for exactness. That would need the owner.
- **Halving by hand costs turns.** About log2(n) runs per level, against one script call, and it loses the script's niceties: JUnit-based reading of the victim's result, and absolute node ids. The procedure keeps the one that mattered most (read the victim's own result, not the exit code). Task 5 measures the rest.
- **`dist` drift.** `dist` is only ever built from `main` by CONTRIBUTING's commands, and a test pins the four excluded folders to those commands. Releases gain one step, which the owner approves like any push.
- **Unverified platform behavior:**
  - which branch's pushes trigger a rescan;
  - whether the portal's Validate takes a non-default branch (the probe answers this);
  - A's marketplace update path;
  - B's nested `--eval-dir`;
  - eval costs on 2.1.318.
- **Shared files.** `tests/test_structure.py` changes in Tasks 1, 3, and 6, `README.md` in Tasks 1, 3, and 6, and `CONTRIBUTING.md` in Tasks 3 and 6. They run strictly in order with one writer, so nothing conflicts, but each builder should re-read the file rather than trust an earlier diff. Between Task 2 and Task 6, the README's "What it runs" still names the scripts. No test pins that text, and Task 6 fixes it.
- **This plan's own text** is read by the scanner test (Rule 5) and by run-plan's extractor. Every embedded block that contains a three-backtick fence sits inside a four-backtick one.

### 5. Testing Strategy

- **Task 1:** unit tests on front-matter keys for every agent and skill, and a README pin. Adversarial round: a key added to a skill, a `tools` list emptied, `permissionMode` in a new agent file.
- **Task 2:** the command's own tests, run from the SKILL.md text: every fence case from the old suite, missing task and missing plan, the output line, a byte-exact round trip on a real plan with nested fences, and zsh. Adversarial round: CRLF line endings, a `Task 1` heading inside a tilde fence that's never closed, `N=0`, a plan path with spaces, and an `OUT` that doesn't exist yet.
- **Task 3:** pins on the procedure's required phrases, with mutation tests. The behavior is measured by evals, not unit tests.
- **Task 4:** the free fixture check in Verify. The behavior is measured in Task 5.
- **Task 5:** paid behavior evals, against the bar.
- **Task 6:** the file-type guard, with a test that shows it can fail, and the CONTRIBUTING pin. The release commands are rehearsed in a scratch clone.
- **Task 7:** the existing version and CHANGELOG test.

### 6. Out of Scope

- Rewording `docs/design.md` §1. It's an approved record, and §2 supersedes it on `permissionMode`.
- Editing CHANGELOG history that mentions the old scripts.
- Fixing `evals/README.md`'s routine commands to pass `--ablation none`, beyond the commands in Task 5. That's worth a follow-up if 2.1.318 really does default to two arms.
- Any change to `ship` to teach it about `dist` in general. This repo's release step lives in its own CONTRIBUTING, which `ship` already reads.
- Editing `~/.claude/CLAUDE.md`. That's the owner's file; under C it needs no change.
- Applying to become a Verified organization. There's no way to apply.
- The README's install commands and the `plugin.json` credential warning (Q9).

## Build log

Gate: the four commands in this plan's header (expect: `OK`, no skips, all four exits 0)
Branch: feat/directory-file-rules, from 341a16f
Work dir: `.git/foundry-run/2026-11-06-directory-file-rules/`

### Before Task 1

- Probe: `probe/directory-rules` at 7bc9414 (the 27-file tree), pushed with the owner's OK (Q2). The portal's Validate on it, without submitting, came back clean of both blocking rules and took the branch. A control on `main` at 341a16f flagged both, naming `evals-expensive/compare.py` and `agents/architect.md · permissionMode`. The probe branch stays on origin until after the build.
- Owner (2026-11-06): every §4 recommendation; design §2 approved.

### Progress

- Task 1: complete (from 67080af; gate exit 0, Ran 425, all four exits 0; adversarial: 35 tests, 7 parser bugs fixed in round 1)
- Task 2: complete (from 90ebe00; gate exit 0, Ran 475, all four exits 0; spec check: no gaps; adversarial: 47 tests, 2 bugs fixed in round 1; byte-identical to the old script on 19 of 19 tasks, bash and zsh)
- Task 3: complete (from 4430bea; gate exit 0, Ran 464, all four exits 0; adversarial: 21 tests, the procedure's commands checked against the real fixture under unittest and pytest, 4 weak pins fixed in round 1)
- Task 4: complete (from d8e5739; gate exit 0, Ran 464, all four exits 0; fixture check: 8 tests, only the victim fails, alone exit 0, pair exit 1; no adversarial round, per the plan)
- Task 6: complete (from d72b2b3 after Task 5's commits; gate exit 0, Ran 506, all four exits 0; adversarial: 30 tests, guard held, 7 release-command bugs fixed in round 1; rehearsed in a scratch clone by the orchestrator: dist 27 files, both validates exit 0)
- Task 7: complete (from 3ca38fe; gate exit 0, Ran 506, all four exits 0; CHANGELOG numbers checked against this log by the orchestrator; one overclaiming phrase fixed in round 1; no adversarial round)
- Task 5: complete after fix batch 1 (bar met on 39ca705 for `debug-polluted-test`, the case that missed; see below). Owner OK'd the runs (2026-11-06). The first try missed the bar, and the run stopped for the owner. Results of that first try:
  - First try of the three branch commands refused to start (`not a trusted plugin directory`; the plan's commands lacked `--trust-plugin`), $0. Re-run with the flag.
  - debug tag × 2: exit 1, $3.03, 501 s. debug-polluted-test 0.75 (`ran-the-check` FAIL in both runs, votes FAIL FAIL FAIL and FAIL PASS FAIL; `fixed-the-polluter`, `right-cause`, `victim-untouched` passed in both). debug-production-report 0.83 (`asks-and-hands-over` failed run 2). The other four cases 1.00.
  - architect-plan-format × 2: exit 0, $1.02, 184 s, 1.00 in both runs (both brief graders passed).
  - run-plan tag × 2: exit 0, $1.03, 193 s. run-plan-decisions 0.93 (`item-d` failed run 2), run-plan-resume 1.00.
  - v2.0.1 baseline, widened debug-polluted-test × 2: $0.96, 124 s, 0.63. `ran-the-check` passed run 1 (PASS FAIL PASS), failed run 2; `victim-untouched` failed both (Edit called 1x).
  - Total spent: $6.04 of the $11 cap. The result files hold no judge reasons, and the runs kept no traces (no `--keep-temp`).
  - Re-run with traces (owner's OK): debug-polluted-test × 2 with `--keep-temp`, $0.87, 118 s, 1.00 in both (`ran-the-check` votes FAIL PASS PASS and PASS PASS PASS). Total now $6.91.
  - What the traces show: both runs ran the victim alone (passed) and `tests.test_a_currency tests.test_c_report` as a process of its own (failed) before the root-cause write-up. Run 1 paired each of the 7 other files with the victim in one Bash loop instead of halving, then said "Exactly one module poisons it: `test_a_currency`" before its labeled pin run. Run 2 halved in groups of three. Neither ran the check as two standalone, labeled commands. So the split votes come from the grader's form, not a missing check: "in one command right after test_a_currency with no other test file in that command" reads one way for a loop of separate processes, and "before naming" reads one way for an interim conclusion.

### Decisions made during the build

- Ruling (Task 1): all 7 failing adversarial tests in `tests/test_front_matter_rules.py` are real bugs in the test parser, not misreads. Two are bypasses of the keys guard (`permissionMode : plan`, a quoted key), both valid YAML; the other five (an underscore-led key, a single-quoted value, an unterminated quote) are YAML behavior the parser gets wrong. If wrong: a stricter parser than the files need, at no cost to the shipped plugin.
- Ruling (Task 1): the README sentence saying `qa`, `uiux`, and `file-reader` don't carry plan mode goes with the replaced paragraph. Why: no agent carries it now, and the new text says so. If wrong: one sentence to restore.

- Ruling (Task 1): fold in the probe's "Frontmatter value may be misread" note (5 findings: `agents/architect.md`, `agents/file-reader.md`, `agents/investigate.md`, `agents/uiux.md`, `skills/ship/SKILL.md`) by double-quoting each `description` value. Why: Task 1 already edits agent front matter, and the fix is mechanical. If wrong: a front-matter parser in the tests that doesn't strip quotes, caught by the gate.

- Ruling (Task 2): `test_non_numeric_n_is_rejected` (3 subtests) and `test_empty_n_is_rejected` are real bugs: N reaches the awk regex unchecked, so `1|2`, `.`, `[0-9]`, or an empty N writes a brief for the wrong task and exits 0, where the old script exited 2. The fix adds an N check to the command, a change to the plan's exact block. If wrong: one line in the skill's command.
- Ruling (Task 2): three behaviors the command shares with the old script stay as they are, pinned by passing tests: a CRLF closing fence never closes, an unterminated last line gains a newline, and a heading inside an HTML comment counts. Why: the old script promised none of them, and no plan here has them. If wrong: a brief with one extra byte, or one cut early by an HTML-commented heading.

- Ruling (Task 3): the builder also cut the `find-polluter` and `task-brief` sentences from README's "The scripts." bullet, beyond its brief. Accepted: Task 6 replaces that bullet whole, and its builder matches on the current text. If wrong: nothing, since Task 6 rewrites it.

- Ruling (Task 3): the four green mutations in `PinMutationTest` are real gaps in the pins, not misread tests: the design's anti-goal is naming a polluter without the check, so the pins must hold the check's position (before naming, and before step 7), and the unittest line with its victim grep. The builder that wrote the pins fixes them. If wrong: stronger pins than needed, at no cost to the shipped text.
- Ruling (Task 3): step 3's pytest example `tests/test_x.py::test_y` gets a few words saying it stands for the victim's full id, `Class::test` included, from the adversarial round's wording note. If wrong: a few words.

- Ruling (Task 4): no adversarial round on the fixture, as the plan says. Why: it's an eval fixture, checked by the free run in Verify and by `tests/test_debug_pollution_procedure.py` against it (21 tests OK). If wrong: a fixture flaw shows up as a Task 5 grader miss instead.

- Ruling (Task 6): all 7 failing release tests in `tests/test_directory_release.py` are real bugs: CONTRIBUTING's dist block checks nothing between steps, so an untagged main, a tag behind main, no main, a missing dev folder, a run from a subfolder, or a dist only on origin each writes a wrong dist commit and exits 0. If wrong: a stricter release step than needed.
- Ruling (Task 6): `.svg` stays refused by the guard. Why: the portal's refusal lists Markdown, text, JSON, YAML, and PNG/JPEG/GIF/WebP/ICO, not SVG, though the older checklist calls SVG text. If wrong: an SVG would need adding to the allowed set before it could ship.

- Ruling (Task 7): no adversarial round on the version bump and CHANGELOG. Why: `test_version_matches_the_newest_changelog_entry` covers the contract, and the orchestrator checked every number against this log. If wrong: a CHANGELOG error that qa should catch.

- Ruling (Task 5, from qa lens 1's triage): `asks-and-hands-over` (debug-production-report, run 2) is unrelated to this branch: the grader checks debug's first reply to a production report, which this branch didn't touch, and it also failed in the kept 2026-10-23 run (case 0.67). A known flaky formatting grader. If wrong: a production-report regression shipped unnoticed.
- Ruling (Task 5, from qa lens 1's triage): `item-d` (run-plan-decisions, run 2) is most likely variance: the case allows only Skill and Read in 4 turns, so the brief command never runs, and the section it tests (run-plan's red flags and rulings) didn't change; it passed 2/2 on 2026-10-23. Unconfirmed, since no trace was kept. If wrong: run-plan's longer skill text shifted one ruling.

### From Task 5 (fix batch 1)

- Owner (2026-11-06): "Both, then re-run": the procedure makes the check visible, and the grader judges it by substance.
- Procedure (the Task 3 builder): step 4 says what halving leaves is a suspect until step 6 holds; step 6 runs its two checks as commands of their own. Pins added, including the suspect sentence's place in step 4.
- Grader and tests (test-engineer): `ran-the-check` now passes a loop that starts each run as its own process, and doesn't count "suspect" as naming. Mutation tests match on flattened whitespace, so a rewrap doesn't break them.
- Gate: exit 0, Ran 473, all four exits 0.
- Re-run on 39ca705 with traces: debug-polluted-test × 2, $0.89, 125 s, 1.00 in both, `ran-the-check` PASS PASS PASS in both. The bar is met. Total Task 5 spend: $7.80 of the $11 cap.
- What the traces show: the grader's change is what moved the votes. The procedure's new form didn't visibly take: neither run called the result a suspect in its text. Run 1 halved once (`--- halves`, first half failed, second passed) before pairing, and run 2 didn't halve. Run 2 paired each candidate with the victim in one loop, then ran the pair as a command of its own; run 1 ran the victim alone and checked the shared state in process. Both still found the right polluter and cause and left the victim alone.
- Ruling: the bar is met, so the build goes on to Task 6, with the finding above carried into the CHANGELOG's Measured notes. Why: the measured outcome (right polluter, right cause, victim untouched, check in substance) holds in 4 of the last 4 runs; how closely agents follow the procedure's form is a separate question. If wrong: a reviewer reading a trace sees a linear search where the skill says halve.
- Ruling: one mutation stays green: a loosening suffix after a pinned phrase ("or alongside other runs, if you like"). The pins are substring checks, and catching every rewording would mean pinning whole sentences. If wrong: a weakened step 6 that only a reviewer would catch.

### From the qa pass

Two read-only qa reviewers on b60dcaf: lens 1 (spec and directory compliance) and lens 2 (correctness, tests, docs truth). Lens 1: 4 medium (2 for the owner), 5 low. Lens 2: 1 high, 6 medium, 8 low. Both confirmed the 27-file `dist` and every CHANGELOG figure.

- Fix batch 1 (release block, CONTRIBUTING and evals/README): lens 2's HIGH (a stale local `main` on an old tag builds the refused 2.0.1 tree, and the export validate can't see either rule that refused it); `git rm --cached` failing from a branch that changed a dev-only file; the `dist` parent taken without a fetch; CONTRIBUTING's validate without `--strict`; the routine eval commands without `--trust-plugin`; the evals/README debug row missing `ran-the-check`. Test findings folded into its adversarial round: release tests that pass without a `dist`, ignored return codes, zsh dropped without a skip, the feature-branch test not touching a dev-only folder.
- Fix batch 2 (run-plan brief command, debug procedure, docs truth): the brief command trusting a non-empty file (noclobber keeps a stale brief, awk failing mid-file under a UTF-8 locale), no guard on unset `PLAN`/`OUT`, step 2's wording on where the variables go (both lenses); the unittest grep matching the wrong `test_y`; README's "bundles no scripts" (both lenses); three CHANGELOG phrases ("neither halved", "and their tests", "the bar was met" unscoped); the `.gitignore` comment. Test findings folded into its adversarial round: the hardcoded private venv (3 skips elsewhere, and the name in a public repo), `tests.` imports that need the repo root as cwd, the tautological mutation test, the unset-OUT test passing only because `/` is read-only, `test_no_skill_ships_scripts` reading the filesystem instead of git, plus a noclobber test and a UTF-8 locale test.
- Ruling (fix batch 1): both failing adversarial tests are real bugs. A quoted key (`"permissionMode": plan`) slips past the front-matter check, which is the hole the check exists for; a valid key with a space before the colon (`name : a`) stops the build, which is a false stop on valid YAML. If wrong: one test to delete.
- Ruling (fix batch 1): the block stops when an unpushed local `dist` from a failed export validate exists, rather than building over it. Kept, and CONTRIBUTING says to delete the local `dist` and build again. Why: an unpushed `dist` commit that failed validation shouldn't become the next one's parent. If wrong: one extra command at release.
- Parked (fix batch 1): the version read takes the last `"version"` on a line, so a one-line `plugin.json` with a nested version would read wrong (ours is pretty-printed); several tags on one `main` commit; agents in subfolders; front matter with no closing `---`. None occurs in this repo, and `DirectoryFileRulesTest` covers the working tree at every commit.
- Fix batch 1: complete (from b60dcaf; gate exit 0, Ran 531, all four exits 0; adversarial: release tests rewritten to 55 with a local bare origin in every fixture, 2 front-matter bugs fixed in round 1; the module now takes ~37 s of a ~47 s suite)
- Done by the orchestrator: the triage rulings above; the build log's self-contradicting Task 5 line and its "neither halved".
- To the docs task: design §2's intro reads as present tense (two scripts, two agents with `permissionMode`), and it names a plan path `dist` won't hold (lens 1, 8). The "As built" subsection records both.
- For the owner, not fixed: a free portal Validate on the exact tree before tagging (lens 1, 2); restoring descriptive names and comments in the awk block (lens 1, 4); a ~$0.50 traced re-run of `item-d`.
- Closed: both parked items (README's "The scripts." bullet was replaced in Task 6; the `brief-script-finds-task-*` grader names stay for continuity with older results).

### Parked

- Task 2 (spec check): README's "The scripts." bullet still names `skills/run-plan/scripts/task-brief` until Task 6 replaces it, as planned. Task 6's builder is told to confirm it.
- Task 2 (spec check): the grader files `brief-script-finds-task-1.md` and `-2.md` keep "script" in their names; the brief says graders don't change, and nothing else names them.
