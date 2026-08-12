#!/usr/bin/env python3
"""Tests for locate.py, the diagnostic-to-file:line filter.

The fixture project pins the four resolution shapes a real project
produced: a method overload (ambiguous by design), two controls sharing
an event name (unique only through the Owner.Event key -- the draft
tooling reported this AMBIGUOUS and skipped a real site), a computed
property (Get/Set bodies), and a #tag Note slab quoting a method that
must not be indexed (stdlib only, Python 3.9+).

Run:  python3 test_locate.py
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
import locate  # noqa: E402

HELPERS = """\
#tag Module
Protected Module Helpers
#tag Method, Flags = &h0
Sub Convert(s As String)
  Dim x As Integer
  x = Len(s)
End Sub
#tag EndMethod
#tag Method, Flags = &h0
Sub Convert(s As String, n As Integer)
  Dim y As Integer
  y = Len(s) + n
End Sub
#tag EndMethod
#tag Note, Name = Old code
Sub Archived()
  x = Len(s)
End Sub
#tag EndNote
End Module
#tag EndModule
"""

MAIN_WINDOW = """\
#tag DesktopWindow
Begin DesktopWindow MainWindow
   Left = 110
   Begin DesktopButton SaveButton
      Left = 20
   End
   Begin DesktopButton CancelButton
      Left = 40
   End
End
#tag EndDesktopWindow
#tag Events SaveButton
Sub Pressed()
  Call Len(s)
End Sub
#tag EndEvents
#tag Events CancelButton
Sub Pressed()
  Call Len(t)
End Sub
#tag EndEvents
"""

PERSON = """\
#tag Class
Protected Class Person
#tag ComputedProperty, Flags = &h0
#tag Getter
Get
  Return mTitle
End Get
#tag EndGetter
#tag Setter
Set
  mTitle = value
