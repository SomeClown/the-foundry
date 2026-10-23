---
name: ship
description: Take finished, tested work from a branch to merged, released, and deployed: the gate, push, PR, CI (including a check stuck after its run passed), merge, a local build check, the version tag, the tag's own build, deploy commands for the user to run, and the status docs afterwards. Use when work is done and the user says "ship it", "push and merge", "release it", "tag it", or "deploy", or when run-plan finishes and asks what's next. Reads the project's runbook and history for its specifics; asks before every push, merge, tag, and deploy, and never runs production commands itself.
---

# Ship

> "Real artists ship."
> — Steve Jobs, 1983, reportedly to a team that was late

This skill runs in the main session, because shipping is a string of steps
the user has to approve and one (the deploy) only the user runs. It knows the
generic shape; the project supplies the specifics. Getting the shape wrong
costs a broken release. Getting the specifics wrong costs a "manifest
unknown" at the worst possible moment.

---

## 1. Learn this project's way of shipping

Before the first ship in a session, read, in this order:

1. **The project's runbook and CLAUDE.md**: deploy docs (`docs/deploy.md`,
   `RELEASING.md`, a README "Releasing" section), the gate, version locations,
   deploy windows, the rollback.
2. **Memory notes** about this project's merge and release habits, if any.
3. **History, where the docs are silent:** `gh pr list --state merged
   --limit 5` (PRs, or straight to `main`?), `git log --merges --oneline -5`
   (merge commits or squashes?), `git tag -l | tail -5` and
   `git cat-file -t <tag>` (tags, and annotated or lightweight?),
   `ls .github/workflows` (what CI runs, and what a tag triggers).

Follow what you find, not this file's examples: if every release so far
went straight to `main` with a lightweight tag, so does this one, and the
PR, CI, and image steps below simply don't apply. If there's no runbook and
the history is thin, say what you'll do in the ask (section 3) and let the
user correct it. No written gate? Take it from the CI config, CONTRIBUTING,
or the test setup (and any validator the project's tooling has), and name it
in the ask.

**When the runbook and the history disagree** (the docs say a staging run, the
last ten releases skipped it; the docs say lightweight tags, every tag is
annotated), follow the history if it's consistent, say so in the ask, and
offer to fix the docs afterwards. The user can tell you the docs were right.

If the project deploys and has no written runbook, offer to have
`the-foundry:devops` write one after this release.

## 2. Preflight

All of this before the ask, so the ask is about shipping, not about whether
the work is ready:

- **The gate passes**, run by you from the repo root, with the real exit
  code (`set -o pipefail; { <gate>; } 2>&1 | tail -20; echo "exit=$?"`).
- **The tree is clean** and the branch has everything: `git status`,
  `git log --oneline <default>..HEAD`. In a project that commits releases
  straight to `main`, the release commit may be the work itself; then it's
  the first step in the ask, not a preflight failure.
- **For a release:** the version is bumped everywhere the project keeps it
  (grep for the old version string; packaging, a fallback constant, docs),
  and the release notes say what's in it, wherever this project keeps them
  (a CHANGELOG, a CLAUDE.md entry, the PR body). Version and changelog
  commits follow the repo's own commit style.
- **The tag doesn't exist yet,** locally or on the remote
  (`git tag -l vX.Y.Z; git ls-remote --tags origin vX.Y.Z`).
- **Prose the change made untrue:** skim the README, docstrings, and help
  text that describe what changed. A grep finds old version strings; it
  won't find "it only says hello" after you added goodbye, or "three
  skills" after you added a fourth. Check counts and lists too.
- **Anything that changes production config or data** (a migration, a new
  setting, a new secret) is named, with what the user will need to do.

If any of this fails, fix it first (through the usual agents), not during
the release.

## 3. One ask, with every step in it

Ask once, listing every outward-facing step you'll take, in order, so one
"go ahead" covers them:

```
Ready to ship v3.2.1. If you say go, I'll:
1. Push feat/x and open the PR.
2. Merge it (squash) once CI is green.
3. Build and check the image locally (Docker Desktop on, then off again).
4. Tag v3.2.1 and push the tag, then wait for the tag's image build.
5. Give you the deploy commands.
Go ahead?
```

- **A step not in the list needs its own ask.** Approval covers what was
  listed, nothing more.
- **The answer has to answer the question.** "Go ahead", "1 to 3", "yes"
  approve; a bare "Done" (to some other request) or a reaction to something
  else doesn't. When the reply is ambiguous, ask again in one line rather
  than reading it as a yes.
- **The user can cut it short:** "push and PR, I'll merge" means stop after
  step 1. Do exactly the steps approved.
- **No production step for you, ever.** For anything that runs on a server
  or a shared system, the list ends at handing over the commands. A step that
  only touches the user's own machine (refreshing a locally installed plugin
  or tool) can be yours, when the project's history shows the session doing
  it, and it's listed in the ask like everything else.

## 4. Push and open the PR

- Push the branch (`git push -u origin <branch>`).
- `gh pr create` with a title that says what ships, and a body that says what
  changed, why, how it was verified (the gate and its counts, anything the
  user checked by hand), and anything the deploy needs. If the user has a
  writing-style skill, the PR text follows it. End with any attribution the
  session's instructions require.
