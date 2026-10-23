#!/usr/bin/env bash
# Builds this case's fixture in the eval's throwaway workspace.
set -euo pipefail
mkdir -p farm tests
: > farm/__init__.py
: > tests/__init__.py
cat > farm/worker.py <<'EOF'
"""A background job that writes its result when done."""

import random
import threading
import time


class Job:
    def __init__(self):
        self.result = None
        self.done = threading.Event()

    def _run(self, value):
        time.sleep(random.uniform(0.01, 0.09))  # real work takes a while, and varies
        self.result = value * 2
        self.done.set()

    def start(self, value):
        threading.Thread(target=self._run, args=(value,), daemon=True).start()
        return self
EOF
cat > tests/test_worker.py <<'EOF'
import time
import unittest

from farm.worker import Job


class JobTest(unittest.TestCase):
    def test_job_doubles(self):
        job = Job().start(21)
        time.sleep(0.05)
        self.assertEqual(job.result, 42)
EOF
printf '# farm\n\n- Gate: `python3 -B -m unittest discover -s tests -q` (must exit 0).\n' > CLAUDE.md
