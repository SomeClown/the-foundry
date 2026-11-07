# Contributing

> "Talk is cheap. Show me the code."
> — Linus Torvalds, saving code reviewers a paragraph since 2000

Improvements are welcome. The bar is simple: a change should make the team
better for people who aren't you. Repo-specific tweaks (your stack, your
deploy quirks, your strong feelings about tabs) belong in your own fork or in
per-project agent overrides — that's what `.claude/agents/` shadowing is for.

## What makes a good contribution

- **Battle-tested changes.** The best PRs read like "this agent kept doing X
  on real projects; this wording stops it." Include the failure you observed.
  Prompt engineering by vibes is how these files got long everywhere else.
- **Tighter, not looser, permissions.** Proposals to add tools to an agent's
  allowlist need a concrete job that can't be done without them. Proposals to
  remove tools get a friendlier reception.
- **Stack-agnostic wording.** The agents read the project's own files to learn
  the stack. A change that assumes everyone uses your framework will be asked
  to generalize.
- **Shorter is better.** Every line of an agent definition is loaded on every
  spawn, forever. A PR that deletes instructions while preserving behavior is
  the most valuable kind there is.

## Process

1. Fork, branch, make the change.
2. Test it: run the affected agent or skill on a real task in a real
   project. "It reads nicely" is not testing; neither of us can review a
   prompt by staring at it. Then run the gate:
   ```bash
   python3 -m unittest discover -s tests -q
   claude plugin validate --strict .
   claude plugin validate --strict .claude-plugin/plugin.json
   claude plugin validate --profile directory .
   ```
   A change to `investigate` or `file-reader` also gets the nesting smoke
   case, and the head-to-head in `evals-expensive/` with the owner's OK,
   since it costs real money.
   `tests/test_debug_pollution_procedure.py` runs debug's procedure against its
   fixture under pytest as well as unittest. It looks for an interpreter with
   pytest in `FOUNDRY_PYTEST_PYTHON`, then the one running the tests, then the
   `pytest` on your `PATH`; with none, those tests skip, and the skip reason
   names the variable. Set it to a venv's `python` for a green run with no skips.
   `tests/` holds the brief command's tests and the structural checks (the README's
   promises about who can write, which model each agent runs, and how many
   skills there are, against the actual files). Nothing outside `tests/`,
   `evals/`, `evals-expensive/`, and `docs/plans/` may be anything but Markdown,
   text, JSON, YAML, or an image, and agent and skill front matter takes only
   the keys the plugin directory accepts; the structural tests fail otherwise.
