#!/usr/bin/env python3
"""Tests for global_to_method.py, the balanced-paren converter and oracle.

These pin the two reasons the tool exists -- nested-call arguments the
bundled [^()] regexes skip by design, and hard rule 3's receiver
refusal that doubles as the deferral oracle -- plus the masking and
reporting honesty the draft lacked (stdlib only, Python 3.9+).

Run:  python3 test_global_to_method.py
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
import global_to_method  # noqa: E402

FIXTURE = """\
#tag Class
Protected Class Worker
#tag Method, Flags = &h0
Sub Run(s As String, a As String, b As String)
  t = ReplaceAll(NthField(s, ",", 1), a, b)
  u = ReplaceAll("00" + s, a, b)
  v = Trim(Trim(s))
  w = "ReplaceAll(x, y, z)" ' ReplaceAll(c, d, e)
  r = ReplaceAll(a,
End Sub
#tag EndMethod
#tag Note, Name = Old
  q = ReplaceAll(s, a, b)
#tag EndNote
End Class
#tag EndClass
"""

SPEC = [{"fn": "ReplaceAll", "method": "", "drop_parens": False},
        {"fn": "Trim", "method": "", "drop_parens": True}]


class ConvertTests(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.td.name)
        self.code = self.root / "Worker.xojo_code"
        self.code.write_text(FIXTURE)
        self.spec = self.root / "spec.json"
        self.spec.write_text(json.dumps(SPEC))

    def tearDown(self):
        self.td.cleanup()

    def run_cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        code = 0
        with contextlib.redirect_stdout(out), \
                contextlib.redirect_stderr(err):
            try:
                global_to_method.main([str(self.root), *argv])
            except SystemExit as e:
                code = e.code if isinstance(e.code, int) else 1
                if not isinstance(e.code, int):
                    err.write(str(e.code or ""))
        return code, out.getvalue(), err.getvalue()

    def lines(self):
        return self.code.read_text().split("\n")

    def test_nested_call_argument_converts(self):
        # The whole reason the tool exists: [^()] rules skip this shape.
        self.run_cli(str(self.spec), "--apply")
        self.assertEqual(self.lines()[4],
                         '  t = NthField(s, ",", 1).ReplaceAll(a, b)')

    def test_illegal_receiver_is_refused_and_reported(self):
        _, out, _ = self.run_cli(str(self.spec), "--apply")
        self.assertIn('u = ReplaceAll("00" + s, a, b)', self.lines()[5])
        self.assertIn("SKIPPED (1)", out)
        self.assertIn("not a legal receiver", out)
        self.assertIn("conversion-traps.md section 4", out)

    def test_nested_same_name_converts_in_one_pass(self):
        # Trim(Trim(s)): converting the outer exposes the inner at the
        # same offset; the rescan-from-same-position loop must convert
        # both, and drop_parens renders the property form.
        self.run_cli(str(self.spec), "--apply")
        self.assertEqual(self.lines()[6], "  v = s.Trim.Trim")

    def test_strings_comments_and_note_slabs_are_untouched(self):
        self.run_cli(str(self.spec), "--apply")
        self.assertEqual(self.lines()[7],
                         '  w = "ReplaceAll(x, y, z)" \' ReplaceAll(c, d, e)')
        self.assertEqual(self.lines()[12], "  q = ReplaceAll(s, a, b)")

    def test_unbalanced_call_is_reported_and_untouched(self):
        # The draft silently abandoned the line; a call spanning lines
        # is real work someone must do by hand.
        _, out, _ = self.run_cli(str(self.spec), "--apply")
        self.assertEqual(self.lines()[8], "  r = ReplaceAll(a,")
        self.assertIn("SPANS LINES (1)", out)

    def test_dry_run_is_the_default(self):
        before = self.code.read_bytes()
        _, out, _ = self.run_cli(str(self.spec))
        self.assertEqual(self.code.read_bytes(), before)
        self.assertIn("dry run", out)

    def test_json_format_counts(self):
        _, out, _ = self.run_cli(str(self.spec), "--format", "json")
        result = json.loads(out)
        self.assertEqual(result["per_function"]["ReplaceAll"]["converted"], 1)
        self.assertEqual(result["per_function"]["Trim"]["converted"], 2)
        self.assertEqual(len(result["skipped"]), 1)
        self.assertFalse(result["applied"])


class OracleTests(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.td.name)
        (self.root / "W.xojo_code").write_text(
            "#tag Class\nProtected Class W\n#tag Method, Flags = &h0\n"
            "Sub R(myString As String, s As String)\n"
            "  n = Len(myString)\n"
            '  m = Len("00" + s)\n'
            "End Sub\n#tag EndMethod\nEnd Class\n#tag EndClass\n")

    def tearDown(self):
        self.td.cleanup()

    def test_oracle_derives_from_rules_and_classifies(self):
        # would-convert = forgotten site; illegal receiver = genuine
        # deferral. This is the boundary reconciliation that makes the
        # forgotten-parked-site class of accounting slip impossible.
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), \
                contextlib.redirect_stderr(err):
            global_to_method.main([str(self.root), "--oracle",
                                   "--format", "json"])
        result = json.loads(out.getvalue())
        self.assertTrue(result["oracle"])
        self.assertFalse(result["applied"])
        self.assertEqual(result["per_function"]["Len"]["converted"], 1)
        self.assertEqual(result["per_function"]["Len"]["method"], "Length")
        self.assertEqual(len(result["skipped"]), 1)
        # Dry only: the tree is untouched.
        self.assertIn("n = Len(myString)",
                      (self.root / "W.xojo_code").read_text())

    def test_oracle_refuses_apply(self):
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                global_to_method.main([str(self.root), "--oracle",
                                       "--apply"])

    def test_oracle_spec_is_nonempty_and_deduped(self):
        spec = global_to_method.oracle_spec()
        fns = [s["fn"].lower() for s in spec]
        self.assertEqual(len(fns), len(set(fns)))
        self.assertIn("len", fns)
        self.assertIn("mid", fns)


if __name__ == "__main__":
    unittest.main(verbosity=1)
