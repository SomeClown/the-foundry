---
type: regex
target: {source: file, path: index.html}
pattern: '<script|https?://|//cdn'
match: not_contains
weight: 3
---
