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
2. Test it: run the affected agent on a real task in a real project. "It reads
   nicely" is not testing; neither of us can review a prompt by staring at it.
3. Update the [CHANGELOG](CHANGELOG.md) under an Unreleased heading.
4. Open a PR describing what behavior changed and how you verified it.

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
[CHANGELOG](CHANGELOG.md) says what they're getting.
