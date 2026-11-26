"""Run each test file as its own `unittest discover` process, side by side.

Usage: python3 tests/run_tests.py [-j N | --jobs N] [--timeout S] [file ...]

Each file runs exactly as `python3 -m unittest discover -s tests -p <file>`
would run it from the repo root, so the working directory and test ids match.
The output ends with unittest's own closing lines, so a grep for them works.
"""
import argparse
import os
import re
import signal
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

TESTS = Path(__file__).resolve().parent
ROOT = TESTS.parent
GRACE = 5

RAN_RE = re.compile(r"^Ran (\d+) tests? in [\d.]+s$")
STATUS_RE = re.compile(r"^(?:(OK|FAILED)(?: \((.*)\))?|NO TESTS RAN)$")
COUNT_KEYS = ("failures", "errors", "skipped", "expected failures", "unexpected successes")


def positive_int(text):
    try:
        value = int(text)
    except ValueError:
        raise argparse.ArgumentTypeError("not an integer: %r" % text)
    if value < 1:
        raise argparse.ArgumentTypeError("must be 1 or more: %r" % text)
    return value


def parse_args(argv):
    parser = argparse.ArgumentParser(
        prog="run_tests.py",
        description="Run each test file as its own process, several at a time.",
    )
    parser.add_argument("-j", "--jobs", type=positive_int, default=min(8, os.cpu_count() or 1),
                        help="files to run at a time (default: the smaller of 8 and the core count)")
    parser.add_argument("--timeout", type=positive_int, default=900,
                        help="seconds allowed per file (default 900)")
    parser.add_argument("files", nargs="*", help="test_x, test_x.py or tests/test_x.py")
    return parser.parse_args(argv)


def fail_usage(message):
    print("error: " + message, file=sys.stderr)
    sys.exit(2)


def pick_files(names):
    for sub in sorted(TESTS.iterdir()):
        if sub.is_dir() and (sub / "__init__.py").exists():
            fail_usage("tests/%s is a package; discover would run it and this runner does not" % sub.name)
    if not names:
        files = sorted(TESTS.glob("test*.py"))
    else:
        files = []
        for raw in names:
            name = raw
            if name.startswith("tests/"):
                name = name[len("tests/"):]
            if name.endswith(".py"):
                name = name[:-3]
            path = TESTS / (name + ".py")
            if "/" in name or not path.is_file():
                fail_usage("no test file tests/%s.py" % name)
            if path not in files:
                files.append(path)
    if not files:
        fail_usage("no test files in %s" % TESTS)
    return files


def kill_group(proc, sig):
    try:
        os.killpg(proc.pid, sig)
    except (ProcessLookupError, PermissionError):
        return False
    return True


def stop(proc):
    kill_group(proc, signal.SIGTERM)
    try:
        proc.wait(timeout=GRACE)
    except subprocess.TimeoutExpired:
        print("module did not stop on SIGTERM; killing it", file=sys.stderr)
    kill_group(proc, signal.SIGKILL)
    proc.wait()


running = set()


def run_file(path, timeout):
    name = path.stem
    cmd = [sys.executable, "-m", "unittest", "discover", "-s", str(TESTS), "-t", str(TESTS),
           "-p", name + ".py", "-v"]
    start = time.monotonic()
    timed_out = False
    with tempfile.TemporaryFile() as out:
        proc = subprocess.Popen(cmd, cwd=str(ROOT), stdin=subprocess.DEVNULL, stdout=out,
                                stderr=subprocess.STDOUT, start_new_session=True)
        running.add(proc)
        try:
            try:
                code = proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                timed_out = True
                stop(proc)
                code = proc.returncode
        finally:
            kill_group(proc, signal.SIGKILL)
            running.discard(proc)
        out.seek(0)
        text = out.read().decode("utf-8", "replace")
    return summarize(name, text, code, timed_out, time.monotonic() - start, timeout)


