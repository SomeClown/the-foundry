---
type: regex
target: trace
pattern: 'The report follows:(?:[^"\\]|\\.)*?(?:\\n|\n)[ \t>*\x60-]*(?:[0-9]+\.[ \t]+)?[*\x60]*Rollback[*\x60]*:[*\x60]*[ \t]+(?:(?!\\n).)*?(?<![Nn]ot )\btried\b(?:(?!\\n).)*?\bexit(?: code)?[ =:]*0\b'
match: contains
weight: 2
---
