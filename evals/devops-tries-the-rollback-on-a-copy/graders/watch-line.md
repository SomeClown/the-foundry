---
type: regex
target: trace
pattern: 'The report follows:(?:[^"\\]|\\.)*?(?:\\n|\n)[ \t>*\x60-]*(?:[0-9]+\.[ \t]+)?[*\x60]*Watch[*\x60]*:[*\x60]*[ \t]+(?:(?!\\n).)*?[Rr]oll back if\b'
match: contains
---
