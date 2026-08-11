#!/usr/bin/env python3
"""Tests for scan.py's token prefilter (stdlib only, Python 3.9+).

The scanner's hot loop runs every compiled pattern (~950) against every
file. Both pattern shapes embed a literal ASCII identifier -- `\\.Member\\b`
and `(?<![\\w.])Name\\b` -- so a single identifier-tokenizing pass over the
file gives a necessary condition for any pattern to match: its identifier
must appear as a token. These tests pin the two properties that make the
prefilter safe to trust:

  1. Equivalence: prefiltered scanning returns byte-for-byte the same hits,
     in the same order, as scanning with every pattern -- over a synthetic
     corpus that exercises every shipped key, over adversarial boundary
     cases, and over the repo's own fixture projects.
  2. Completeness of the index: every pattern key is either reachable
     through a token or listed in the always-run residual, so a future
     non-identifier key degrades to the old behavior instead of silently
     never matching.

Run:  python3 test_scan.py
"""
import json
import pathlib
import re
import sys
import tempfile
import unittest

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import scan  # noqa: E402

REFS = HERE.parent / "references"
# Fixture projects live in the xojo docs skill; when this skill is used
# standalone they may be absent, so tests over them skip rather than fail.
FIXTURES = HERE.parent.parent / "xojo" / "references" / "projects"

IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")


def shipped_patterns():
    coverage = json.loads((REFS / "coverage.json").read_text(encoding="utf-8"))
    rules = json.loads((REFS / "rules.json").read_text(encoding="utf-8"))
    return scan.build_patterns(coverage, rules)


class CountingRegex:
    """Wraps a compiled regex, counting findall calls through a shared cell."""

    def __init__(self, rx, cell):
        self._rx = rx
        self._cell = cell

    def findall(self, text):
        self._cell[0] += 1
        return self._rx.findall(text)


def counting_patterns(pats, cell):
    return {key: (CountingRegex(rx, cell), is_member, rows)
            for key, (rx, is_member, rows) in pats.items()}


class PrefilterIndexTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pats = shipped_patterns()
        cls.prefilter = scan.build_prefilter(cls.pats)

    def test_every_key_is_indexed_or_residual(self):
        by_token, residual = self.prefilter
        indexed = [k for keys in by_token.values() for k in keys]
        every = indexed + list(residual)
        self.assertEqual(sorted(every), sorted(self.pats),
                         "each pattern key must appear exactly once across "
                         "the token index and the residual")

    def test_residual_holds_only_non_identifier_keys(self):
        by_token, residual = self.prefilter
        for key in residual:
            self.assertIsNone(IDENTIFIER.match(key.lstrip(".")),
                              f"identifier key {key!r} belongs in the token "
                              f"index, not the residual")
        # Today every shipped key is a plain identifier; if this ever grows,
        # the residual still scans unconditionally, but flag the growth.
        self.assertEqual(list(residual), [])

    def test_tokens_are_lowercase_identifiers(self):
        by_token, _ = self.prefilter
        for token in by_token:
            self.assertEqual(token, token.lower())
            self.assertIsNotNone(IDENTIFIER.match(token))


class CandidateKeysTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pats = shipped_patterns()
        cls.prefilter = scan.build_prefilter(cls.pats)

    def test_member_token_yields_member_key(self):
        cand = scan.candidate_keys("Me.lstItems.ListCount = 5\n", self.prefilter)
        self.assertIn(".listcount", cand)

    def test_global_token_yields_global_key(self):
        cand = scan.candidate_keys("i = UBound(arr)\n", self.prefilter)
        self.assertIn("ubound", cand)

    def test_case_insensitive(self):
        cand = scan.candidate_keys("X.LISTCOUNT\n", self.prefilter)
        self.assertIn(".listcount", cand)

    def test_unknown_tokens_yield_only_residual(self):
        _, residual = self.prefilter
        cand = scan.candidate_keys("zzz = qqq9 + _wobble\n", self.prefilter)
        self.assertEqual(cand, set(residual))

    def test_residual_key_is_always_candidate(self):
        # No shipped key lands in the residual, so pin its contract with a
        # synthetic pattern: a non-identifier key must always be a candidate
        # and must scan equivalently in both modes.
        pats = dict(self.pats)
        pats["&h"] = (re.compile(r"&h[0-9A-Fa-f]+", re.I), False, [])
        prefilter = scan.build_prefilter(pats)
        self.assertIn("&h", prefilter[1])
        self.assertIn("&h", scan.candidate_keys("nothing here\n", prefilter))
        text = "v = &hFF\n"
        self.assertEqual(scan.scan_text(text, pats),
                         scan.scan_text(text, pats, prefilter))
        self.assertEqual(scan.scan_text(text, pats, prefilter).get("&h"), (1, 1, 0))


