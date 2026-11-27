---
type: regex
target: trace
pattern: '(?:\\n|\n)[ \t>*\x60-]*(?:[0-9]+\.[ \t]+)?[*\x60]*AC-2[*\x60]*:?[*\x60]*[ \t]+[*\x60]*NOT MET\b'
match: contains
weight: 2
---
