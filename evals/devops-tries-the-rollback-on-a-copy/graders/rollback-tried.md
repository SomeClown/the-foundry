---
type: regex
target: trace
pattern: 'The report follows:(?:[^"\\]|\\.)*?(?:\\n|\n)[ \t>*\x60-]*(?:[0-9]+\.[ \t]+)?[*\x60]*Rollback[*\x60]*:[*\x60]*[ \t]+(?!(?:(?!\\n)(?!\b[Tt]ried\b).)*(?:\b[Nn][Oo][Tt]\b|n\x27t\b)[^\w\n]*\b[Tt]ried\b)(?:(?!\\n)(?!\b[Tt]ried\b).)*\b[Tt]ried\b(?:(?!\\n)(?!\bexit\b).)*\bexit(?: code)?[ =:]*0\b'
match: contains
weight: 2
---
