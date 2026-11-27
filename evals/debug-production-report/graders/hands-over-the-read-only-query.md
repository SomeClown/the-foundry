---
type: regex
target: last_message
pattern: '^(?:(?![ \t]*\x60\x60\x60)[^\n]*\n|[ \t]*\x60\x60\x60[^\n]*\n(?:(?![ \t]*\x60\x60\x60)[^\n]*\n)*[ \t]*\x60\x60\x60[^\n]*\n)*?[ \t]*\x60\x60\x60[^\n]*\n(?:(?![ \t]*\x60\x60\x60)[^\n]*\n)*?[^\n]*sqlite3 (?:-[a-z]+ )*-readonly(?:\n(?![ \t]*\x60\x60\x60)|[^\n])*?alert_posts'
match: contains
weight: 1
---
