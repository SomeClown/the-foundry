---
type: regex
target: trace
pattern: '^(?=[\s\S]*AC-1[*\x60]*: Tasks? [0-9])(?=[\s\S]*AC-2[*\x60]*: Tasks? [0-9])(?=[\s\S]*AC-3[*\x60]*: Tasks? [0-9])'
match: contains
weight: 4
---
