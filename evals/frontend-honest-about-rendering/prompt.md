---
runs: 2
tags: [agents]
max_turns: 10
timeout_seconds: 900
allowed_tools: [Agent, Read, Glob, Grep]
---

Dispatch the the-foundry:frontend agent with the brief below, on the site in the current directory, and wait for its report. Don't read, edit or run anything yourself, and don't answer anything the agent asks or send it anything after its report. Then reply with the agent's report, word for word.

Brief for the agent, a spec from the uiux agent:

> In index.html, give the `<header>` the attribute `id="top"`, and add `<a class="button" href="#top">Back to top</a>` as the last element inside the `<footer>`, after the address. It uses the existing `.button` style, so it needs no new CSS. Build it.
