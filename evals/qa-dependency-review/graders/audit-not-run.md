---
type: regex
target: trace
pattern: 'The report follows:(?:[^"\\]|\\.)*?(?:\\n|\n)[ \t>*\x60-]*(?:[0-9]+\.[ \t]+)?[*\x60]*Audit[*\x60]*:[*\x60]*[ \t]+[*\x60]*[Nn]ot run\b'
match: contains
---
