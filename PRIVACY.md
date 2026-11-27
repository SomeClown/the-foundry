# Privacy

The Foundry doesn't collect or send any data. The one thing it stores is a
file on your own machine, described below. There's no server, no
account, no analytics, and no telemetry; nothing in the plugin reports back to
me or to anyone else. It's Markdown instructions for Claude Code. The repository's `main` branch also
holds its tests and eval cases, which run only when you run them.

What it does do, it does inside your own Claude Code session, under the
permissions you've set:

- **Your files:** its agents read the project you open, and five of them write
  files there, each in its own lane (application code, UI code, tests, config,
  docs). `investigate` starts read-only reader agents inside your session, and
  they go nowhere new. On a large repo it also starts copies of itself as area
  leads, which hold Bash like it does. Nothing is copied anywhere else by the plugin,
  with one exception: `run-plan` and `debug` append a retro to
  `~/.foundry/retro.md` on your own machine (or to the file named by the
  `FOUNDRY_RETRO_FILE` environment variable, if you set it). For each run that
  needed correcting, it holds the date, the repo's top folder's name, the plan
  file's name or the bug's short name, and one line per correction. A run with
  nothing to correct writes nothing. The instructions tell the session to keep
  code, file contents and secrets out of it. `run-plan` also puts a copy of its
  lines in the build log at the end of the plan file, which is committed with
  the plan. Nothing reads the retro file but you and your sessions, and nothing
  sends it anywhere.
- **The web:** two agents (`qa` and `uiux`) can use Claude Code's own web search
  and page fetching, and two (`frontend` and `uiux`) can drive the Claude
  desktop app's built-in browser, mostly against your own dev server. None of them puts your files, code,
  secrets or anyone's details into a search, a URL or a form on another site.
- **Your remote:** the `ship` skill pushes, opens pull requests, merges, and
  tags in your own repository, using the git and GitHub CLI login you already
  have, and only after you approve the exact steps.
- **Credentials:** the plugin ships none and `investigate` doesn't open files named
  like credential stores, and every agent reports a secret it comes on by file
  and line, never by value. `ship` (and `devops`, when you ask it to run a deploy) use the git,
  `gh`, SSH, or cloud CLI logins you already have; those tools handle the
  token, and the plugin never sees it.

Your code and conversations reach Anthropic the same way they do in any Claude
Code session; the plugin adds no other destination.
[Anthropic's own privacy policy](https://www.anthropic.com/legal/privacy)
covers that part.

The skills ship no scripts: `run-plan` and `debug` give your session commands
that run through its own Bash. On the `main` branch, `evals-expensive/compare.py`,
`evals-expensive/sync_case.py`, `evals-expensive/sync_big_sweep.py`,
`evals-expensive/measure_reply.py` and `evals-expensive/check_parts.py` run
only when you run them by hand, stay local, use no network, and read result
JSON, transcripts or saved reports. `sync_big_sweep.py` also runs a scaffold
and writes generated files under `evals-expensive/`, and `check_parts.py`
runs the fixture's own `bin/git`. The `evals-expensive/` scaffolds that build
a repo each write a `bin/git` wrapper into their scratch fixture.

`evals/scorecard.py` is run by hand the same way: it reads result JSON, writes rows into `evals/SCORECARD.md`, and uses no network.

The README's "What it runs, sends, and fetches" section has the full list. If
something here is ever wrong, that's a bug: please
[open an issue](https://github.com/SomeClown/the-foundry/issues).
