---
type: llm
focus: trace
---

The trace is a session that dispatched one agent. The agent's own report is the result of the Agent call: the text after "The report follows:", every line indented two spaces. Judge that report, not the session's final message.

PASS only if the report is a design direction a frontend builder could implement without coming back: a palette with exact hex values and a role for each, named typefaces with fallback stacks, and how it lands in this project's plain CSS (custom properties or rules for styles.css, and class or markup changes for index.html), with a note on keeping text contrast at WCAG AA. FAIL if it is vague, with no values, proposes a CSS framework, an npm package or a build step, or says it wrote or edited a file.
