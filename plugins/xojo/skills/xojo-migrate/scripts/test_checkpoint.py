#!/usr/bin/env python3
"""Tests for checkpoint.py, the analyze-document differ.

These pin the two field lessons -- identical counts are a staleness
signal, and regressions key on (message, location) so an edit above a
site does not turn the whole file into "new errors" -- plus the draft's
inversion: a clean document is a success, not a failed run
(stdlib only, Python 3.9+).

Run:  python3 test_checkpoint.py
"""
import contextlib
import io
import json
import pathlib
import sys
import tempfile
import unittest

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import checkpoint  # noqa: E402


def diag(message, severity="warning", location="App.Run", line=1):
    return {"severity": severity, "kind": "project", "type": "Code",
            "message": message, "location": location,
            "position": f"{location}, line {line}", "line": line}


def dep(sym, location="App.Run", line=1):
    return diag(f"{sym} is deprecated.  You should use New{sym} instead",
                location=location, line=line)


def doc(diags, ok=None, outcome=None):
    n_err = sum(1 for d in diags if d["severity"] == "error")
    return {"schema_version": 1,
            "ok": (not n_err) if ok is None else ok,
            "outcome": outcome or ("project_errors" if n_err
                                   else "project_warnings"),
            "exit_code": 1 if n_err else 0,
            "summary": f"{n_err} errors", "diagnostics": diags,
            "error": None}


BASE = doc([dep("Left"), dep("Left", line=9), dep("InStr"),
            diag("This item does not exist", severity="error",
                 location="App.Run", line=4)])


class CheckpointTests(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.td.name)
        self.basefile = self.root / "base.json"
        self.basefile.write_text(json.dumps(BASE))

    def tearDown(self):
        self.td.cleanup()

    def run_cli(self, new_doc, *argv):
        newfile = self.root / "new.json"
        newfile.write_text(json.dumps(new_doc))
        out, err = io.StringIO(), io.StringIO()
        code = 0
        with contextlib.redirect_stdout(out), \
                contextlib.redirect_stderr(err):
            try:
                checkpoint.main([str(newfile), str(self.basefile), *argv])
            except SystemExit as e:
                code = e.code if isinstance(e.code, int) else 1
                if not isinstance(e.code, int):
                    err.write(str(e.code or ""))
        return code, out.getvalue(), err.getvalue()

    def test_progress_reads_as_progress(self):
        code, out, _ = self.run_cli(doc([dep("InStr")]))
        self.assertEqual(code, 0)
        self.assertIn("verdict: no new errors", out)
        self.assertIn("cleared to zero (1): Left", out)
        self.assertIn("1 (was     1)  InStr", out)

    def test_clean_document_is_a_success(self):
        # The draft exited "the analysis did not run" on zero
        # diagnostics, making the migration's goal state unreportable.
        code, out, _ = self.run_cli(doc([]))
        self.assertEqual(code, 0)
        self.assertIn("verdict: clean -- 0 errors, 0 warnings", out)

    def test_identical_counts_raise_the_staleness_flag(self):
        # 1 error + 3 warnings, exactly like the baseline: if edits
        # happened in between, the IDE analyzed a stale copy. The field
        # run hit exactly this and nearly trusted it.
        same_shape = doc([dep("Left"), dep("Left", line=9), dep("InStr"),
                          diag("This item does not exist",
                               severity="error", location="App.Run",
                               line=4)])
        code, out, _ = self.run_cli(same_shape)
        self.assertEqual(code, 0)
        self.assertIn("verdict: SUSPECT", out)
        self.assertIn("stale", out)

    def test_a_new_error_stops_the_boundary(self):
        broken = doc([dep("InStr"),
                      diag("Type has no member named RemoveAt",
                           severity="error", location="App.Cleanup",
                           line=2)])
        code, out, _ = self.run_cli(broken)
        self.assertEqual(code, 1)
        self.assertIn("verdict: STOP", out)
        self.assertIn("RemoveAt", out)

    def test_shifted_line_is_not_a_regression(self):
        # Same message and location, different line: an edit above the
        # site moved it. A line-keyed diff called this a new error.
        shifted = doc([diag("This item does not exist", severity="error",
                            location="App.Run", line=44)])
        code, out, _ = self.run_cli(shifted)
        self.assertEqual(code, 0)
        self.assertIn("NEW errors not in baseline: 0", out)
        self.assertIn("shifted line numbers", out)

    def test_documents_that_never_analyzed_are_refused(self):
        failed = {"ok": False, "outcome": "connect_failed",
                  "diagnostics": [],
                  "error": {"message": "no IDE socket"}}
        code, _, err = self.run_cli(failed)
        self.assertNotEqual(code, 0)
        self.assertIn("did not run", err)

    def test_json_format(self):
        _, out, _ = self.run_cli(doc([dep("InStr")]), "--format", "json")
        d = json.loads(out)
        self.assertEqual(d["errors"], {"baseline": 1, "new": 0})
        self.assertEqual(d["cleared"], ["Left"])
        self.assertIn("verdict", d)

    def test_stdin_dash(self):
        out, err = io.StringIO(), io.StringIO()
        stdin = io.StringIO(json.dumps(doc([dep("InStr")])))
        with contextlib.redirect_stdout(out), \
                contextlib.redirect_stderr(err):
            checkpoint.main(["-", str(self.basefile)], stdin=stdin)
        self.assertIn("verdict: no new errors", out.getvalue())


if __name__ == "__main__":
    unittest.main(verbosity=1)
