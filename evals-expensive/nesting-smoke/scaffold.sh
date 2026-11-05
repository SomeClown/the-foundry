#!/usr/bin/env bash
# Builds the nesting smoke fixture: six small files, one token in deep/only_here.py.
set -euo pipefail
real_git=""
for candidate in "$(xcrun --find git 2>/dev/null || true)" /Library/Developer/CommandLineTools/usr/bin/git "$(command -v git)"; do
  if [ -n "$candidate" ] && [ -x "$candidate" ]; then real_git="$candidate"; break; fi
done
[ -n "$real_git" ] || { echo "no git found" >&2; exit 1; }
mkdir -p bin deep
printf '#!/bin/sh\nexec "%s" "$@"\n' "$real_git" > bin/git
chmod +x bin/git
G="./bin/git -c user.name=Owner -c user.email=owner@example.com -c commit.gpgsign=false"

cat > README.md <<'EOT'
# shelf

A tiny library that keeps a list of books and prints it.

Run `python3 app.py` to see the list.
EOT
cat > app.py <<'EOT'
"""Prints the shelf."""

from util import title_case
from deep.helpers import join_titles

BOOKS = ["dune", "emma", "ulysses"]


def main():
    print(join_titles([title_case(b) for b in BOOKS]))


if __name__ == "__main__":
    main()
EOT
cat > util.py <<'EOT'
"""Small string helpers."""


def title_case(text):
    return text.strip().title()
EOT
: > deep/__init__.py
cat > deep/helpers.py <<'EOT'
"""Joins titles for display."""


def join_titles(titles):
    return ", ".join(titles)
EOT
cat > deep/only_here.py <<'EOT'
"""Holds the one marker this smoke test looks for."""

# The smoke test checks that this exact string survives the trip back up.
MARKER = "NEST-5519"


def marker():
    return MARKER
EOT
$G init -q -b main
mkdir -p .git/info
printf 'bin/\n' >> .git/info/exclude
$G add -A && $G commit -qm "shelf 0.1.0"
