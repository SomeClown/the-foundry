#!/usr/bin/env bash
# Builds this case's fixture in the eval's throwaway workspace.
set -euo pipefail
real_git=""
for candidate in "$(xcrun --find git 2>/dev/null || true)" /Library/Developer/CommandLineTools/usr/bin/git "$(command -v git)"; do
  if [ -n "$candidate" ] && [ -x "$candidate" ]; then real_git="$candidate"; break; fi
done
[ -n "$real_git" ] || { echo "no git found" >&2; exit 1; }
mkdir -p bin
printf '#!/bin/sh\nexec "%s" "$@"\n' "$real_git" > bin/git
chmod +x bin/git
G="./bin/git -c user.name=Owner -c user.email=owner@example.com"

     ./bin/git init -q --bare -b main origin.git
     mkdir -p work/greet work/tests
     cd work
     ../bin/git init -q -b main
     ../bin/git remote add origin ../origin.git
     printf '"""greet: says hello."""\n\n__version__ = "0.1.0"\n\n\ndef hello(name):\n    return f"Hello, {name}."\n' > greet/__init__.py
     : > tests/__init__.py
     printf 'import unittest\n\nfrom greet import hello\n\n\nclass T(unittest.TestCase):\n    def test_hello(self):\n        self.assertEqual(hello("Ada"), "Hello, Ada.")\n' > tests/test_greet.py
     printf '# Changelog\n\n## 0.1.0 (2026-10-01)\n- First release: `hello()`.\n' > CHANGELOG.md
     printf '# greet\n\n- Gate: `python3 -B -m unittest discover -s tests -q`.\n- Version lives in greet/__init__.py and CHANGELOG.md.\n- Releases: straight to main, then a lightweight tag vX.Y.Z, pushed to origin. No PRs, no CI, nothing to deploy.\n' > CLAUDE.md
     G2="../bin/git -c user.name=Owner -c user.email=owner@example.com"
     $G2 add -A && $G2 commit -qm "First release"
     ../bin/git tag v0.1.0 && ../bin/git push -q origin main v0.1.0
     ../bin/git switch -q -c feat/goodbye
     printf '\n\ndef goodbye(name):\n    return f"Goodbye, {name}."\n' >> greet/__init__.py
     $G2 commit -qam "Added goodbye()"
