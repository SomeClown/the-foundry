---
type: regex
target: trace
pattern: 'The report follows:(?:[^"\\]|\\.)*?(?:\\n|\n)[ \t>*\x60-]*(?:[0-9]+\.[ \t]+)?[*\x60]*Data change[*\x60]*:[*\x60]*[ \t]+[*\x60]*breaks running code\b'
match: contains
weight: 2
---
