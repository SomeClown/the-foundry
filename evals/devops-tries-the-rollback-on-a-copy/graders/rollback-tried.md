---
type: regex
target: trace
pattern: 'The report follows:(?:[^"\\]|\\.)*?(?:\\n|\n)[ \t>*\x60-]*(?:[0-9]+\.[ \t]+)?[*\x60]*Rollback[*\x60]*:[*\x60]*[ \t]+(?!(?:(?!\\n)(?!\btried\b).)*(?:\b[Nn][Oo][Tt]\b|n\x27t\b)[^\w\n]*\btried\b)(?:(?!\\n)(?!\btried\b).)*\btried\b(?:(?!\\n)(?!\bexit\b).)*\bexit(?: code)?[ =:]*0\b'
match: contains
weight: 2
---