class EquivalenceTests(unittest.TestCase):
    """Brute-force and prefiltered scans must be indistinguishable."""

    @classmethod
    def setUpClass(cls):
        cls.pats = shipped_patterns()
        cls.prefilter = scan.build_prefilter(cls.pats)

    def assert_equivalent(self, text):
        brute = scan.scan_text(text, self.pats)
        fast = scan.scan_text(text, self.pats, self.prefilter)
        self.assertEqual(brute, fast)
        # Same insertion order too: report assembly and JSON output follow
        # dict order, so order equality is part of "output is unchanged".
        self.assertEqual(list(brute), list(fast))

    def test_synthetic_corpus_every_shipped_key(self):
        # One line per key, case-mangled on rotation, so every pattern gets
        # the chance to disagree with its prefilter token.
        lines = []
        for i, key in enumerate(self.pats):
            name = key.lstrip(".")
            name = (name, name.upper(), name.lower())[i % 3]
            if key.startswith("."):
                lines.append(f"  v = obj.{name}(1)\n")
            else:
                lines.append(f"  v = {name}(1)\n")
        self.assert_equivalent("".join(lines))

    def test_synthetic_corpus_inside_masked_regions(self):
        # The second findall runs over code_only() output; force raw and
        # in-code counts to diverge so both paths are compared.
        sample = [k for k in self.pats if k.startswith(".")][:25]
        globals_ = [k for k in self.pats if not k.startswith(".")][:25]
        lines = ["#tag Note\n"]
        lines += [f"  archived: x.{k.lstrip('.')} and {g}\n"
                  for k, g in zip(sample, globals_)]
        lines += ["#tag EndNote\n"]
        lines += [f"  ' comment mentioning x.{k.lstrip('.')}\n" for k in sample]
        lines += [f'  s = "literal {g}"\n' for g in globals_]
        lines += [f"  v = obj{k}(1) + {g}(2)\n" for k, g in zip(sample, globals_)]
        self.assert_equivalent("".join(lines))

    def test_boundary_traps(self):
        cases = [
            "x.ListCount2 = 1\n",          # digit suffix defeats \b
            "PreListCount = 1\n",          # prefixed identifier
            "x_ListCount = 1\n",           # underscore-joined
            "A.B.Mid(1)\n",                # chained receiver
            "foo.Mid☃\n",             # non-word right neighbor: MATCHES
            "foo.Midé\n",             # word-class non-ASCII right
                                           # neighbor: Unicode \b fails, so
                                           # this must NOT match
            "éMid(x)\n",              # non-ASCII left neighbor: the
                                           # lookbehind rejects it
            "x.Mid_(1)\n",                 # trailing underscore defeats \b
            'msg = "UBound in a string"\n',
        ]
        for text in cases:
            with self.subTest(text=text):
                self.assert_equivalent(text)
        # Spot-check the two non-obvious expectations directly, so the trap
        # tests cannot both pass by matching nothing.
        hits = scan.scan_text("foo.Mid☃\n", self.pats, self.prefilter)
        self.assertEqual(hits.get(".mid"), (1, 1, 0))
        hits = scan.scan_text("éMid(x)\n", self.pats, self.prefilter)
        self.assertNotIn("mid", hits)

    def test_case_fold_impostors(self):
        # re.IGNORECASE folds exactly four non-ASCII codepoints onto ASCII
        # letters (U+0130 İ and U+0131 ı match i, U+017F ſ matches s, U+212A
        # Kelvin K matches k), so a pattern can match an identifier spelled
        # with one of them -- a span the ASCII tokenizer never emits as the
        # bare name. Failing-first pins for the fold-before-tokenize fix.
        cases = [
            "v = obj.Mıd(1)\n",        # dotless i, member shape
            "x.MİD = 1\n",             # dotted capital I
            "n = Inſtr(hay, pin)\n",   # long s, global shape
            "x = s.Inſtr(pin)\n",      # long s, member shape
            "c = bg.BacKColor\n",      # Kelvin sign
        ]
        for text in cases:
            with self.subTest(text=text):
                self.assert_equivalent(text)
        # The traps must genuinely match brute-force, or the equivalence
        # checks above could pass with both sides empty.
        hits = scan.scan_text("v = obj.Mıd(1)\n", self.pats)
        self.assertEqual(hits.get(".mid"), (1, 1, 0))
        hits = scan.scan_text("n = Inſtr(hay, pin)\n", self.pats)
        self.assertEqual(hits.get("instr"), (1, 1, 0))

    def test_fixture_projects(self):
        if not FIXTURES.is_dir():
            self.skipTest(f"fixture projects not present at {FIXTURES}")
        files = sorted(FIXTURES.rglob("*.xojo_code"))
        if not files:
            self.skipTest("no .xojo_code fixtures found")
        for f in files:
            with self.subTest(file=f.name):
                self.assert_equivalent(
                    f.read_text(encoding="utf-8", errors="replace"))


