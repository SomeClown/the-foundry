---
type: regex
target: last_message
pattern: '^(?:(?![ \t]*\x60\x60\x60)[^\n]*\n|[ \t]*\x60\x60\x60[^\n]*\n(?:(?![ \t]*\x60\x60\x60)[^\n]*\n)*[ \t]*\x60\x60\x60[^\n]*\n)*?[ \t]*\x60\x60\x60[^\n]*\n(?:(?![ \t]*\x60\x60\x60)[^\n]*\n)*?[^\n]*\blogs\b'
match: contains
weight: 1
---
