#!/usr/bin/env python3
"""Tests for apply_rules.py, the rules.json executor.

These pin the three damage classes applying-rules-by-script.md names:
an untranslated $1 written into source, a locate-only rule's empty
replace deleting text, and a rule running over metadata instead of
code -- plus the span-identity rule that suppresses a match running
from code INTO a string, which start-only masking missed
(stdlib only, Python 3.9+).

Run:  python3 test_apply_rules.py
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
import apply_rules  # noqa: E402

FIXTURE = """\
#tag Class
Protected Class Worker
#tag Method, Flags = &h0
Sub Run(myString As String, s As String)
  n = Len(myString)
  x = Len(s) ' was Len(t)
  msg = "Len(a)"
  nameField.Text = nameField.Text.Left(5)
End Sub
#tag EndMethod
End Class
#tag EndClass
"""

WINDOW = """\
#tag DesktopWindow
Begin DesktopWindow MainWindow
   Left = 110
   Text = "OK"
End
#tag EndDesktopWindow
"""


class ApplyRulesTests(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.td.name)
        self.code = self.root / "Worker.xojo_code"
        self.code.write_text(FIXTURE)
        self.window = self.root / "MainWindow.xojo_window"
        self.window.write_text(WINDOW)

    def tearDown(self):
        self.td.cleanup()

    def run_cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        code = 0
        with contextlib.redirect_stdout(out), \
                contextlib.redirect_stderr(err):
            try:
                apply_rules.main([str(self.root), *argv])
            except SystemExit as e:
                code = e.code if isinstance(e.code, int) else 1
                if not isinstance(e.code, int):
                    err.write(str(e.code or ""))
        return code, out.getvalue(), err.getvalue()

    def test_c0r0_converts_code_and_only_code(self):
        # The shipped Len rule, IDE dialect: find has $1 in its replace.
        code, out, _ = self.run_cli("--rules", "c0r0", "--apply")
        self.assertEqual(code, 0)
        text = self.code.read_text()
        self.assertIn("n = myString.Length", text)
        self.assertIn("x = s.Length ' was Len(t)", text)  # comment kept
        self.assertIn('msg = "Len(a)"', text)             # string kept
        self.assertNotIn("$1", text)                      # dialect translated
        # The window's layout metadata is untouched even though nothing
        # in it matches Len -- assert byte identity for the principle.
        self.assertEqual(self.window.read_text(), WINDOW)

    def test_case_insensitive_like_the_ide_checkbox(self):
        self.code.write_text(FIXTURE.replace("Len(myString)",
                                             "len(myString)"))
        self.run_cli("--rules", "c0r0", "--apply")
        self.assertIn("n = myString.Length", self.code.read_text())

    def test_locate_only_rule_is_loud_and_leaves_bytes_alone(self):
        # c3r54 ships find "\\.Text\\b" with an EMPTY replace: running
        # it would turn nameField.Text = ... into nameField = ... and
        # compile. applies:false must gate it out, loudly.
        before = self.code.read_bytes()
        code, _, err = self.run_cli("--rules", "c3r54", "--apply")
        self.assertNotEqual(code, 0)   # nothing runnable was named
        self.assertEqual(self.code.read_bytes(), before)
        self.assertIn("locate-only", err)
        self.assertIn("c3r54", err)

    def test_mixed_list_runs_the_runnable_and_skips_the_rest(self):
        code, out, err = self.run_cli("--rules", "c0r0,c3r54", "--apply")
        self.assertEqual(code, 0)
        self.assertIn("locate-only", err)
        self.assertIn("n = myString.Length", self.code.read_text())
        self.assertIn(".Text", self.code.read_text())  # c3r54 never ran

    def test_unknown_rule_id_is_fatal(self):
        code, _, err = self.run_cli("--rules", "c99r99")
        self.assertNotEqual(code, 0)
        self.assertIn("c99r99", err)

    def test_dry_run_is_the_default(self):
        before = self.code.read_bytes()
        code, out, _ = self.run_cli("--rules", "c0r0")
        self.assertEqual(code, 0)
        self.assertEqual(self.code.read_bytes(), before)
        self.assertIn("dry run", out)
        self.assertIn("c0r0", out)

    def test_match_running_into_a_string_is_suppressed(self):
        # Span identity: the match begins in code and ends inside the
        # literal's blanked content, so the masked slice differs and
        # the whole match must be suppressed -- a start-only test
        # would have applied it and cut the string open.
        self.code.write_text(
            "#tag Class\nProtected Class W\n#tag Method, Flags = &h0\n"
            'Sub R()\n  y = Combine(q, "sep")\nEnd Sub\n'
            "#tag EndMethod\nEnd Class\n#tag EndClass\n")
        edits = self.root / "edits.json"
        edits.write_text(json.dumps(
            [{"label": "bad-span", "find": 'Combine\\(q, "se',
              "replace": "X"}]))
        before = self.code.read_bytes()
        _, out, _ = self.run_cli("--edits", str(edits), "--apply")
        self.assertEqual(self.code.read_bytes(), before)
        self.assertIn("suppressed in non-code", out)

    def test_edits_file_uses_python_dialect_verbatim(self):
        edits = self.root / "edits.json"
        edits.write_text(json.dumps(
            [{"label": "swap", "find": r"(?i)\bmyString\b",
              "replace": "renamed"}]))
        self.run_cli("--edits", str(edits), "--apply")
        self.assertIn("n = Len(renamed)", self.code.read_text())

    def test_path_filter_limits_the_files(self):
        other_dir = self.root / "Sub"
        other_dir.mkdir()
        other = other_dir / "Other.xojo_code"
        other.write_text(FIXTURE)
        self.run_cli("--rules", "c0r0", "--apply", "--path", "Sub")
        self.assertIn("myString.Length", other.read_text())
        self.assertIn("Len(myString)", self.code.read_text())  # untouched

    def test_two_matches_on_one_line_count_as_two(self):
        # The count the commit template pastes must reconcile with the
        # differ's per-occurrence warning deltas; counting changed
        # LINES under-reported.
        self.code.write_text(
            "#tag Class\nProtected Class W\n#tag Method, Flags = &h0\n"
            "Sub R(a As String, b As String)\n"
            "  n = Len(a) + Len(b)\n"
            "End Sub\n#tag EndMethod\nEnd Class\n#tag EndClass\n")
        _, out, _ = self.run_cli("--rules", "c0r0", "--format", "json")
        self.assertEqual(json.loads(out)["total"], 2)

    def test_crlf_survives_a_dollar_anchored_rule(self):
        # `\s*$` would otherwise swallow the \r and write a
        # mixed-ending file; the \r is held out of the match.
        crlf = ("#tag Class\r\nProtected Class W\r\n"
                "#tag Method, Flags = &h0\r\nSub R(arr() As String)\r\n"
                "  arr.Remove i\r\nEnd Sub\r\n#tag EndMethod\r\n"
                "End Class\r\n#tag EndClass\r\n")
        self.code.write_bytes(crlf.encode())
        edits = self.root / "edits.json"
        edits.write_text(json.dumps(
            [{"label": "tail", "find": r"\.Remove\s+(\w+)\s*$",
              "replace": r".RemoveAt(\1)"}]))
        self.run_cli("--edits", str(edits), "--apply")
        data = self.code.read_bytes()
        self.assertIn(b"arr.RemoveAt(i)\r\n", data)
        self.assertNotIn(b")\n#", data)   # no bare-\n line crept in

    def test_json_format(self):
        _, out, _ = self.run_cli("--rules", "c0r0", "--format", "json")
        result = json.loads(out)
        self.assertFalse(result["applied"])
        self.assertEqual(result["total"], 2)
        self.assertEqual(result["rules"][0]["applied"], 2)


if __name__ == "__main__":
    unittest.main(verbosity=1)
