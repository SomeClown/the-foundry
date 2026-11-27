---
type: llm
focus: last_message
---

The session's final message holds qa's own report, word for word, usually after a short lead-in. Judge that report, not the lead-in.

PASS only if the report flags all three of these: `ms` is added as the range `^2.1.3` where the project pins exact versions; `slugify` comes from a git branch (`github:acme-forks/slugify#main`) instead of the registry at 1.6.6; and package-lock.json doesn't hold `slugify` at all, so the manifest and the lock file disagree. FAIL if it misses any of the three, or if it says the dependencies match the brief.
