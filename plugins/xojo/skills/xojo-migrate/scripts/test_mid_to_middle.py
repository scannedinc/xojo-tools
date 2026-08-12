#!/usr/bin/env python3
"""Tests for mid_to_middle.py, the audit-first Mid converter.

The audit is the point: API 1.0 Mid clamps a start below 1 and Middle
does not, so `For j = 0 To n ... Mid(s, j, 1)` works today and breaks
after a mechanical decrement. These pin the audit's verdicts (literal,
To, DownTo, offset shift, For Each, no-loop), the refusal to --apply
over a risky site, and the decrement simplifier's exact output table
(stdlib only, Python 3.9+).

Run:  python3 test_mid_to_middle.py
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
import mid_to_middle  # noqa: E402

FIXTURE = """\
#tag Class
Protected Class Worker
#tag Method, Flags = &h0
Sub Safe(s As String)
  For i As Integer = 1 To 10
    a = Mid(s, i, 1)
    b = Mid(s, i + 1, 1)
  Next
End Sub
#tag EndMethod
#tag Method, Flags = &h0
Sub Risky(s As String)
  For j As Integer = 0 To 5
    c = Mid(s, j, 1)
  Next
End Sub
#tag EndMethod
#tag Method, Flags = &h0
Sub Down(s As String)
  For k As Integer = 9 DownTo 1
    d = Mid(s, k, 1)
  Next
End Sub
#tag EndMethod
#tag Method, Flags = &h0
Sub Review(s As String, offset As Integer, items() As String)
  e = Mid(s, offset, 2)
  For Each item As String In items
    f = Mid(s, 3)
  Next
  g = s.Mid(2, 1)
  h = Mid("lit" + s, 2, 1)
  k2 = Mid(s)
End Sub
#tag EndMethod
End Class
#tag EndClass
"""


class DecrementTests(unittest.TestCase):
    def test_the_simplification_table(self):
        # The exact outputs the field draft produced; pinned so a
        # "cleanup" cannot quietly change emitted source.
        for expr, want in (("5", "4"), ("1", "0"),
                           ("i + 1", "i"), ("i+1", "i"),
                           ("x", "x - 1"),
                           ("x+10", "(x+10) - 1"),
                           ("f(x)", "(f(x)) - 1")):
            self.assertEqual(mid_to_middle.decrement(expr), want, expr)


class AuditAndConvertTests(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.td.name)
        self.code = self.root / "Worker.xojo_code"
        self.code.write_text(FIXTURE)

    def tearDown(self):
        self.td.cleanup()

    def run_cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        code = 0
        with contextlib.redirect_stdout(out), \
                contextlib.redirect_stderr(err):
            try:
                mid_to_middle.main([str(self.root), *argv])
            except SystemExit as e:
                code = e.code if isinstance(e.code, int) else 1
                if not isinstance(e.code, int):
                    err.write(str(e.code or ""))
        return code, out.getvalue(), err.getvalue()

    def result(self, *argv):
        _, out, _ = self.run_cli("--format", "json", *argv)
        return json.loads(out)

    def test_audit_groups_sites_by_bound(self):
        a = self.result()["audit"]
        self.assertEqual(a["histogram"]["i=1"], 2)   # i and i+1
        self.assertEqual(a["histogram"]["j=0"], 1)
        self.assertEqual(a["histogram"]["k=1"], 1)   # DownTo's To side
        self.assertEqual(a["histogram"]["LITERAL"], 3)  # f, g, h starts
        self.assertEqual(a["total"], 8)

    def test_audit_flags_the_clamp_reliance(self):
        a = self.result()["audit"]
        self.assertEqual(len(a["risky"]), 1)
        self.assertIn("start='j'", a["risky"][0])
        self.assertIn("effective 0", a["risky"][0])

    def test_offset_shifts_the_test(self):
        # `Mid(s, i + 1, 1)` under For i = 1: effective 2, safe -- and
        # under a 0-based loop it would be exactly what makes it safe.
        a = self.result()["audit"]
        self.assertEqual(len(a["risky"]), 1)  # i+1 did NOT join j

    def test_unsettleable_bounds_go_to_hand_review(self):
        a = self.result()["audit"]
        joined = "\n".join(a["review"])
        self.assertIn("start='offset'", joined)   # parameter, no loop
        self.assertEqual(len(a["review"]), 1)

    def test_apply_refuses_over_a_risky_site(self):
        before = self.code.read_bytes()
        code, _, err = self.run_cli("--apply")
        self.assertNotEqual(code, 0)
        self.assertEqual(self.code.read_bytes(), before)
        self.assertIn("clamp", err)
        self.assertIn("--force", err)

    def test_force_converts_with_the_decrement(self):
        code, _, _ = self.run_cli("--apply", "--force")
        self.assertEqual(code, 0)
        text = self.code.read_text()
        self.assertIn("a = s.Middle(i - 1, 1)", text)
        self.assertIn("b = s.Middle(i, 1)", text)      # i+1 collapsed
        self.assertIn("c = s.Middle(j - 1, 1)", text)
        self.assertIn("e = s.Middle(offset - 1, 2)", text)
        self.assertIn("g = s.Middle(1, 1)", text)      # method form
        self.assertIn('h = Mid("lit" + s, 2, 1)', text)  # illegal receiver
        self.assertIn("k2 = Mid(s)", text)             # not framework

    def test_one_argument_mid_is_reported_not_silent(self):
        r = self.result()
        self.assertTrue(any("one argument" in s
                            for s in r["not_framework"]))

    def test_method_form_sites_are_previewed(self):
        _, out, _ = self.run_cli()
        self.assertIn("METHOD FORM (1)", out)
        self.assertIn("s.Mid(2, 1)", out)

    def test_dry_run_is_the_default(self):
        before = self.code.read_bytes()
        code, out, _ = self.run_cli()
        self.assertEqual(code, 0)
        self.assertEqual(self.code.read_bytes(), before)
        self.assertIn("dry run", out)
        self.assertIn("verdict: 1 risky of 8, 1 for hand review", out)


if __name__ == "__main__":
    unittest.main(verbosity=1)
