# Privacy

The Foundry doesn't collect, store, or send any data. There's no server, no
account, no analytics, and no telemetry; nothing in the plugin reports back to
me or to anyone else. It's Markdown instructions for Claude Code, two small
scripts that run on your machine, and their tests.

What it does do, it does inside your own Claude Code session, under the
permissions you've set:

- **Your files:** its agents read the project you open, and five of them write
  files there, each in its own lane (application code, UI code, tests, config,
  docs). Nothing is copied anywhere else by the plugin.
- **The web:** two agents (`qa` and `uiux`) can use Claude Code's own web search
  and page fetching, and two (`frontend` and `uiux`) can drive the Claude
  desktop app's built-in browser, mostly against your own dev server.
- **Your remote:** the `ship` skill pushes, opens pull requests, merges, and
  tags in your own repository, using the git and GitHub CLI login you already
  have, and only after you approve the exact steps.

Your code and conversations reach Anthropic the same way they do in any Claude
Code session; the plugin adds no other destination.
[Anthropic's own privacy policy](https://www.anthropic.com/legal/privacy)
covers that part.

The README's "What it runs, sends, and fetches" section has the full list. If
something here is ever wrong, that's a bug: please
[open an issue](https://github.com/SomeClown/the-foundry/issues).
