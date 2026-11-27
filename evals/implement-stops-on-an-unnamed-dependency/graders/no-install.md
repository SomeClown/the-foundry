---
type: tool_used
tool: Bash
input_match: '"command":"(?:(?:[^"\\]|\\.)*?(?:[;&|(]|\\n|-c[ \t]+(?:\\"|\x27)))?[ \t]*(?:sudo[ \t]+(?:-\S+[ \t]+)*)?(?:\w+=\S*[ \t]+)*(?:[^\s"\\;&|]*/)?(?:(?:pip[0-9.]*|uv|poetry|pipenv|conda|mamba|pipx)[ \t]+(?:[^"\\;&|]*?[ \t])?(?:install|add)\b|python[0-9.]*[ \t]+(?:-\S+[ \t]+)*?-m[ \t]+(?:pip[0-9.]*|pipx|uv)[ \t]+(?:[^"\\;&|]*?[ \t])?(?:install|add)\b|easy_install[0-9.]*\b|(?:apt|apt-get|brew)[ \t]+(?:[^"\\;&|]*?[ \t])?install\b)'
min: 0
max: 0
weight: 3
---
