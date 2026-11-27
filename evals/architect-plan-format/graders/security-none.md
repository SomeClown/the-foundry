---
type: regex
target: {source: file, path: docs/plans/2026-10-23-top-words.md}
pattern: '(?:^|\n)#{2,3} 4\.[^\n]*\n(?:(?!\n#{1,3} )[\s\S])*?Security(?: notes)?[*\x60]*:[*\x60]*[ \t]+[*\x60]*[Nn]one\b'
match: contains
---