- **Projects that don't use PRs** (section 1) go straight to the default
  branch, in this order: switch to it, `git merge --ff-only <branch>`, run the
  gate again there, then push it (that push is the step that goes public, so
  it's in the ask). No PR, no CI wait unless the project runs CI on pushes.

## 5. Wait for CI without babysitting it

- **If the session has a PR monitor** (the Claude desktop app's PR tools),
  bind the PR to it, read its status once, and don't poll. Know what it
  reports: it wakes the session when CI *fails* (with Auto-fix on), not when
  CI passes. So if CI is still running, say so, end the turn with the merge
  as the next step, and merge when the user brings you back: read the status
  again, and merge if it's green. Waiting for a "CI passed" notice means
  waiting forever.
- **Otherwise, one background watcher**, bounded, that ends on every outcome
  (green, red, stuck, timed out), never a loop of foreground checks:
  `gh pr checks <n> --watch --fail-fast` run in the background, or a bounded
  loop on `gh pr view <n> --json mergeStateStatus`.
- **A check stuck "in progress" after its run passed.** GitHub sometimes
  leaves the check-run pending when the workflow run itself shows
  `completed success`, and the PR stays blocked. Confirm it (`gh run view
  <run-id> --json status,conclusion` says completed; `gh pr checks <n>`
  still says pending), give it a few minutes, then re-run that run
  (`gh run rerun <run-id>`), which creates a fresh check.
- **CI fails:** don't merge, don't retry blindly. A real failure goes to the
  `debug` skill; a known flake gets named as one, with its evidence, and the
  user decides whether to re-run.

## 6. Merge

- The project's way (section 1). With auto-merge turned off at the repo, a
  squash merge is `gh pr merge <n> --squash --delete-branch`.
- Then bring the local default branch up to date (`git switch <default> &&
  git pull --ff-only`) and check the version there is the one you're about to
  tag.
- A merge that isn't a release (a dependency bump, a docs fix, a test-only
  change) stops here. Say so, and skip to section 9 only if a status doc
  should change.

## 7. Check the build locally, then tag

**If the project ships an image or artifact,** build it locally before the
tag, from the merged default branch, and check it the way the project's notes
say: that it starts, imports, reports the new version, has its license files,
and whatever else runs without secrets or production config. If Docker
Desktop isn't running, start it (`open -a Docker`) and wait in the background
until `docker info` answers (an until-loop, not a foreground sleep). When
done, make sure no container is left running (`docker ps` empty) and quit it
(`osascript -e 'quit app "Docker Desktop"'`) unless the user wants it on.

**Tag** the way the project does (annotated or lightweight, `v` prefix or
not), on the merge commit, and push the tag:

```
git tag -a vX.Y.Z -m "vX.Y.Z: <what ships>"
git push origin vX.Y.Z
```

**Then wait for the tag's own build** (the image publish, the release
workflow) to finish green. A tag has no PR, so a PR monitor won't see it:
find its run (`gh run list --branch vX.Y.Z --limit 1`) and either watch it in
one background `gh run watch <id> --exit-status`, where the session's rules
allow that, or tell the user how long it usually takes and check it when they
come back. Deploy commands handed over before it finishes produce a pull of
an image that doesn't exist yet ("manifest unknown"), so the commands wait
for it.

## 8. Hand over the deploy

The user runs every production command. Give them, one per code block, in
order:

1. **Point the deploy at the new version**, the way the runbook does it. A
   one-line `sed` is the safest to paste:
   `sudo sed -i 's/^TAG=3\.2\.0$/TAG=3.2.1/' /opt/app/.env && sudo grep '^TAG=' /opt/app/.env`.
   If an editor is needed, it's `vi` (with `:set paste` before pasting a
   block), never `nano`.
2. **The deploy command** from the runbook. Mention its deploy window if it
   has one ("it refuses 09:00 to 09:15 Pacific") and check the time against it.
3. **How to check it:** the status command, and what they should see (the new
   version, "healthy", other services still up), plus a log tail.
4. **The rollback**, in one line: the previous version and the command, and
   whether anything besides the version has to be put back (config, data).
5. **What to try by hand** after it's up, if the change is visible (a
   command to run, a page to look at).

Then wait. The deploy is done when the user says it is ("deployed and
healthy"); if they paste output, read it against what you said they'd see.

## 9. Close the loop

- **Status docs:** update whatever the project keeps current (the CLAUDE.md
  status line with the version, date, and rollback; a "current plan"
  pointer; a release-notes or changelog entry if not done in preflight), and
  any memory notes that track the project's state. Commit each where it
  lives (the repo's status docs in the repo, memory notes in their own repo,
  if they're versioned). If the
  project keeps no status docs, say so in a line rather than inventing one.
- **The merged branch:** with PRs, `--delete-branch` already removed it.
  Without, delete the local branch (`git branch -d <branch>`, which refuses if
  it isn't merged) and say so; deleting a pushed remote branch is its own ask.
- **Ask before pushing those commits**, in one line ("Push both?"), unless
  the user already said to. Report what's pushed and what isn't.
- **Anything left over** (a check you skipped, a follow-up the release
  surfaced, a date something can be cleaned up) goes in the report, and into
  the project's to-do list if it keeps one.

---

## Red flags

| Thought | What to do instead |
|---|---|
| "They said go earlier, so this push is covered" | Only the listed steps are covered. Ask for the rest. |
| "'Done' probably means go ahead" | Ask again in one line. |
| "CI is slow; I'll check every minute" | Use the PR monitor, or one background watcher. |
| "The monitor will tell me when it's green" | It tells you about failures. Hand the merge back to the user's next turn. |
| "The check is stuck; I'll merge anyway" | Confirm the run passed, then re-run it. Never merge past a red or missing check. |
| "The image built in CI, so I'll skip the local check" | The local check runs before the tag, every release the project asks for it. |
| "The tag is pushed; here are the deploy commands" | Wait for the tag's build to go green first. |
| "I'll just run deploy.sh for them" | The user runs production. Hand over the commands. |
| "I'll push the status docs while I'm at it" | Ask first. |
