#!/usr/bin/env python3
"""Tests for enrich_from_ide_db.py (stdlib only, Python 3.9+).

The tool writes into shipped data, so the tests pin the rules that keep the
import conservative: a replacement is imported only when the API 2 class
documents it, an answer we already have is never overwritten, and the
database chosen is the newest one that actually opens.

Run:  python3 test_enrich_from_ide_db.py
"""
import pathlib
import shutil
import sqlite3
import sys
import tempfile
import unittest

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import enrich_from_ide_db as E  # noqa: E402


def make_db(path, items=(), events=(), classes=()):
    con = sqlite3.connect(str(path))
    con.execute("create table items (class_name, old_name, new_name)")
    con.execute("create table classes (id integer primary key, name, super)")
    con.execute("create table events (class_id, old_name, new_name)")
    con.executemany("insert into items values (?,?,?)", items)
    con.executemany("insert into classes values (?,?,?)", classes)
    con.executemany("insert into events values (?,?,?)", events)
    con.commit()
    con.close()
    return path


class FakeDocs:
    """Stands in for the documentation mirror: {class: {members}}."""

    def __init__(self, pages):
        self.pages = {k.lower(): {m.lower() for m in v}
                      for k, v in pages.items()}

    def has(self, cls, member):
        page = self.pages.get(cls.lower())
        if page is None:
            return None
        return E.bare_name(member) in page


def row(old, new, cat="Source — member"):
    return {"old": old, "new": new, "kind": "—", "cat": cat, "covered": False,
            "since": "", "status": "Deprecated", "note": "", "origin": "member"}


class BareNameTests(unittest.TestCase):
    def test_strips_signatures_and_return_types(self):
        for text, want in (
                ("Activated()", "activated"),
                ("CancelClosing() As Boolean", "cancelclosing"),
                ("Pressed(button As ToolbarItem)", "pressed"),
                ("DesktopListBox.RowCount", "rowcount"),
                ("BevelStyle", "bevelstyle"),
        ):
            self.assertEqual(E.bare_name(text), want, text)

    def test_empty_for_nonsense(self):
        self.assertEqual(E.bare_name(""), "")
        self.assertEqual(E.bare_name("()"), "")


class PlanTests(unittest.TestCase):
    def setUp(self):
        self.coverage = [
            row("ListBox", "DesktopListBox", cat="IDE handles"),
            row("ListBox.GridLinesHorizontal", "DesktopListBox.GridLineStyle"),
            row("ListBox.Bevel", "—"),
        ]
        self.docs = FakeDocs({
            "DesktopListBox": {"GridLineStyle", "BevelStyle", "RowCount"},
        })

    def plan(self, rows):
        return E.plan(self.coverage, rows, self.docs, "TestRelease")

    def test_blank_row_is_filled_from_the_database(self):
        fills, adds, rejects = self.plan([("ListBox", "Bevel", "BevelStyle",
                                           "member")])
        self.assertEqual(len(fills), 1)
        self.assertEqual((adds, rejects), ([], []))
        self.assertEqual(fills[0][3], "BevelStyle")

    def test_existing_answer_is_never_overwritten(self):
        # This is the GridLines case: the IDE proposes a member of the
        # DEPRECATED class, and the matrix already holds the API 2 answer.
        fills, adds, rejects = self.plan([
            ("ListBox", "GridLinesHorizontal", "GridLinesHorizontalStyle",
             "member")])
        self.assertEqual((fills, adds), ([], []))
        self.assertEqual(len(rejects), 1)
        self.assertIn("GridLinesHorizontalStyle", rejects[0]["new"])

    def test_replacement_absent_from_the_api2_class_is_rejected(self):
        fills, adds, rejects = self.plan([("ListBox", "DoubleClick",
                                           "DoubleClicked", "member")])
        self.assertEqual((fills, adds), ([], []))
        self.assertEqual(rejects[0]["target"], "DesktopListBox")

    def test_unknown_destination_class_is_rejected_not_guessed(self):
        fills, adds, rejects = self.plan([("Mystery", "Foo", "Bar", "member")])
        self.assertEqual((fills, adds), ([], []))
        self.assertIn("no documentation page", rejects[0]["why"])

    def test_new_pair_is_added(self):
        fills, adds, rejects = self.plan([("ListBox", "ListCount", "RowCount",
                                           "member")])
        self.assertEqual((fills, rejects), ([], []))
        built = E.build_row(*adds[0])
        self.assertEqual(built["old"], "ListBox.ListCount")
        self.assertEqual(built["new"], "DesktopListBox.RowCount")
        self.assertEqual(built["src"], E.SRC)


