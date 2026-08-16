#!/usr/bin/env python3
"""Tests for docs.py (stdlib only, Python 3.9+).

What they pin:

- prune_stale deletes only generated pages the build no longer produces:
  current pages and non-.md files survive, and subdirectories emptied by
  the pruning are removed with their files
- prune_stale never unlinks a directory that merely ends in .md, and
  compares membership casefolded, so a case-only docname change never
  deletes the live page on a case-insensitive filesystem
- run_build prunes only from a complete build: a stale page goes when
  every inventory page was converted, and survives when sources are
  missing or the inventory yields no pages at all (the mass-deletion
  gates)

Run:  python3 test_docs.py
"""
import argparse
import contextlib
import io
import pathlib
import shutil
import tempfile
import unittest
import zlib
from unittest import mock

import docs


class PruneStaleTests(unittest.TestCase):
    def setUp(self):
        self.dir = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.dir)

    def seed(self, relative):
        path = self.dir / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("x", encoding="utf-8")
        return path

    def test_stale_pages_go_and_everything_else_survives(self):
        page = self.seed("api/listbox.md")
        members = self.seed("api/listbox.members.md")
        stale = self.seed("api/deprecated/window.md")
        stale_members = self.seed("api/deprecated/window.members.md")
        index = self.seed("classes.tsv")
        junk = self.seed("api/.DS_Store")

        pruned = docs.prune_stale(self.dir, {page, members})

        self.assertEqual(pruned, 2)
        self.assertTrue(page.exists())
        self.assertTrue(members.exists())
        self.assertFalse(stale.exists())
        self.assertFalse(stale_members.exists())
        self.assertTrue(index.exists())
        self.assertTrue(junk.exists())

    def test_emptied_directories_are_removed(self):
        kept = self.seed("api/current.md")
        self.seed("api/deprecated/old/window.md")

        pruned = docs.prune_stale(self.dir, {kept})

        self.assertEqual(pruned, 1)
        # deprecated/ held nothing but the emptied old/, so both go.
        self.assertFalse((self.dir / "api/deprecated").exists())
        self.assertTrue((self.dir / "api").is_dir())

    def test_directory_named_like_a_page_is_left_alone(self):
        # A hostile docname like api/foo.md/bar creates a *directory* named
        # foo.md; rglob("*.md") yields it, and unlink() on it would raise.
        kept = self.seed("api/current.md")
        inside = self.seed("api/foo.md/keep.txt")

        pruned = docs.prune_stale(self.dir, {kept})

        self.assertEqual(pruned, 0)
        self.assertTrue((self.dir / "api/foo.md").is_dir())
        self.assertTrue(inside.exists())

    def test_casefold_differing_current_page_survives(self):
        # An upstream case change (Foo -> foo) leaves the on-disk file at its
        # old case on a case-insensitive filesystem, while expected carries
        # the new one; the page is current and must not be deleted. On a
        # case-sensitive filesystem the file is merely retained as stale.
        on_disk = self.seed("api/Listbox.md")

        pruned = docs.prune_stale(self.dir, {self.dir / "api/listbox.md"})

        self.assertEqual(pruned, 0)
        self.assertTrue(on_disk.exists())


class RunBuildPruneGateTests(unittest.TestCase):
    """The mass-deletion gates, end to end through run_build.

    Each test builds a two-page mirror -- a real objects.inv (four header
    lines, then zlib-compressed std:doc records, the shape
    parse_inventory_labels reads) plus the matching _sources/*.rst.txt
    files -- and pre-seeds dest with a stale page the inventory no longer
    lists.
    """

    DOCNAMES = ("api/listbox", "api/window")

    def setUp(self):
        self.dir = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.dir)
        self.source = self.dir / "mirror"
        self.dest = self.dir / "references"
        (self.source / "_sources").mkdir(parents=True)
        # The repo's real override file must not leak rows into the fixture.
        patcher = mock.patch.object(docs, "OVERRIDES", self.dir / "no-overrides.tsv")
        patcher.start()
        self.addCleanup(patcher.stop)

    def write_inventory(self, docnames):
        header = (
            b"# Sphinx inventory version 2\n"
            b"# Project: Test\n"
            b"# Version: 1\n"
            b"# The remainder of this file is compressed using zlib.\n"
        )
        records = "".join(
            f"{name} std:doc -1 {name}.html -\n" for name in docnames
        )
        (self.source / "objects.inv").write_bytes(
            header + zlib.compress(records.encode("utf-8"))
        )

    def write_source(self, docname):
        path = self.source / "_sources" / f"{docname}.rst.txt"
        path.parent.mkdir(parents=True, exist_ok=True)
        title = docname.rsplit("/", 1)[-1]
        path.write_text(
            f"{title}\n{'=' * len(title)}\n\nA page.\n", encoding="utf-8"
        )

    def build(self):
        args = argparse.Namespace(
            source=str(self.source), dest=str(self.dest), include_all=False
        )
        with contextlib.redirect_stdout(io.StringIO()), \
                contextlib.redirect_stderr(io.StringIO()):
            return docs.run_build(args)

    def seed_stale(self, relative="api/old.md"):
        path = self.dest / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("stale\n", encoding="utf-8")
        return path

    def test_complete_build_prunes_the_stale_page(self):
        self.write_inventory(self.DOCNAMES)
        for docname in self.DOCNAMES:
            self.write_source(docname)
        stale = self.seed_stale()

        self.assertEqual(self.build(), 0)

        self.assertFalse(stale.exists())
        for docname in self.DOCNAMES:
            self.assertTrue((self.dest / f"{docname}.md").is_file())

    def test_missing_source_disables_pruning(self):
        self.write_inventory(self.DOCNAMES)
        self.write_source("api/listbox")  # api/window is absent
        stale = self.seed_stale()

        self.assertEqual(self.build(), 0)

        self.assertTrue(stale.exists())
        self.assertTrue((self.dest / "api/listbox.md").is_file())

    def test_hollow_inventory_disables_pruning(self):
        # Valid zlib, zero parseable pages: absent stays empty too, so only
        # the not-pages gate stands between this and deleting everything.
        self.write_inventory(())
        stale = self.seed_stale()
        other = self.seed_stale("api/listbox.md")

        self.assertEqual(self.build(), 0)

        self.assertTrue(stale.exists())
        self.assertTrue(other.exists())


if __name__ == "__main__":
    unittest.main(verbosity=1)
