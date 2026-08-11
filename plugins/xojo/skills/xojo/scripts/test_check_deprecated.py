#!/usr/bin/env python3
"""Tests for check-deprecated.py (stdlib only, Python 3.9+).

The script reads the generated TSV indexes, which are build artifacts and
may be absent, so these tests build a small synthetic pair in a temp
directory instead. What they pin:

- the three syntax positions (member access, As/New including the
  `As New X` compound, and global calls), and the prose stripping
- the function-vs-class split: a name that is both a deprecated global
  function ("<Name> Method" page) and a deprecated class reports the
  function at a call and the class after As/New
- the bare-member fallback staying silent when a current API shares the
  member name, and current globals like Val never being flagged

Run:  python3 test_check_deprecated.py
"""
import importlib.util
import pathlib
import shutil
import sys
import tempfile
import unittest

HERE = pathlib.Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location(
    "check_deprecated", HERE / "check-deprecated.py"
)
C = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(C)

CLASSES = """\
name\tkind\tflags\tdeprecated_in\treplacement\tnote\tmembers\tpath\tsummary
Window\tClass\tdeprecated\t2021r3\tDesktopWindow\t\t0\tapi/deprecated/window.md\t
Window Method\tMethod\tdeprecated\t2019r2\tApp.WindowAt / App.WindowCount / App.Windows\t\t0\tapi/deprecated/window_method.md\t
Screen Method\tMethod\tdeprecated\t2019r2\tDesktopDisplay.DisplayAt\t\t0\tapi/deprecated/screen_method.md\t
Date\tClass\tdeprecated\t2019r2\tDateTime\t\t0\tapi/deprecated/date.md\t
MsgBox\tMethod\tdeprecated\t2019r2\tMessageBox or MessageDialog\t\t0\tapi/deprecated/msgbox.md\t
Val\tMethod\t\t\t\t\t0\tapi/text/val.md\t
"""

MEMBERS = """\
name\tkind\tsignature\tflags\tdeprecated_in\treplacement\tnote\tpath
ListBox.ListCount\tproperty\t\tdeprecated\t2019r2\tDesktopListBox.RowCount\t\tx
ListBox.Text\tproperty\t\tdeprecated\t2021r3\tDesktopListBox\t\tx
DesktopTextField.Text\tproperty\t\t\t\t\t\tx
"""


class Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = pathlib.Path(tempfile.mkdtemp())
        (cls.dir / "classes.tsv").write_text(CLASSES, encoding="utf-8")
        (cls.dir / "members.tsv").write_text(MEMBERS, encoding="utf-8")
        cls._references = C.REFERENCES
        C.REFERENCES = cls.dir
        cls.index = C.load_index()

    @classmethod
    def tearDownClass(cls):
        C.REFERENCES = cls._references
        shutil.rmtree(cls.dir)

    def hits(self, line):
        return C.find_uses(line, self.index)

    def replacement(self, line):
        found = self.hits(line)
        self.assertEqual(len(found), 1, found)
        return found[0][2][2]

    def test_as_position_flags_the_type(self):
        self.assertEqual(self.replacement("Dim d As Date"), "DateTime")

    def test_as_new_compound_flags_the_type(self):
        # `Dim d As New Date` -- the As once consumed the New and the type
        # name went unmatched.
        self.assertEqual(self.replacement("Dim d As New Date"), "DateTime")

    def test_call_position_prefers_the_function_row(self):
        self.assertEqual(
            self.replacement("w = Window(0)"),
            "App.WindowAt / App.WindowCount / App.Windows",
        )

    def test_type_position_keeps_the_class_row(self):
        self.assertEqual(self.replacement("Dim w As Window"), "DesktopWindow")

    def test_function_with_no_class_row_is_matched_both_ways(self):
        # No deprecated Screen class page exists, so the "Screen Method" row
        # serves both positions.
        self.assertEqual(self.replacement("d = Screen(0)"), "DesktopDisplay.DisplayAt")
        self.assertEqual(self.replacement("Dim s As Screen"), "DesktopDisplay.DisplayAt")

    def test_current_global_is_never_flagged(self):
        self.assertEqual(self.hits("n = Val(s)"), [])

    def test_member_on_an_instance_matches_by_leaf(self):
        self.assertEqual(self.replacement("n = lst.ListCount"), "DesktopListBox.RowCount")

    def test_leaf_shared_with_current_api_stays_silent(self):
        # .Text is deprecated on ListBox and current on DesktopTextField, so
        # the bare leaf must not match; only the qualified form may.
        self.assertEqual(self.hits("s = fld.Text"), [])
        self.assertEqual(len(self.hits("s = ListBox.Text")), 1)

    def test_strings_comments_and_notes_are_not_code(self):
        text = (
            '#tag Note, Name = Old\n'
            'MsgBox "hi"\n'
            '#tag EndNote\n'
            's = "MsgBox is not a call here"\n'
            "' MsgBox in a comment\n"
        )
        self.assertEqual(self.hits(text), [])

    def test_real_call_is_still_seen_after_stripping(self):
        self.assertEqual(
            self.replacement('MsgBox("hello")'), "MessageBox or MessageDialog"
        )


if __name__ == "__main__":
    unittest.main(verbosity=1)
