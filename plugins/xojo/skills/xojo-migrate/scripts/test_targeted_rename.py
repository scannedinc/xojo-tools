#!/usr/bin/env python3
"""Tests for targeted_rename.py, the flagged-line member renamer.

The fixture pins the tool's whole reason to exist: a flagged
`g.FillRect` renames while the user class's own `DrawRect` -- same
member name, two lines away -- does not. The rest pin the honesty
rules: occurrence mismatch refuses instead of guessing, null map values
report instead of silently dropping, replacements never chain, a
located path outside the verified project root is reported, never
edited, and the root itself must be a real project folder naming real
Xojo source (stdlib only, Python 3.9+).

Run:  python3 test_targeted_rename.py
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
import targeted_rename  # noqa: E402

FIXTURE = """\
#tag Class
Protected Class Painter
#tag Method, Flags = &h0
Sub Draw(g As Graphics)
  g.FillRect 0, 0, 10, 10 ' draws .FillRect
  Call f.GetSaveInfo(v)
  Call helper.DrawRect(1, 2)
End Sub
#tag EndMethod
#tag Method, Flags = &h0
Sub Trim2(a As String, b As String)
  s = a.Trim + b.Trim
End Sub
#tag EndMethod
#tag Method, Flags = &h0
Sub Chain(x As Thing)
  y = x.A + x.B
End Sub
#tag EndMethod
#tag Method, Flags = &h0
Sub DrawRect(a As Integer, b As Integer)
  Dim unused As Integer