class BuildRowTests(unittest.TestCase):
    def test_web_rows_are_out_of_scope(self):
        built = E.build_row("WebButton", "Caption", "Text", "WebButton",
                            "member", "r")
        self.assertEqual(built["cat"], "Out of scope")

    def test_desktop_events_are_converter_work(self):
        built = E.build_row("Window", "Open", "Opening()", "DesktopWindow",
                            "event", "r")
        self.assertEqual(built["cat"], "IDE handles")
        self.assertEqual(built["kind"], "Event")

    def test_event_note_carries_the_menu_handler_hazard(self):
        built = E.build_row("MenuItem", "Action", "MenuItemSelected()",
                            "DesktopMenuItem", "event", "r")
        self.assertIn("Handles", built["note"])
        self.assertIn(".Action", built["note"])

    def test_member_rows_are_source_work(self):
        built = E.build_row("BevelButton", "Bevel", "BevelStyle",
                            "DesktopBevelButton", "member", "r")
        self.assertEqual(built["cat"], "Source — member")
        self.assertEqual(built["kind"], "Property")


class FindDbTests(unittest.TestCase):
    def setUp(self):
        self.dir = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.dir)

    def test_usable_rejects_a_file_that_is_not_a_database(self):
        bad = self.dir / "bad.db"
        bad.write_bytes(b"\xc3\xf4not sqlite at all")
        self.assertFalse(E.usable(bad))

    def test_usable_rejects_a_database_without_the_items_table(self):
        empty = sqlite3.connect(str(self.dir / "empty.db"))
        empty.execute("create table something (x)")
        empty.commit()
        empty.close()
        self.assertFalse(E.usable(self.dir / "empty.db"))

    def test_usable_accepts_a_real_one(self):
        self.assertTrue(E.usable(make_db(self.dir / "ok.db",
                                         items=[("A", "b", "c")])))

    def install(self, root, folder, app, content=None):
        d = root / folder / f"{app}.app" / "Contents" / "Resources"
        d.mkdir(parents=True)
        target = d / "deprecation_cache.db"
        if content is None:
            make_db(target, items=[("A", "b", "c")])
        else:
            target.write_bytes(content)
        return target

    def find_in(self, root):
        original = E.XOJO_APPS
        E.XOJO_APPS = root
        try:
            return E.find_db()
        finally:
            E.XOJO_APPS = original

    def test_highest_version_wins_over_a_later_folder_name(self):
        # Folder names under /Applications/Xojo are the user's own
        # numbering, not Xojo versions: "Xojo 79 (2019R3.2)" sorts after
        # "Xojo 2026.2.1" as a string while being seven years older.
        root = self.dir / "Applications"
        self.install(root, "Xojo 79", "Xojo 79 (2019R3.2)")
        self.install(root, "Xojo 2026.2.1.67756", "Xojo 2026.2.1.67756")
        self.assertIn("2026.2.1", str(self.find_in(root)))

    def test_unreadable_newest_falls_back_to_the_next_usable(self):
        root = self.dir / "Applications"
        self.install(root, "Xojo 156", "Xojo 156 (2026.2)",
                     content=b"not a database")
        self.install(root, "Xojo 148", "Xojo 148 (2025.2.1)")
        self.assertIn("2025.2.1", str(self.find_in(root)))


class ParseVersionTests(unittest.TestCase):
    def test_reads_both_release_spellings(self):
        for path, want in (
                ("/Applications/Xojo/Xojo 138 (2024.4.2)/x.app", (2024, 4, 2)),
                ("/Applications/Xojo/Xojo 156 (2026.2)/x.app", (2026, 2, 0)),
                ("/Applications/Xojo/Xojo 2026.2.1.67756/x.app", (2026, 2, 1)),
                ("/Applications/Xojo/Xojo 79 (2019R3.2)/x.app", (2019, 3, 2)),
                ("/Applications/Xojo/Xojo 66 (2018R3)/x.app", (2018, 3, 0)),
        ):
            self.assertEqual(E.parse_version(path), want, path)

    def test_private_folder_numbering_is_not_read_as_a_version(self):
        # "Xojo <n>" for n under 2000 is a private install number, never a
        # release. A version always begins with its four-digit year.
        for n in (66, 73, 79, 138, 148, 156, 1999):
            self.assertIsNone(E.parse_version(f"/Applications/Xojo/Xojo {n}/x.app"),
                              n)

    def test_orders_releases_correctly(self):
        order = [E.parse_version(p) for p in (
            "Xojo 66 (2018R3)", "Xojo 79 (2019R3.2)", "Xojo 138 (2024.4.2)",
            "Xojo 156 (2026.2)", "Xojo 2026.2.1.67756")]
        self.assertEqual(order, sorted(order))


if __name__ == "__main__":
    unittest.main(verbosity=1)
