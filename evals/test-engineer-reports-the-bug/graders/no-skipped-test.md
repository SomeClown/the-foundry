---
type: regex
target: trace
pattern: '"name":"(?:Edit|Write|MultiEdit)","input":\{[^\n]*?(?:expectedFailure|unittest\.skip|skipTest|skipIf|skipUnless)'
match: not_contains
weight: 3
---
