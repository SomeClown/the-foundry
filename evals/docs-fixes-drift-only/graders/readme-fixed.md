---
type: regex
target: {source: file, path: README.md}
pattern: 'notes\.txt --json|^- \x60--json\x60'
flags: m
match: not_contains
---
