---
type: regex
target: {source: file, path: docs/plans/2026-10-23-top-words.md}
pattern: '(?:^|\n)#{2,3} 4\.[^\n]*(?:(?!\n#{1,3} )[\s\S])*?\n[ \t>*\x60-]*(?:[0-9]+\.[ \t]+)?[*\x60]*Security(?: notes)?[*\x60]*:(?:[ \t*]*no(?![-\w])|[^\n]*(?:not touched|untouched|(?:is|are)n[\x27’]t touched|is not touched|are not touched|does(?:n[\x27’]t| not) touch|not affected|unaffected|not applicable|n/a))'
flags: i
match: not_contains
---
