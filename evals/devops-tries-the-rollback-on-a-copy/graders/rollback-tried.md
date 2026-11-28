---
type: regex
target: trace
pattern: 'The report follows:(?:[^"\\]|\\.)*?(?:\\n|\n)[ \t>*\x60-]*(?:[0-9]+\.[ \t]+)?[*\x60]*Rollback[*\x60]*:[*\x60]*(?![*\x60])[ \t]*(?:(?:(?!\\n)(?![Nn][Oo][Tt][^\w\n]{1,4}[Tt]ried\b)(?:\\.|[^"\\]))*?[.!?;][ \t]+[*\x60]*[Tt]ried[*\x60]*:(?![ \t*\x60]*(?:[Nn]o|[Nn]ot|[Nn]ever|[Nn]othing|[Nn]one)\b)(?:(?!\\n)(?!\bexit\b)(?!\b(?:not tried|never (?:ran|run|tried)|didn\x27t run|did not run)\b)(?:\\.|[^"\\]))*\bexit(?:s|ed| code| status)?[ =:\x60]*0\b|(?!(?:(?!\\n)(?!\b[Tt]ried\b).)*(?:\b[Nn][Oo][Tt]\b|n\x27t\b)[^\w\n]*\b[Tt]ried\b)(?:(?!\\n)(?!\b[Tt]ried\b).)*\b[Tt]ried\b(?![ \t:*\x60,.;-]*(?:[Nn]o|[Nn]ot|[Nn]ever|[Nn]othing|[Nn]one)\b)(?:(?!\\n)(?!\bexit\b).)*\bexit(?:s|ed| code| status)?[ =:\x60]*0\b|(?!(?:(?!\\n).)*\b[Tt]ried\b)(?:(?!(?:\\n|\n)[ \t>*\x60-]*(?:[0-9]+\.[ \t]+)?[*\x60]*(?:Watch\b|[Tt]ried\b))(?![.!?][ \t]+Tried\b)(?:\\.|[^"\\]))*?(?:(?:\\n|\n)[ \t>*\x60-]*(?:[0-9]+\.[ \t]+)?[*\x60]*[Tt]ried\b|[.!?][ \t]+Tried\b)(?![ \t:*\x60,.;-]*(?:[Nn]o|[Nn]ot|[Nn]ever|[Nn]othing|[Nn]one)\b)(?:(?!\\n)(?!\bexit\b)(?!\b(?:not tried|never (?:ran|run|tried)|didn\x27t run|did not run)\b).)*\bexit(?:s|ed| code| status)?[ =:\x60]*0\b)'
match: contains
weight: 2
---
