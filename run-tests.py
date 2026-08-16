#!/usr/bin/env python3
"""Run every local check that gates a change to this repository.

This is THE canonical local gate: run it from the repository root before
pushing. It runs, in order:

  1. unittest discovery in plugins/xojo/skills/xojo/scripts
  2. unittest discovery in plugins/xojo/skills/xojo-lint/scripts
  3. unittest discovery in plugins/xojo/skills/xojo-migrate/scripts
  4. the bespoke runner plugins/xojo/skills/xojo-ide/scripts/test_xojoctl.py
  5. the pre-commit hook's content checks (sh .githooks/pre-commit)

Exits nonzero if any suite fails. A suite that runs zero tests, or whose
summary line cannot be found, also counts as a failure so a broken
discovery can never pass silently. Skipped tests are surfaced but do not
fail: in particular the xojo-migrate drift tests skip on a fresh clone,
until the xojo skill's generated documentation indexes are built. The
hook step (step 5) checks staged/index content, so with nothing staged it
validates the last-committed state rather than unstaged edits.
"""

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent

RAN_RE = re.compile(r"^Ran (\d+) tests?", re.MULTILINE)
BESPOKE_RE = re.compile(r"^(\d+) passed, (\d+) failed", re.MULTILINE)

# Generous per-suite ceiling: a hung suite must fail the gate, not wedge it.
TIMEOUT = 600

MIGRATE_SKIP_NOTE = (
    "note: the drift tests skip when the xojo skill's generated"
    " documentation indexes are not built (fresh clone)"
)


def _capture(cmd, cwd):
    # A None return code means the suite hit TIMEOUT; callers fail it.
    try:
        proc = subprocess.run(
            cmd, cwd=str(cwd),
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            universal_newlines=True, timeout=TIMEOUT)
    except subprocess.TimeoutExpired as exc:
        def text(s):
            if s is None:
                return ""
            return s if isinstance(s, str) else s.decode("utf-8", "replace")
        return None, text(exc.stdout), text(exc.stderr)
    return proc.returncode, proc.stdout, proc.stderr


def _timed_out(label, out, err):
    tail = "FAIL: suite timed out after %d seconds" % TIMEOUT
    return _report(label, False, tail, out + err)


def _report(label, ok, tail, dump):
    print("== %s ==" % label)
    print(tail)
    if not ok and dump.strip():
        print(dump.strip())
    return ok


def run_unittest(label, subdir, skip_note=None):
    code, out, err = _capture(
        [sys.executable, "-m", "unittest", "discover"], ROOT / subdir)
    if code is None:
        return _timed_out(label, out, err)
    # unittest writes its whole report to stderr; the summary is the
    # "Ran N tests" line plus the final OK/FAILED status line.
    lines = [ln for ln in err.strip().splitlines() if ln.strip()]
    ran_line = next((ln for ln in lines if RAN_RE.match(ln)), None)
    status = lines[-1] if lines else "(no output)"
    match = RAN_RE.search(err)
    count = int(match.group(1)) if match else None
    ok = code == 0 and count is not None and count > 0
    if count is None:
        tail = "FAIL: no 'Ran N tests' line in the unittest output"
    elif count == 0:
        tail = "FAIL: zero tests ran (%s)" % ran_line
    else:
        tail = "%s -- %s" % (ran_line, status)
    if skip_note and "skipped=" in status:
        tail += "\n" + skip_note
    return _report(label, ok, tail, out + err)


def run_bespoke(label, script):
    path = ROOT / script
    code, out, err = _capture([sys.executable, path.name], path.parent)
    if code is None:
        return _timed_out(label, out, err)
    match = BESPOKE_RE.search(out + err)
    if match is None:
        tail = "FAIL: no 'N passed, M failed' line in the runner output"
        ok = False
    elif int(match.group(1)) == 0:
        tail = "FAIL: zero tests passed (%s)" % match.group(0)
        ok = False
    elif int(match.group(2)) != 0:
        # The counts gate alongside the exit code: a runner that reports
        # failures but exits 0 must not pass.
        tail = "FAIL: %s" % match.group(0)
        ok = False
    else:
        ok = code == 0
        tail = match.group(0) if ok else "FAIL: %s" % match.group(0)
    return _report(label, ok, tail, out + err)


def run_hook(label):
    code, out, err = _capture(["sh", ".githooks/pre-commit"], ROOT)
    if code is None:
        return _timed_out(label, out, err)
    ok = code == 0
    tail = "content checks passed" if ok else "content checks failed"
    return _report(label, ok, tail, out + err)


def main():
    results = [
        ("xojo scripts", run_unittest(
            "xojo scripts", "plugins/xojo/skills/xojo/scripts")),
        ("xojo-lint scripts", run_unittest(
            "xojo-lint scripts", "plugins/xojo/skills/xojo-lint/scripts")),
        ("xojo-migrate scripts", run_unittest(
            "xojo-migrate scripts", "plugins/xojo/skills/xojo-migrate/scripts",
            skip_note=MIGRATE_SKIP_NOTE)),
        ("xojo-ide test_xojoctl", run_bespoke(
            "xojo-ide test_xojoctl",
            "plugins/xojo/skills/xojo-ide/scripts/test_xojoctl.py")),
        ("pre-commit hook", run_hook("pre-commit hook")),
    ]
    print("== summary ==")
    for label, ok in results:
        print("%s  %s" % ("PASS" if ok else "FAIL", label))
    failed = [label for label, ok in results if not ok]
    if failed:
        print("FAILED: %s" % ", ".join(failed))
        return 1
    print("All suites passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
