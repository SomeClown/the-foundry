---
type: regex
target: {source: file, path: docs/plans/2026-10-23-top-words.md}
pattern: '(?:^|\n)#{2,3} 4\.[^\n]*(?:(?!\n#{1,3} )[\s\S])*?\n[ \t>*\x60-]*(?:[0-9]+\.[ \t]+)?[*\x60]*Security(?: notes)?[*\x60]*:'
match: contains
---
