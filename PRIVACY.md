# Privacy

The Foundry doesn't collect, store, or send any data. There's no server, no
account, no analytics, and no telemetry; nothing in the plugin reports back to
me or to anyone else. It's Markdown instructions for Claude Code, a few small
scripts that run on your machine, and their tests.

What it does do, it does inside your own Claude Code session, under the
permissions you've set:

- **Your files:** its agents read the project you open, and five of them write
  files there, each in its own lane (application code, UI code, tests, config,
  docs). `investigate` starts read-only reader agents inside your session, and
  they go nowhere new. On a large repo it also starts copies of itself as area
  leads, which hold Bash like it does. Nothing is copied anywhere else by the plugin.
- **The web:** two agents (`qa` and `uiux`) can use Claude Code's own web search
  and page fetching, and two (`frontend` and `uiux`) can drive the Claude
  desktop app's built-in browser, mostly against your own dev server.
- **Your remote:** the `ship` skill pushes, opens pull requests, merges, and
  tags in your own repository, using the git and GitHub CLI login you already
  have, and only after you approve the exact steps.
- **Credentials:** the plugin ships none and reads no credential files or
  tokens. `ship` (and `devops`, when you ask it to run a deploy) use the git,
  `gh`, SSH, or cloud CLI logins you already have; those tools handle the
  token, and the plugin never sees it.

Your code and conversations reach Anthropic the same way they do in any Claude
Code session; the plugin adds no other destination.
[Anthropic's own privacy policy](https://www.anthropic.com/legal/privacy)
covers that part.

Beyond the two workflow scripts, `evals-expensive/compare.py` and
`evals-expensive/sync_case.py` run only when you run them by hand, stay local,
use no network, and read result JSON; the eval scaffold writes a `bin/git`
wrapper into its scratch fixture.

The README's "What it runs, sends, and fetches" section has the full list. If
something here is ever wrong, that's a bug: please
[open an issue](https://github.com/SomeClown/the-foundry/issues).
