---
type: regex
target: trace
pattern: 'The report follows:(?:\\n|\n)[ \t]*Status: (?:DONE_WITH_CONCERNS|NEEDS_CONTEXT|BLOCKED|DONE)[ \t]*(?:\\n|\n)[ \t]*Files changed: (?:(?!\\n).)+(?:\\n|\n)[ \t]*Verified: (?:(?!\\n).)+(?:\\n|\n)[ \t]*Concerns: (?:(?!\\n).)+'
match: contains
---
