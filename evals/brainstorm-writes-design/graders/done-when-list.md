---
type: regex
target: {source: file, path: docs/design.md}
pattern: '(?:^|\n)## 3\. (?:(?!\n## )[\s\S])*?\*\*Done when(?:(?!\n## )[\s\S])*?AC-1\b(?:(?!\n## )[\s\S])*?AC-2\b'
match: contains
---
