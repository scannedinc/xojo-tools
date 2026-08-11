#!/usr/bin/env python3
"""Consistency tests between coverage.json and the xojo skill's doc indexes.

Two layers, split by what they need:

- **Shape tests** always run. They pin the contract every consumer relies on:
  the fields lookup.py hard-indexes, the seven exact bucket strings, the
  release format, and the absence of the markup junk a 2026-08 audit found
  had been harvested into both datasets.
- **Drift tests** run only when the sibling xojo skill's generated indexes
  exist (they are gitignored build artifacts; when this skill is used
  standalone they may be absent, so these tests skip rather than fail).
  They re-run refresh_from_docs.py's joins and assert that everything the
  two datasets disagree on is a KNOWN, deliberate divergence listed here
  with its reason. A new deprecation in the docs, a backfillable date, or a
  fresh disagreement fails the test; run refresh_from_docs.py and triage.

Run:  python3 test_coverage_consistency.py
"""
import json
import pathlib
import re
import sys
import unittest

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import refresh_from_docs as R  # noqa: E402

COVERAGE = json.loads(
    (HERE.parent / "references" / "coverage.json").read_text(encoding="utf-8")
)
DOCS = HERE.parent.parent / "xojo" / "references" / "documentation"
HAVE_DOCS = (DOCS / "classes.tsv").is_file() and (DOCS / "members.tsv").is_file()

BUCKETS = {
    "Source — member", "Source — global", "Source — type", "Out of scope",
    "Removed", "IDE handles", "No replacement",
}

# The fields lookup.py indexes with row[...] on every row; a regenerated or
# hand-edited matrix must keep them present.
REQUIRED = ("old", "new", "kind", "cat", "covered", "since", "status",
            "note", "origin")

RELEASE = re.compile(r"^\d{4}r\d+(\.\d+)?$")

# Xojo's own Deprecations table lists these, while each symbol's detail page
# presents it as current with no replacement and no deprecated page exists.
# The matrix follows the table; the indexes follow the pages. Both are
# faithful readings, so the conflict stands until Xojo's docs agree with
# themselves.
STATUS_KNOWN = {"CLong", "POP3SecureSocket.MessageCount",
                "StyledTextPrinter.EOF"}

# The docs name Application.Window as the Window function's replacement, but
# that member is itself deprecated on the deprecated Application class; the
# matrix deliberately routes past it to DesktopApplication's WindowAt,
# WindowCount and Windows.
REPLACEMENT_KNOWN = {"Window"}

# Deprecations the indexes carry that the matrix deliberately omits:
# self-named overload deprecations on mobile-only surfaces (a bare-name row
# would replace a name with itself), and constructors of the long-removed
# REALbasic namespace.
CANDIDATES_KNOWN = {
    "Barcode.Image", "Picture.SystemImage",
    "Realbasic.Point.Constructor", "Realbasic.Rect.Constructor",
    "Realbasic.Size.Constructor",
}


class ShapeTests(unittest.TestCase):
    def test_every_row_has_the_fields_lookup_indexes(self):
        for row in COVERAGE:
            missing = [key for key in REQUIRED if key not in row]
            self.assertFalse(missing, f"{row.get('old')}: missing {missing}")

    def test_cat_values_are_the_seven_known_buckets(self):
        # sweep.py excludes and worklist.py routes by exact string, em dash
        # included, so a new spelling would silently change their behavior.
        for row in COVERAGE:
            self.assertIn(row["cat"], BUCKETS, row["old"])

    def test_since_is_a_release_or_empty(self):
        for row in COVERAGE:
            if row["since"]:
                self.assertRegex(row["since"], RELEASE, row["old"])

    def test_no_markup_junk_in_replacements(self):
        # The 2026-08 audit found half-converted wiki markup harvested into
        # six rows' replacements ("alpha channels]]", "<ShowIf version]]").
        # Single square brackets stay legal: Xojo signature notation writes
        # optional parameters as "([parent As DesktopWindow])".
        junk = re.compile(r"\]\]|[{}<>\\]|\bShowIf\b")
        for row in COVERAGE:
            self.assertIsNone(junk.search(row["new"]), (row["old"], row["new"]))

    def test_no_markup_junk_in_notes(self):
        # Notes legitimately carry "->" and the `Handles <Menu>.Action`
        # placeholder, so only the wiki leftovers are checked.
        junk = re.compile(r"\]\]|\}\}|\bShowIf\b")
        for row in COVERAGE:
            self.assertIsNone(junk.search(row["note"]), (row["old"], row["note"]))

    def test_no_duplicate_symbol_rows(self):
        # "Window" appears as both the class and the global method; the pair
        # (old, kind) is what has to stay unique for keyed edits to work.
        seen = set()
        for row in COVERAGE:
            key = (row["old"].lower(), row["kind"])
            self.assertNotIn(key, seen, key)
            seen.add(key)


@unittest.skipUnless(HAVE_DOCS, "xojo skill's generated indexes not built")
class DriftTests(unittest.TestCase):
    """Every disagreement with the docs must be a known, reasoned one."""

    @classmethod
    def setUpClass(cls):
        cls.indexes = R.Indexes(DOCS)
        # Work on a copy: backfill_since mutates rows in place.
        cls.coverage = json.loads(json.dumps(COVERAGE))

    def test_no_backfillable_since_dates(self):
        filled, normalized = R.backfill_since(
            self.coverage, self.indexes, R.table_dates(DOCS)
        )
        self.assertEqual(
            (filled, normalized), ([], 0),
            "the docs carry dates the matrix lacks; run refresh_from_docs.py",
        )

    def test_every_ide_imported_replacement_is_a_documented_member(self):
        rewritten, unknown = R.reverify_ide_rows(self.coverage, self.indexes)
        self.assertEqual(
            unknown, [],
            "an IDE-imported replacement is not in the member index; the row "
            "is wrong the way WebTextField.Text -> Value was",
        )
        self.assertEqual(rewritten, [], "stale confirmation sentences remain")

    def test_status_conflicts_are_the_known_doc_ambiguities(self):
        status, _ = R.report_disagreements(self.coverage, self.indexes)
        self.assertEqual({old for old, _ in status}, STATUS_KNOWN)

    def test_replacement_disagreements_are_the_known_divergences(self):
        _, replacement = R.report_disagreements(self.coverage, self.indexes)
        self.assertEqual({old for old, _, _ in replacement}, REPLACEMENT_KNOWN)

    def test_new_docs_deprecations_reach_the_matrix_or_this_list(self):
        candidates = R.report_candidates(self.coverage, self.indexes)
        self.assertEqual({name for name, _, _ in candidates}, CANDIDATES_KNOWN)


if __name__ == "__main__":
    unittest.main(verbosity=1)