End Set
#tag EndSetter
Title As String
#tag EndComputedProperty
End Class
#tag EndClass
"""


def build_project(root):
    root = pathlib.Path(root)
    (root / "Helpers.xojo_code").write_text(HELPERS)
    (root / "MainWindow.xojo_window").write_text(MAIN_WINDOW)
    (root / "Person.xojo_code").write_text(PERSON)
    (root / "Fixture.xojo_project").write_text("Type=Desktop\n")
    return root


class IndexTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.td = tempfile.TemporaryDirectory()
        cls.root = build_project(cls.td.name)
        cls.idx = locate.build_index(cls.root)

    @classmethod
    def tearDownClass(cls):
        cls.td.cleanup()

    def test_overloads_share_a_key(self):
        self.assertEqual(
            [line for _, line in self.idx[("helpers", "convert")]],
            [4, 10])

    def test_note_slab_method_is_not_indexed(self):
        # `Sub Archived` exists only inside #tag Note; indexing it would
        # let a diagnostic resolve into archived prose.
        self.assertNotIn(("helpers", "archived"), self.idx)

    def test_event_keys(self):
        self.assertEqual(self.idx[("mainwindow", "savebutton.pressed")],
                         [(str(self.root / "MainWindow.xojo_window"), 13)])
        self.assertEqual(self.idx[("cancelbutton", "pressed")],
                         [(str(self.root / "MainWindow.xojo_window"), 18)])
        self.assertEqual(
            [line for _, line in self.idx[("mainwindow", "pressed")]],
            [13, 18])

    def test_computed_property_keys(self):
        # Bare name maps to BOTH bodies; .Get/.Set are exact.
        self.assertEqual(
            [line for _, line in self.idx[("person", "title")]], [5, 10])
        self.assertEqual(
            [line for _, line in self.idx[("person", "title.get")]], [5])
        self.assertEqual(
            [line for _, line in self.idx[("person", "title.set")]], [10])


class ResolveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.td = tempfile.TemporaryDirectory()
        cls.root = build_project(cls.td.name)
        cls.idx = locate.build_index(cls.root)

    @classmethod
    def tearDownClass(cls):
        cls.td.cleanup()

    def test_overload_is_ambiguous_with_candidates(self):
        res = locate.resolve(self.idx, "Helpers.Convert", 2)
        self.assertEqual(res[0], "ambiguous")
        self.assertEqual([c["file_line"] for c in res[1]], [6, 12])

    def test_shared_event_name_resolves_through_the_owner_key(self):
        # (mainwindow, pressed) has two hits; the draft stopped there
        # and reported AMBIGUOUS. The Owner.Event key is unique and must
        # win even though a broader shape multi-hits first.
        res = locate.resolve(self.idx, "MainWindow.SaveButton.Pressed", 1)
        self.assertEqual(res, ("located",
                               str(self.root / "MainWindow.xojo_window"),
                               14))

    def test_bare_computed_property_is_ambiguous(self):
        res = locate.resolve(self.idx, "Person.Title", 1)
        self.assertEqual(res[0], "ambiguous")
        self.assertEqual(len(res[1]), 2)

    def test_computed_property_get_is_exact(self):
        res = locate.resolve(self.idx, "Person.Title.Get", 1)
        self.assertEqual(res[0], "located")
        self.assertEqual(res[2], 6)

    def test_ide_casing_is_ignored(self):
        res = locate.resolve(self.idx, "MAINWINDOW.SaveButton.PRESSED", 1)
        self.assertEqual(res[0], "located")

    def test_unknown_location_is_unresolved(self):
        self.assertEqual(locate.resolve(self.idx, "Nowhere.Nothing", 1),
                         ("unresolved",))


def diag(**kw):
    d = {"severity": "warning", "kind": "project", "type": "Code",
         "message": "Len is deprecated.  You should use String.Length "
                    "instead", "location": None, "line": None}
    d.update(kw)
    return d


class EnrichTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.td = tempfile.TemporaryDirectory()
        cls.root = build_project(cls.td.name)

    @classmethod
    def tearDownClass(cls):
        cls.td.cleanup()

    def make_doc(self):
        return {
            "ok": False,
            "diagnostics": [
                diag(location="CancelButton.Pressed", line=1,
                     custom_field="keep-me"),
                diag(severity="error",
                     message="This item does not exist",
                     location="MainWindow.SaveButton.Pressed", line=1),
                diag(location="Helpers.Convert", line=2),
                diag(location="CancelButton.Pressed"),  # line: null
                diag(location="Nowhere.Nothing", line=1),
                diag(message="dropped 3 messages"),     # no location
            ],
        }

    def test_enrichment_fields_and_formula(self):
        doc = self.make_doc()
        stats = locate.enrich(doc, self.root)
        d = doc["diagnostics"][0]
        self.assertEqual(d["resolution"], "located")
        self.assertEqual(d["file_line"], 19)  # signature 18 + body line 1
        self.assertEqual(d["line_basis"], "body-offset")
        self.assertTrue(d["file"].endswith("MainWindow.xojo_window"))
        self.assertEqual(d["custom_field"], "keep-me")  # untouched
        self.assertEqual(stats["located"], 3)
        self.assertEqual(stats["ambiguous"], 1)
        self.assertEqual(stats["unresolved"], 1)
        self.assertEqual(stats["no_location"], 1)
        self.assertEqual(doc["located"], stats)

    def test_errors_are_enriched_too(self):
        # The draft filtered to deprecation warnings; the burn-down
        # recipe needs errors located as well.
        doc = self.make_doc()
        locate.enrich(doc, self.root)
        self.assertEqual(doc["diagnostics"][1]["resolution"], "located")

    def test_null_line_marks_its_basis(self):
        doc = self.make_doc()
        locate.enrich(doc, self.root)
        d = doc["diagnostics"][3]
        self.assertEqual(d["file_line"], 18)  # the signature line itself
        self.assertEqual(d["line_basis"], "signature")

    def test_ambiguous_carries_candidates_and_no_file(self):
        doc = self.make_doc()
        locate.enrich(doc, self.root)
        d = doc["diagnostics"][2]
        self.assertEqual(d["resolution"], "ambiguous")
        self.assertEqual(len(d["candidates"]), 2)
        self.assertNotIn("file", d)
        self.assertNotIn("file_line", d)


class CliTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.td = tempfile.TemporaryDirectory()
        cls.root = build_project(cls.td.name)

    @classmethod
    def tearDownClass(cls):
        cls.td.cleanup()

    def run_main(self, argv, doc):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), \
                contextlib.redirect_stderr(err):
            locate.main(argv, stdin=io.StringIO(json.dumps(doc)))
        return out.getvalue(), err.getvalue()

    def test_session_project_drives_enrichment(self):
        doc = {"ok": True,
               "diagnostics": [diag(location="CancelButton.Pressed",
                                    line=1)],
               "result": {"session": {
                   "project": str(self.root / "Fixture.xojo_project"),
                   "was_open": False, "closed": True}}}
        out, err = self.run_main([], doc)
        emitted = json.loads(out)
        self.assertEqual(emitted["diagnostics"][0]["file_line"], 19)
        self.assertIn("located 1 site(s)", err)

    def test_no_root_passes_through_unenriched(self):
        # No session record, no --project: claiming a file:line the disk
        # cannot back would be worse than adding nothing.
        doc = {"ok": True,
               "diagnostics": [diag(location="CancelButton.Pressed",
                                    line=1)]}
        out, err = self.run_main([], doc)
        emitted = json.loads(out)
        self.assertEqual(emitted, doc)
        self.assertNotIn("file_line", emitted["diagnostics"][0])
        self.assertIn("UNENRICHED", err)

    def test_project_flag_overrides(self):
        doc = {"ok": True,
               "diagnostics": [diag(location="CancelButton.Pressed",
                                    line=1)]}
        out, _ = self.run_main(["--project", str(self.root)], doc)
        self.assertEqual(json.loads(out)["diagnostics"][0]["file_line"], 19)

    def test_open_session_warns_but_enriches(self):
        doc = {"ok": True,
               "diagnostics": [diag(location="CancelButton.Pressed",
                                    line=1)],
               "result": {"session": {
                   "project": str(self.root / "Fixture.xojo_project"),
                   "was_open": True, "closed": False}}}
        out, err = self.run_main([], doc)
        self.assertEqual(json.loads(out)["diagnostics"][0]["file_line"], 19)
        self.assertIn("session.closed is false", err)

    def test_text_report(self):
        doc = {"ok": True,
               "diagnostics": [diag(location="CancelButton.Pressed",
                                    line=1),
                               diag(location="Helpers.Convert", line=2)]}
        out, _ = self.run_main(
            ["--project", str(self.root), "--format", "text"], doc)
        self.assertIn("LOCATED (1)", out)
        self.assertIn("MainWindow.xojo_window:19", out)
        self.assertIn("AMBIGUOUS (1)", out)


if __name__ == "__main__":
    unittest.main(verbosity=1)
