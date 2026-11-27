---
type: regex
target: trace
pattern: 'The report follows:(?:[^"\\]|\\.)*?(?:migrate\.py up|DROP COLUMN legacy_phone)'
match: contains
weight: 1
---