3. If you changed what a skill does, run its behavior cases:
   `claude plugin eval . --tag <skill> --scaffold --trust-plugin --allow-tools Bash Write Edit --judge-model sonnet --threshold 0.8 --no-publish`.
   A new behavior worth keeping gets a case of its own. See
   [evals/README.md](https://github.com/SomeClown/the-foundry/blob/main/evals/README.md) for how to read a failure and how a
   case is built.
4. Update the [CHANGELOG](CHANGELOG.md) under an Unreleased heading.
5. Open a PR describing what behavior changed and how you verified it.

## Versioning

Semver-ish, applied to prompt files with a straight face:

- **Major** — restructuring the team: agents added/removed/renamed, or a
  breaking change to how the plugin installs.
- **Minor** — behavior changes to one or more agents, new docs, new
  capabilities.
- **Patch** — typos, clarifications, and wording fixes that don't change
  behavior.

The `version` field in `.claude-plugin/plugin.json` is what triggers plugin
updates for installed users, so it gets bumped on every release, and the
[CHANGELOG](CHANGELOG.md) says what they're getting. Each release also gets
a `vX.Y.Z` tag and a GitHub Release with that version's CHANGELOG entry as
its notes, so the repo page shows what's current instead of whatever
version last remembered to announce itself.

## Releasing to the plugin directory

The plugin directory takes only Markdown, text, JSON, YAML, and images, so it
reads the `dist` branch: `main` without `tests/`, `evals/`, `evals-expensive/`,
and `docs/plans/`. Build it from `main` after the release is tagged, and never
edit it by hand:

```bash
(
set -e
cd "$(git rev-parse --show-toplevel)"
die() { echo "error: $*" >&2; exit 1; }
git fetch -q origin || die "git fetch origin failed"
TAG=$(git describe --tags --exact-match main 2>/dev/null) || die "need a local main with a tag exactly on it"
VER=$(git show main:.claude-plugin/plugin.json | sed -n 's/.*"version"[^"]*"\([^"]*\)".*/\1/p' | head -n 1)
[ "$TAG" = "v$VER" ] || die "main is tagged $TAG but its plugin.json says version $VER"
git merge-base --is-ancestor origin/main main || die "origin/main is not an ancestor of local main"
export GIT_INDEX_FILE="$(git rev-parse --absolute-git-dir)/dist-index"; trap 'rm -f "$GIT_INDEX_FILE"' EXIT
git read-tree main
git rm -r -q -f --cached --ignore-unmatch tests evals evals-expensive docs/plans
TREE=$(git write-tree); MSG="dist: $TAG from $(git rev-parse --short main)"
BAD=$(git ls-tree -r --name-only "$TREE" | awk '{n=$0; sub(/.*\//,"",n)} n=="LICENSE" || n==".gitignore" {next} tolower($0) !~ /[^\/]\.(md|txt|json|yaml|yml|png|jpg|jpeg|gif|webp|ico)$/')
[ -z "$BAD" ] || die "the directory refuses these files in the built tree: $BAD"
BAD=$(git ls-tree -r --name-only "$TREE" | grep -E '^(agents/[^/]+|skills/[^/]+/SKILL)\.md$' | while read -r P; do
  OK="name description"; [ "${P#agents/}" = "$P" ] || OK="name description tools model"
  git show "${TREE}:$P" | awk -v ok="$OK" -v p="$P" 'BEGIN {split(ok, a, " "); for (i in a) k[a[i]] = 1} /^---[ \t\r]*$/ {if (++d == 2) exit; next} d == 1 && /^[^ \t#-][^:]*:/ {key = $0; sub(/:.*/, "", key); gsub(/^[ \t\r]+|[ \t\r]+$/, "", key); if (key ~ /^\042.*\042$/ || key ~ /^\047.*\047$/) key = substr(key, 2, length(key) - 2); if (!(key in k)) print p ": " key}'
done)
[ -z "$BAD" ] || die "front-matter keys the directory refuses: $BAD"
DIST=$(git rev-parse -q --verify refs/heads/dist || true); REMOTE=$(git rev-parse -q --verify refs/remotes/origin/dist || true)
if [ -n "$REMOTE" ]; then
  [ -z "$DIST" ] || git merge-base --is-ancestor "$DIST" "$REMOTE" || die "local dist has commits origin/dist lacks (unpushed or diverged dist work)"
  PARENT=$REMOTE
else
  PARENT=$DIST
fi
[ -z "$PARENT" ] || [ "$(git rev-parse "$PARENT^{tree}")" != "$TREE" ] || die "$TAG is already built: the parent of dist has this exact tree"
if [ -n "$PARENT" ]; then C=$(git commit-tree "$TREE" -p "$PARENT" -m "$MSG"); else C=$(git commit-tree "$TREE" -m "$MSG"); fi
git update-ref refs/heads/dist "$C"
)
```

Then check the tree the directory will see, and push `dist` with the release. If the export fails validation, delete the local `dist` (`git branch -D dist`) before building again, since the block stops on an unpushed local `dist`:

```bash
T=$(mktemp -d); git archive dist | tar -x -C "$T"
claude plugin validate --strict "$T"; echo "validate exit=$?"
claude plugin validate --profile directory --strict "$T"; echo "directory exit=$?"
```
