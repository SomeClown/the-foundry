---
type: regex
target: trace
pattern: 'The report follows:(?:[^"\\]|\\.)*?(?:\\n|\n)[ \t>*\x60-]*(?:[0-9]+\.[ \t]+)?[*\x60]*Watch[*\x60]*:[*\x60]*[ \t]+(?:(?!\\n).)*?[Rr]oll back if\b[ \t:]*(?:\\\x22|[\x60\x22\x27(\[*_“‘])*\w'
match: contains
---