def summarize(name, text, code, timed_out, secs, timeout):
    lines = text.splitlines()
    ran_at = status_at = None
    for i in range(len(lines) - 2):
        if RAN_RE.match(lines[i]) and lines[i + 1] == "" and STATUS_RE.match(lines[i + 2]):
            ran_at, status_at = i, i + 2
    n = int(RAN_RE.match(lines[ran_at]).group(1)) if ran_at is not None else None
    status = lines[status_at] if status_at is not None else None
    counts = dict.fromkeys(COUNT_KEYS, 0)
    word = None
    if status is not None:
        m = STATUS_RE.match(status)
        word = m.group(1)
        for key, val in re.findall(r"([a-z ]+)=(\d+)", m.group(2) or ""):
            if key.strip() in counts:
                counts[key.strip()] = int(val)
    if timed_out:
        reason = "timed out after %ds" % timeout
    elif (n == 0 and counts["skipped"] == 0) or status == "NO TESTS RAN":
        reason = "no tests ran"
    elif code != 0:
        reason = "exit %d" % code
    elif n is None or word is None:
        reason = "no summary"
    elif word != "OK":
        reason = "exit %d" % code
    else:
        reason = None
    body = [l for i, l in enumerate(lines) if i != ran_at and i != status_at]
    return {"name": name, "n": n, "counts": counts, "reason": reason, "secs": secs, "body": body}


def progress_line(r):
    tests = "" if r["n"] is None else ", %d tests" % r["n"]
    if r["reason"] is None:
        skipped = r["counts"]["skipped"]
        extra = ", %d skipped" % skipped if skipped else ""
        return "module %s: ok%s%s, %.1fs" % (r["name"], tests, extra, r["secs"])
    return "module %s: failed (%s)%s, %.1fs" % (r["name"], r["reason"], tests, r["secs"])


def main(argv):
    args = parse_args(argv)
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="backslashreplace")
    files = pick_files(args.files)
    results = []
    start = time.monotonic()
    pool = ThreadPoolExecutor(max_workers=args.jobs)
    try:
        futures = [pool.submit(run_file, f, args.timeout) for f in files]
        for fut in as_completed(futures):
            r = fut.result()
            results.append(r)
            print(progress_line(r), flush=True)
    except KeyboardInterrupt:
        for proc in list(running):
            kill_group(proc, signal.SIGKILL)
        pool.shutdown(wait=False, cancel_futures=True)
        print("interrupted", file=sys.stderr)
        return 130
    pool.shutdown()
    wall = time.monotonic() - start

    results.sort(key=lambda r: r["name"])
    failed = [r for r in results if r["reason"] is not None]
    totals = dict.fromkeys(COUNT_KEYS, 0)
    total = 0
    for r in results:
        total += r["n"] or 0
        for key in COUNT_KEYS:
            totals[key] += r["counts"][key]
    for r in failed:
        print("=" * 70)
        print("module %s output:" % r["name"])
        print("\n".join(r["body"]))
        if not any(l.startswith(("FAIL: ", "ERROR: ")) for l in r["body"]):
            print("ERROR: %s (%s)" % (r["name"], r["reason"]))
            own = r["counts"]
            if not (own["failures"] or own["errors"] or own["unexpected successes"]):
                totals["errors"] += 1
    print("runner: %d test files, %d at a time, %d failed" % (len(files), args.jobs, len(failed)))
    print("-" * 70)
    print("Ran %d test%s in %.3fs" % (total, "" if total == 1 else "s", wall))
    print()
    bad = totals["failures"] or totals["errors"] or failed
    parts = ["%s=%d" % (k, totals[k]) for k in COUNT_KEYS if totals[k]]
    if bad:
        print("FAILED (%s)" % ", ".join(parts) if parts else "FAILED")
    else:
        print("OK (%s)" % ", ".join(parts) if parts else "OK")
    sys.stdout.flush()
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