class ConditionalOnlyTests(unittest.TestCase):
    def test_only_target_constructs_survive(self):
        code = ("a = Left(s, 1)\n"
                "#if TargetWindows\n"
                "b = Left(s, 2)\n"
                "#else\n"
                "c = Left(s, 3)\n"
                "#endif\n"
                "#if DebugBuild\n"
                "d = Left(s, 4)\n"
                "#endif\n")
        lines = scan.conditional_only(code).splitlines()
        self.assertEqual(lines[0].strip(), "")       # outside any construct
        self.assertIn("Left(s, 2)", lines[2])        # the Target branch
        self.assertIn("Left(s, 3)", lines[4])        # its #else counts too
        self.assertEqual(lines[7].strip(), "")       # DebugBuild is not platform

    def test_elseif_target_marks_the_rest_of_the_construct(self):
        code = ("#if DebugBuild\n"
                "a = 1\n"
                "#elseif TargetWindows\n"
                "b = Left(s, 1)\n"
                "#endif\n")
        lines = scan.conditional_only(code).splitlines()
        self.assertEqual(lines[1].strip(), "")
        self.assertIn("Left(s, 1)", lines[3])

    def test_directive_lines_are_kept(self):
        # `#if TargetCocoa` is itself a deprecated-symbol hit.
        code = "#if TargetCocoa\nx = 1\n#endif\n"
        self.assertIn("TargetCocoa", scan.conditional_only(code))

    def test_single_line_if_does_not_touch_the_stack(self):
        # Xojo's one-line form (`#If cond Then code`) has no #EndIf, so
        # pushing it would poison the tagging for the rest of the file --
        # and a one-line `#If DebugBuild Then Break` inside a block would
        # steal the block's #EndIf.
        code = ("#If TargetWindows Then DoWindowsThing\n"
                "a = Left(s, 1)\n"
                "#if TargetMacOS\n"
                "#If DebugBuild Then Break\n"
                "b = Left(s, 2)\n"
                "#endif\n"
                "c = Left(s, 3)\n")
        lines = scan.conditional_only(code).splitlines()
        self.assertIn("TargetWindows", lines[0])   # the one-liner itself
        self.assertEqual(lines[1].strip(), "")     # next line is NOT tagged
        self.assertIn("Break", lines[3])           # inside a Target block
        self.assertIn("Left(s, 2)", lines[4])
        self.assertEqual(lines[6].strip(), "")     # the #endif still closed

    def test_scan_text_counts_conditional_hits(self):
        pats = shipped_patterns()
        pre = scan.build_prefilter(pats)
        text = ("s = Left(t, 1)\n"
                "#if TargetWindows\n"
                "u = Left(t, 2)\n"
                "#endif\n")
        agg = [v for k, v in scan.scan_text(text, pats, pre).items()
               if k.lstrip(".").lower() == "left"]
        self.assertTrue(any(v[1] >= 2 and v[2] == 1 for v in agg),
                        f"expected one of two Left hits flagged: {agg}")


class OrphanedTests(unittest.TestCase):
    def test_spaced_basenames_are_referenced_not_orphaned(self):
        # "Build Automation.xojo_code" is referenced via a BuildSteps=
        # field; the token regex alone cannot span the space, and any
        # spaced filename was misreported as unreferenced.
        with tempfile.TemporaryDirectory() as d:
            root = pathlib.Path(d)
            plain = root / "Window1.xojo_code"
            spaced = root / "Build Automation.xojo_code"
            dead = root / "OldStuff.xojo_code"
            for p in (plain, spaced, dead):
                p.write_text("", encoding="utf-8")
            manifest = root / "P.xojo_project"
            manifest.write_text(
                "Class=Window1;Window1.xojo_code;&h1234\n"
                "BuildSteps=Build Automation.xojo_code;&h5678\n",
                encoding="utf-8")
            stale = scan.orphaned([plain, spaced, dead], [manifest], root)
            self.assertEqual([p.name for p in stale], ["OldStuff.xojo_code"])


class WorkAvoidanceTests(unittest.TestCase):
    """The point of the prefilter: patterns without a token never run."""

    @classmethod
    def setUpClass(cls):
        cls.pats = shipped_patterns()
        cls.prefilter = scan.build_prefilter(cls.pats)

    def test_no_tokens_no_regex_calls(self):
        cell = [0]
        counted = counting_patterns(self.pats, cell)
        scan.scan_text("nothing = relevant_here9\n", counted, self.prefilter)
        self.assertEqual(cell[0], 0)

    def test_brute_force_runs_every_pattern(self):
        cell = [0]
        counted = counting_patterns(self.pats, cell)
        scan.scan_text("nothing = relevant_here9\n", counted)
        self.assertEqual(cell[0], len(self.pats))

    def test_one_token_runs_only_its_patterns(self):
        by_token, residual = self.prefilter
        expected = len(by_token.get("ubound", [])) + len(residual)
        cell = [0]
        counted = counting_patterns(self.pats, cell)
        hits = scan.scan_text("i = UBound(arr)\n", counted, self.prefilter)
        # findall runs once over raw text per candidate, plus once over the
        # masked text per candidate that hit, plus once over the
        # platform-conditional mask per candidate that hit in code.
        in_code = sum(1 for v in hits.values() if v[1])
        self.assertEqual(cell[0], expected + len(hits) + in_code)
        self.assertIn("ubound", hits)


if __name__ == "__main__":
    unittest.main(verbosity=1)