End Sub
#tag EndMethod
End Class
#tag EndClass
"""

MAP = {"FillRect": "FillRectangle", "Trim": "Trimmed",
       "A": "B", "B": "C", "GetSaveInfo": None}


def dg(sym, location, line):
    return {"severity": "warning", "kind": "project", "type": "Code",
            "message": f"{sym} is deprecated.  You should use "
                       f"New{sym} instead",
            "location": location,
            "position": f"{location}, line {line}", "line": line}


def located(sym, file, file_line):
    d = dg(sym, "Painter.Draw", 1)
    d.update({"resolution": "located", "file": str(file),
              "file_line": file_line, "line_basis": "body-offset"})
    return d


DIAGS = [dg("FillRect", "Painter.Draw", 1),
         dg("GetSaveInfo", "Painter.Draw", 2),
         dg("Trim", "Painter.Trim2", 1),      # ONE diag, TWO occurrences
         dg("A", "Painter.Chain", 1),
         dg("B", "Painter.Chain", 1)]


class RenameTests(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.td.name)
        self.src = self.root / "Painter.xojo_code"
        self.src.write_text(FIXTURE)
        (self.root / "Fixture.xojo_project").write_text("Type=Desktop\n")
        self.docfile = self.root / "analyze.json"
        self.docfile.write_text(json.dumps({
            "ok": True, "outcome": "project_warnings",
            "diagnostics": DIAGS,
            "result": {"session": {
                "project": str(self.root / "Fixture.xojo_project"),
                "was_open": False, "closed": True}}}))
        self.mapfile = self.root / "map.json"
        self.mapfile.write_text(json.dumps(MAP))

    def tearDown(self):
        self.td.cleanup()

    def run_cli(self, *extra):
        out, err = io.StringIO(), io.StringIO()
        code = 0
        with contextlib.redirect_stdout(out), \
                contextlib.redirect_stderr(err):
            try:
                targeted_rename.main([str(self.docfile), str(self.mapfile),
                                      *extra])
            except SystemExit as e:
                code = e.code if isinstance(e.code, int) else 1
                if not isinstance(e.code, int):
                    err.write(str(e.code or ""))
        return code, out.getvalue(), err.getvalue()

    def lines(self):
        return self.src.read_text().split("\n")

    def test_flagged_line_renames_and_the_user_class_does_not(self):
        # pass-hazards section 2's case: the analyzer flagged
        # g.FillRect; the project's own Sub DrawRect and its call site
        # share the member NAME shape and must survive untouched.
        code, out, _ = self.run_cli("--apply")
        self.assertEqual(code, 0)
        lines = self.lines()
        self.assertIn("g.FillRectangle 0, 0, 10, 10", lines[4])
        self.assertIn(".FillRect", lines[4])   # the comment keeps its text
        self.assertIn("helper.DrawRect(1, 2)", lines[6])
        self.assertIn("Sub DrawRect(", lines[20])
        self.assertIn("renamed: 3 site(s)", out)

    def test_occurrence_mismatch_refuses_the_line(self):
        # One diagnostic, two `.Trim` in code: the IDE gives no column,
        # so renaming either occurrence is a guess. Refuse loudly.
        _, out, _ = self.run_cli("--apply")
        self.assertIn("s = a.Trim + b.Trim", self.lines()[11])
        self.assertIn("OCCURRENCE-AMBIGUOUS", out)
        self.assertIn(".Trim: 2 occurrence(s) in code, 1 flagged", out)

    def test_replacements_do_not_chain(self):
        # A->B and B->C on one line: spans are measured against the
        # original line, so A's result must not feed B's pattern.
        self.run_cli("--apply")
        self.assertEqual(self.lines()[16], "  y = x.B + x.C")

    def test_null_map_value_reports_instead_of_dropping(self):
        # The draft promised this in its docstring and silently dropped
        # the sites instead.
        _, out, _ = self.run_cli("--apply")
        self.assertIn("REPORT ONLY", out)
        self.assertIn("GetSaveInfo", out)
        self.assertIn("Call f.GetSaveInfo(v)", self.lines()[5])

    def test_dry_run_writes_nothing(self):
        before = self.src.read_bytes()
        code, out, _ = self.run_cli()
        self.assertEqual(code, 0)
        self.assertEqual(self.src.read_bytes(), before)
        self.assertIn("(dry run", out)

    def test_json_format(self):
        _, out, _ = self.run_cli("--apply", "--format", "json")
        result = json.loads(out)
        self.assertEqual(result["renamed"], 3)
        self.assertTrue(result["applied"])
        self.assertEqual(len(result["occurrence_ambiguous"]), 1)
        self.assertEqual(len(result["report_only"]), 1)

    def test_error_diagnostics_drive_the_burn_down(self):
        # Pass E feeds this ERRORS -- 'Type "X" has no member named
        # "Y"'. The first version accepted only deprecation warnings
        # and silently no-opped the whole documented burn-down.
        err = {"severity": "error", "kind": "project", "type": "Code",
               "message": 'Type "DesktopThing" has no member named '
                          '"FillRect"',
               "location": "Painter.Draw",
               "position": "Painter.Draw, line 1", "line": 1}
        self.docfile.write_text(json.dumps({
            "ok": False, "outcome": "project_errors",
            "diagnostics": [err],
            "result": {"session": {
                "project": str(self.root / "Fixture.xojo_project"),
                "was_open": False, "closed": True}}}))
        code, out, _ = self.run_cli("--apply")
        self.assertEqual(code, 0)
        self.assertIn("renamed: 1 site(s)", out)
        self.assertIn("g.FillRectangle 0, 0, 10, 10", self.lines()[4])

    def test_undotted_occurrence_refuses_the_line(self):
        # 'mine.ListCount = ListCount': the IDE may be flagging the
        # implicit-Self use. Renaming the dotted occurrence converts an
        # unflagged site and leaves the flagged one -- refuse instead.
        fixture = (
            "#tag Class\nProtected Class W\n#tag Method, Flags = &h0\n"
            "Sub R(mine As Thing)\n"
            "  mine.ListCount = ListCount\n"
            "End Sub\n#tag EndMethod\nEnd Class\n#tag EndClass\n")
        src = self.root / "W.xojo_code"
        src.write_text(fixture)
        self.docfile.write_text(json.dumps({
            "ok": True, "diagnostics": [dg("ListCount", "W.R", 1)],
            "result": {"session": {
                "project": str(self.root / "Fixture.xojo_project"),
                "was_open": False, "closed": True}}}))
        self.mapfile.write_text(json.dumps({"ListCount": "RowCount"}))
        _, out, _ = self.run_cli("--apply")
        self.assertIn("mine.ListCount = ListCount",
                      src.read_text())          # untouched
        self.assertIn("undotted", out)
        self.assertIn("renamed: 0", out)

    def test_unlocated_document_without_root_exits(self):
        self.docfile.write_text(json.dumps(
            {"ok": True, "diagnostics": DIAGS}))
        code, _, err = self.run_cli()
        self.assertNotEqual(code, 0)
        self.assertIn("locate.py", err)

    def write_located_doc(self, diags, located_record):
        self.docfile.write_text(json.dumps(
            {"ok": True, "diagnostics": diags,
             "located": located_record}))
        self.mapfile.write_text(json.dumps({"FillRect": "FillRectangle"}))

    def test_out_of_root_located_path_is_reported_not_edited(self):
        # A located document names its files verbatim; a stale or
        # forged one can name a file outside the project. That site
        # must surface in the report and never reach the work queue.
        outside = tempfile.TemporaryDirectory()
        self.addCleanup(outside.cleanup)
        victim = pathlib.Path(outside.name) / "Victim.xojo_code"
        victim.write_text(FIXTURE)
        self.write_located_doc([located("FillRect", victim, 5)],
                               {"project_root": str(self.root)})
        code, out, _ = self.run_cli("--apply")
        self.assertEqual(code, 0)
        self.assertEqual(victim.read_text(), FIXTURE)
        self.assertIn("renamed: 0", out)
        self.assertIn("file outside project root", out)
        self.assertIn(str(victim), out)

    def test_project_flag_disagreeing_with_recorded_root_exits(self):
        # --project naming a different root than the document records
        # is the stale/relocated-document case: fail loudly naming
        # both, before any edit, instead of silently preferring either.
        elsewhere = tempfile.TemporaryDirectory()
        self.addCleanup(elsewhere.cleanup)
        before = self.src.read_bytes()
        self.write_located_doc([located("FillRect", self.src, 5)],
                               {"project_root": str(self.root)})
        code, _, err = self.run_cli("--apply", "--project",
                                    elsewhere.name)
        self.assertNotEqual(code, 0)
        self.assertIn("disagrees", err)
        self.assertIn(str(pathlib.Path(elsewhere.name).resolve()), err)
        self.assertIn(str(self.root.resolve()), err)
        self.assertEqual(self.src.read_bytes(), before)

    def test_in_root_located_document_still_renames(self):
        # The verified-root check must not disturb the normal pipeline:
        # a document located against this project renames as before,
        # with no enrichment re-run and no --project needed.
        self.write_located_doc([located("FillRect", self.src, 5)],
                               {"project_root": str(self.root)})
        code, out, _ = self.run_cli("--apply")
        self.assertEqual(code, 0)
        self.assertIn("renamed: 1 site(s)", out)
        self.assertIn("g.FillRectangle 0, 0, 10, 10", self.lines()[4])

    def test_project_flag_agreeing_with_recorded_root_proceeds(self):
        self.write_located_doc([located("FillRect", self.src, 5)],
                               {"project_root": str(self.root)})
        code, out, _ = self.run_cli("--apply", "--project",
                                    str(self.root))
        self.assertEqual(code, 0)
        self.assertIn("renamed: 1 site(s)", out)
        self.assertIn("g.FillRectangle 0, 0, 10, 10", self.lines()[4])

    def test_non_source_located_target_is_reported_not_edited(self):
        # locate.py can only locate files from collect_files' source
        # list, so a located diagnostic naming any other suffix is per
        # se forged -- it must land in the report, whatever root the
        # containment check would have blessed.
        evil = self.root / "Evil.txt"
        evil.write_text(FIXTURE)
        self.write_located_doc([located("FillRect", evil, 5)],
                               {"project_root": str(self.root)})
        code, out, _ = self.run_cli("--apply")
        self.assertEqual(code, 0)
        self.assertEqual(evil.read_text(), FIXTURE)
        self.assertIn("renamed: 0", out)
        self.assertIn("not a Xojo source file", out)
        self.assertIn(str(evil), out)

    def test_filesystem_anchor_root_exits(self):
        # A forged document recording project_root "/" makes every
        # absolute path pass the containment check. The anchor is never
        # a legitimate project folder: hard exit before any edit.
        outside = tempfile.TemporaryDirectory()
        self.addCleanup(outside.cleanup)
        victim = pathlib.Path(outside.name) / "Victim.xojo_code"
        victim.write_text(FIXTURE)
        self.write_located_doc([located("FillRect", victim, 5)],
                               {"project_root": "/"})
        code, _, err = self.run_cli("--apply")
        self.assertNotEqual(code, 0)
        self.assertIn(".xojo_project", err)
        self.assertEqual(victim.read_text(), FIXTURE)

    def test_manifestless_root_exits(self):
        # A real directory with no top-level manifest is not a project
        # folder. locate.py records the manifest's parent as the root,
        # so a legitimate document never trips this; a forged one does.
        bare = tempfile.TemporaryDirectory()
        self.addCleanup(bare.cleanup)
        victim = pathlib.Path(bare.name) / "Victim.xojo_code"
        victim.write_text(FIXTURE)
        self.write_located_doc([located("FillRect", victim, 5)],
                               {"project_root": bare.name})
        code, _, err = self.run_cli("--apply")
        self.assertNotEqual(code, 0)
        self.assertIn(".xojo_project", err)
        self.assertEqual(victim.read_text(), FIXTURE)

    def test_located_record_without_root_or_project_exits(self):
        # A bare "located": {} used to skip enrichment AND the root
        # question entirely, letting the document's absolute paths go
        # anywhere. It must now demand --project instead.
        before = self.src.read_bytes()
        self.write_located_doc([located("FillRect", self.src, 5)], {})
        code, _, err = self.run_cli("--apply")
        self.assertNotEqual(code, 0)
        self.assertIn("--project", err)
        self.assertEqual(self.src.read_bytes(), before)


if __name__ == "__main__":
    unittest.main(verbosity=1)
