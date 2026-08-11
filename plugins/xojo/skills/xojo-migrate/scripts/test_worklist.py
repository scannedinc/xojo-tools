#!/usr/bin/env python3
"""Tests for worklist.py (stdlib only, Python 3.9+).

Every message string below was captured from a live Xojo IDE
(2026.2.1) by running `xojoctl analyze --json` over a project with the
deprecation warnings enabled -- not invented. Two properties of the real
text drive the whole design and are pinned here:

  - The IDE writes TWO spaces after "deprecated." and spells names in its
    own casing ("Listbox", not "ListBox").
  - Member deprecations arrive with NO receiver ("ListCount is
    deprecated..."), so the matrix join cannot key on the receiver. The
    IDE's replacement is what disambiguates: "RowCount" picks
    ListBox.ListCount over PopupMenu.ListCount.

Run:  python3 test_worklist.py
"""
import io
import contextlib
import json
import pathlib
import sys
import unittest

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import worklist  # noqa: E402


def diag(message, severity="warning", location="App.TestDeprecations",
         line=1, source=""):
    return {"id": "d", "severity": severity, "kind": "project", "type": "Code",
            "message": message, "location": location,
            "position": f"{location}, line {line}", "line": line,
            "source": source}


# The seven diagnostics a live analyze returned for a method exercising a
# global function, a global with a sentinel change, a deprecated type, a
# deprecated control class, a bare member, a global whose replacement is a
# constructor signature, and one warning that is not a deprecation at all.
LIVE = {
    "schema_version": 1, "ok": True, "outcome": "project_warnings",
    "exit_code": 0, "summary": "7 warnings",
    "counts": {"errors": 0, "warnings": 7, "script_errors": 0,
               "open_errors": 0},
    "diagnostics": [
        diag("Left is deprecated.  You should use String.Left instead",
             line=3, source="Left(s, 5"),
        diag("InStr is deprecated.  You should use String.IndexOf instead",
             line=4, source='InStr(s, "o"'),
        diag("Date is deprecated.  You should use DateTime instead",
             line=5, source="Date"),
        diag("Listbox is deprecated.  You should use DesktopListBox instead",
             line=7, source="ListBox"),
        diag("ListCount is deprecated.  You should use RowCount instead",
             line=8, source="ListCount"),
        diag("GetFolderItem is deprecated.  You should use "
             "FolderItem.Constructor(path As String, pathMode As PathModes) "
             "instead", line=9, source='GetFolderItem("x"'),
        diag("unused is an unused local variable", line=1),
    ],
    "notes": [], "error": None,
}


class ParseTests(unittest.TestCase):
    def test_parses_replacement_form(self):
        self.assertEqual(
            worklist.parse_deprecation(
                "Left is deprecated.  You should use String.Left instead"),
            ("Left", "String.Left"))

    def test_parses_plain_form(self):
        # The IDE's issue-type list carries "Item1 is deprecated" as its own
        # warning (id -2), separate from the use-Item2 form.
        self.assertEqual(worklist.parse_deprecation("Screen is deprecated"),
                         ("Screen", None))

    def test_parses_signature_replacement_whole(self):
        old, new = worklist.parse_deprecation(LIVE["diagnostics"][5]["message"])
        self.assertEqual(old, "GetFolderItem")
        self.assertEqual(new, "FolderItem.Constructor(path As String, "
                              "pathMode As PathModes)")

    def test_non_deprecation_messages_are_not_parsed(self):
        for msg in ("unused is an unused local variable",
                    "Old-style constructor methods are no longer supported.  "
                    'You should use "Constructor" instead',
                    "This property shadows one already defined by Window1"):
            self.assertIsNone(worklist.parse_deprecation(msg), msg)


class JoinTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.matrix = worklist.load_matrix()

    def rows_for(self, old, new):
        return worklist.match_rows(old, new, self.matrix)

    def test_replacement_disambiguates_a_bare_member(self):
        # Two rows own the bare name; only one leads to RowCount.
        rows = self.rows_for("ListCount", "RowCount")
        self.assertEqual([r["old"] for r in rows], ["ListBox.ListCount"])

    def test_replacement_disambiguates_a_global_from_a_member(self):
        rows = self.rows_for("Left", "String.Left")
        self.assertEqual([r["old"] for r in rows], ["Left"])

    def test_ide_casing_is_ignored(self):
        # The IDE spells it "Listbox"; the matrix spells it "ListBox".
        rows = self.rows_for("Listbox", "DesktopListBox")
        self.assertTrue(rows)
        self.assertTrue(any(r["old"].lower() == "listbox" for r in rows))

    def test_single_candidate_needs_no_disambiguation(self):
        rows = self.rows_for("InStr", "String.IndexOf")
        self.assertEqual([r["old"] for r in rows], ["InStr"])

    def test_unmatched_symbol_returns_nothing(self):
        self.assertEqual(self.rows_for("NotARealXojoSymbol", "Whatever"), [])

    def test_a_generic_replacement_word_still_narrows(self):
        # "String" is filler in prose but a decisive replacement name here:
        # seven rows own the bare name Text, and only one becomes String.
        rows = self.rows_for("Text", "String")
        self.assertEqual([r["old"] for r in rows], ["Text"])

    def test_ambiguity_is_reported_not_guessed(self):
        # A replacement that matches neither candidate must keep both, so the
        # caller can say "ambiguous" instead of silently picking one.
        rows = self.rows_for("ListCount", "SomethingElseEntirely")
        self.assertGreater(len(rows), 1)


class WorklistTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.wl = worklist.build(LIVE)

    def test_every_diagnostic_is_accounted_for_exactly_once(self):
        seen = ([s["message"] for g in self.wl["groups"] for s in g["sites"]]
                + [d["message"] for d in self.wl["unmatched"]]
                + [d["message"] for d in self.wl["related"]]
                + [d["message"] for d in self.wl["other"]]
                + [d["message"] for d in self.wl["errors"]])
        self.assertEqual(sorted(seen),
                         sorted(d["message"] for d in LIVE["diagnostics"]))

    def test_non_deprecation_warning_is_not_forced_through_the_matrix(self):
        self.assertEqual([d["message"] for d in self.wl["other"]],
                         ["unused is an unused local variable"])

    def test_deprecation_in_another_wording_is_not_dismissed(self):
        # Extracted from the IDE binary's own string table: the two "%1 is
        # deprecated..." templates are not the only deprecation findings it
        # writes. These four are migration work -- a Super that is a
        # deprecated class, an old-style constructor -- so filing them with
        # the unused-variable warnings under "not deprecations" is wrong.
        others = [
            "This class is based on a deprecated class. It is recommended "
            "that you update this.",
            "This control is based on a deprecated class. It is recommended "
            "that you update this.",
            "This class is using a deprecated type of constructor. It is "
            "recommended that you update this.",
            "You cannot have a Menu Bar that contains DesktopMenuItems when "
            "the project contains deprecated Windows. Convert all Windows to "
            "DesktopWindows first.",
        ]
        wl = worklist.build(dict(LIVE, diagnostics=(
            [diag(m) for m in others]
            + [diag("unused is an unused local variable")])))
        self.assertEqual([d["message"] for d in wl["related"]], others)
        self.assertEqual([d["message"] for d in wl["other"]],
                         ["unused is an unused local variable"])

    def test_instr_needs_hand_conversion(self):
        g = self.group("InStr")
        self.assertEqual(g["action"], worklist.HAND)
        # The sentinel change is the reason, and it must be quoted, not
        # merely pointed at: this is the trap the IDE's own message hides.
        self.assertTrue(any(r.get("manual") for r in g["rules"]))

    def test_listcount_is_mechanical(self):
        self.assertEqual(self.group("ListCount")["action"], worklist.MECHANICAL)

    def test_control_type_rename_is_left_to_the_converter(self):
        # ListBox -> DesktopListBox is an "IDE handles" row. Attaching the
        # category's member rules to it buried three real traps under 46
        # rules for a site that needs no source edit.
        g = self.group("Listbox")
        self.assertEqual(g["action"], worklist.CONVERTER)
        self.assertEqual(g["rules"], [])

    def test_rule_prose_does_not_attach_a_foreign_rule(self):
        # Timer.Mode -> Timer.RunMode is a correct join. c1r20 governs
        # StrComp and matched only because "mode" is one of its PARAMETER
        # names; being manual-only it then drove the whole group to the
        # top section, telling the reader to study string comparison before
        # renaming a Timer property.
        wl = worklist.build(dict(LIVE, diagnostics=[
            diag("Mode is deprecated.  You should use RunMode instead")]))
        rules = [r["id"] for g in wl["groups"] for r in g["rules"]]
        self.assertNotIn("c1r20", rules)

    def test_unknown_replacement_rows_are_ambiguous_not_agreed(self):
        # Three classes own .InsertRow and the matrix records no
        # replacement for any of them. Three identical "unknown" markers
        # are not three rows agreeing.
        wl = worklist.build(dict(LIVE, diagnostics=[
            diag("InsertRow is deprecated.  You should use AddRowAt instead")]))
        g = wl["groups"][0]
        self.assertTrue(g["ambiguous"])
        self.assertNotEqual(g["action"], worklist.MECHANICAL)

    def test_unrecorded_replacement_is_never_mechanical(self):
        # "Mechanical rename" is the one heading that says "edit without
        # reading anything", so it must never cover a row whose
        # replacement the matrix does not actually record.
        for g in worklist.build(LIVE)["groups"]:
            if g["action"] == worklist.MECHANICAL:
                for row in g["rows"]:
                    self.assertTrue(worklist.known_replacement(row),
                                    f"{g['symbol']}: {row}")

    def test_ide_suggestion_contradicting_the_matrix_is_flagged(self):
        # Verified live against Xojo 2026.2.1: the IDE really does say
        # "GridLinesHorizontal is deprecated.  You should use
        # GridLinesHorizontalStyle instead". That property exists -- on the
        # deprecated ListBox class. DesktopListBox has GridLineStyle and no
        # GridLinesHorizontalStyle, so following the IDE moves you from one
        # deprecated member to another. The disagreement must be visible.
        wl = worklist.build(dict(LIVE, diagnostics=[
            diag("GridLinesHorizontal is deprecated.  You should use "
                 "GridLinesHorizontalStyle instead")]))
        g = wl["groups"][0]
        self.assertTrue(g["ide_disagrees"])
        self.assertNotEqual(g["action"], worklist.MECHANICAL)

    def test_agreeing_suggestion_is_not_flagged(self):
        wl = worklist.build(dict(LIVE, diagnostics=[
            diag("ListCount is deprecated.  You should use RowCount instead")]))
        self.assertFalse(wl["groups"][0]["ide_disagrees"])

    def test_disagreement_is_reported_in_the_text_output(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            worklist.report(worklist.build(dict(LIVE, diagnostics=[
                diag("GridLinesHorizontal is deprecated.  You should use "
                     "GridLinesHorizontalStyle instead")])))
        text = out.getvalue()
        self.assertIn("GridLineStyle", text)
        self.assertIn("matrix", text.lower())

    def test_equivalent_rows_are_not_called_ambiguous(self):
        # Date and Xojo.Core.Date both become DateTime; there is nothing for
        # the reader to resolve.
        self.assertFalse(self.group("Date")["ambiguous"])

    def test_left_is_flagged_for_review(self):
        # c0r4 is medium: a user-defined Left(a, b) would match too.
        self.assertEqual(self.group("Left")["action"], worklist.REVIEW)

    def test_groups_are_ordered_most_dangerous_first(self):
        seen = [worklist.ACTION_ORDER.index(g["action"])
                for g in self.wl["groups"]]
        self.assertEqual(seen, sorted(seen))
        self.assertEqual(worklist.ACTION_ORDER[0], worklist.HAND)

    def test_sites_of_one_symbol_group_together(self):
        doc = dict(LIVE, diagnostics=[
            diag("Left is deprecated.  You should use String.Left instead",
                 line=3),
            diag("Left is deprecated.  You should use String.Left instead",
                 line=11, location="Window1.Opening"),
        ])
        wl = worklist.build(doc)
        self.assertEqual(len(wl["groups"]), 1)
        self.assertEqual(len(wl["groups"][0]["sites"]), 2)

    def test_unknown_deprecation_is_surfaced_not_dropped(self):
        doc = dict(LIVE, diagnostics=[
            diag("Fizzbuzzer is deprecated.  You should use Nothing instead")])
        wl = worklist.build(doc)
        self.assertEqual(len(wl["unmatched"]), 1)
        self.assertEqual(wl["groups"], [])

    def test_errors_are_separated_from_warnings(self):
        doc = dict(LIVE, diagnostics=[
            diag("Type mismatch", severity="error"),
            diag("Left is deprecated.  You should use String.Left instead")])
        wl = worklist.build(doc)
        self.assertEqual(len(wl["errors"]), 1)
        self.assertEqual(len(wl["groups"]), 1)

    def group(self, symbol):
        for g in self.wl["groups"]:
            if g["symbol"].lower() == symbol.lower():
                return g
        self.fail(f"no group for {symbol}: "
                  f"{[g['symbol'] for g in self.wl['groups']]}")


class CliTests(unittest.TestCase):
    def run_cli(self, doc, *argv):
        out, err = io.StringIO(), io.StringIO()
        code = 0
        stdin = io.StringIO(json.dumps(doc))
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                worklist.main(list(argv), stdin=stdin)
            except SystemExit as e:
                # sys.exit(str) carries its message in the exception; the
                # interpreter prints it only when it escapes to top level.
                if isinstance(e.code, int):
                    code = e.code
                else:
                    code = 1
                    err.write(str(e.code or ""))
        return code, out.getvalue(), err.getvalue()

    def test_reads_stdin_and_reports_every_symbol(self):
        code, out, _ = self.run_cli(LIVE)
        self.assertEqual(code, 0)
        for sym in ("InStr", "Left", "ListCount", "GetFolderItem", "Date"):
            self.assertIn(sym, out)
        self.assertIn("unused local variable", out)

    def test_reconciliation_line_states_the_totals(self):
        _, out, _ = self.run_cli(LIVE)
        self.assertIn("7 diagnostics", out)

    def test_json_format_round_trips(self):
        _, out, _ = self.run_cli(LIVE, "--format", "json")
        parsed = json.loads(out)
        self.assertEqual(len(parsed["groups"]) + len(parsed["unmatched"])
                         + len(parsed["other"]) + len(parsed["errors"]),
                         len({d["message"] for d in LIVE["diagnostics"]}))

    def test_rejects_a_non_analyze_document(self):
        code, _, err = self.run_cli({"nonsense": True})
        self.assertNotEqual(code, 0)
        self.assertIn("analyze", err.lower())

    def test_rejects_a_failed_analysis_instead_of_reading_it_as_clean(self):
        # xojoctl emits a JSON document on every outcome, including a
        # failed connection, and that document carries an empty
        # diagnostics list. Reporting "no deprecation warnings" for an
        # analysis that never ran is the worst answer available: it reads
        # as a finished migration.
        failed = {"schema_version": 1, "ok": False, "outcome": "connect_failed",
                  "exit_code": 2, "summary": "could not reach the IDE",
                  "counts": {"errors": 0, "warnings": 0},
                  "diagnostics": [],
                  "error": {"code": "connect_failed",
                            "message": "no IDE socket"}}
        code, out, err = self.run_cli(failed)
        self.assertNotEqual(code, 0)
        self.assertNotIn("no deprecation", out.lower())
        combined = (out + err).lower()
        self.assertIn("connect_failed", combined)
        # It must send the reader somewhere, not just stop.
        self.assertIn("scan.py", combined)

    def test_accepts_a_project_with_compile_errors(self):
        # outcome project_errors is an analysis that RAN -- the normal
        # state of a freshly converted project, whose phase-1 converter
        # renamed control types and left members behind. Refusing it
        # demotes the whole migration to the type-blind scanner; one
        # real migration had to forge ok:true past the old gate.
        broken = dict(LIVE, ok=False, outcome="project_errors",
                      exit_code=1, error=None)
        code, out, err = self.run_cli(broken)
        self.assertEqual(code, 0)
        self.assertIn("InStr", out)
        self.assertIn("project_errors", err)
        self.assertIn("worklist", err)

    def test_truncated_row_list_says_how_many_were_hidden(self):
        code, out, _ = self.run_cli(dict(LIVE, diagnostics=[
            diag("DataField is deprecated")]))
        self.assertEqual(code, 0)
        self.assertIn("2 more", out)

    def test_group_without_rules_prints_the_matrix_row_note(self):
        # The row's note is the only guidance such a group has; SKILL.md
        # calls a note "part of the answer, not decoration".
        _, out, _ = self.run_cli(dict(LIVE, diagnostics=[
            diag("AbsolutePath is deprecated")]))
        rows = worklist.match_rows("AbsolutePath", None,
                                   worklist.load_matrix())
        note = next((r.get("note") for r in rows if r.get("note")), None)
        if not note:
            self.skipTest("no noted no-rule row available in this matrix")
        self.assertIn(note.split(".")[0][:40], out)

    def test_reports_a_clean_analyze(self):
        code, out, _ = self.run_cli(dict(LIVE, diagnostics=[]))
        self.assertEqual(code, 0)
        self.assertIn("no deprecation", out.lower())

    def test_a_differently_worded_finding_is_not_called_clean(self):
        code, out, _ = self.run_cli(dict(LIVE, diagnostics=[
            diag("This class is based on a deprecated class. It is "
                 "recommended that you update this.")]))
        self.assertEqual(code, 0)
        self.assertNotIn("no deprecation", out.lower())


if __name__ == "__main__":
    unittest.main(verbosity=1)
