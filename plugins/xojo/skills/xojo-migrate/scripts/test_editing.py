#!/usr/bin/env python3
"""Tests for editing.py, the shared machinery of the source-editing scripts.

These pin the three behaviors every editor leans on: balanced-paren call
parsing that cannot be fooled by strings, the hard-rule-3 receiver test,
and file IO that round-trips bytes which are not valid UTF-8 -- the
draft tooling read with errors="replace" and silently wrote U+FFFD into
the user's source (stdlib only, Python 3.9+).

Run:  python3 test_editing.py
"""
import os
import pathlib
import shutil
import stat
import sys
import tempfile
import unittest

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import editing  # noqa: E402


class FindCallTests(unittest.TestCase):
    def test_simple_span(self):
        line = "x = Len(name) + 1"
        self.assertEqual(editing.find_call(line, 4), (7, 12))

    def test_nested_call(self):
        line = "n = InStr(Mid(s, i, 1), t)"
        self.assertEqual(editing.find_call(line, 4), (9, 25))

    def test_paren_inside_string_ignored(self):
        # The ( in the literal must not open a depth level.
        line = 'r = Fn(s, "a(b", c)'
        self.assertEqual(editing.find_call(line, 4), (6, 18))

    def test_doubled_quote_escape(self):
        # Xojo escapes a quote by doubling it; the string does not end at
        # the doubled quote, so the paren inside it stays invisible.
        line = 'r = Fn("say ""(""", x)'
        self.assertEqual(editing.find_call(line, 4), (6, 21))

    def test_unbalanced_returns_none(self):
        # A call continued on the next line must be reported, not guessed.
        self.assertIsNone(editing.find_call("r = Fn(a, b,", 4))

    def test_no_paren_returns_none(self):
        self.assertIsNone(editing.find_call("r = Fn", 4))


class SplitArgsTests(unittest.TestCase):
    def test_top_level_commas_only(self):
        self.assertEqual(
            [a.strip() for a in editing.split_args('s, "a,b", f(x, y)')],
            ["s", '"a,b"', "f(x, y)"],
        )

    def test_single_argument(self):
        self.assertEqual(editing.split_args("s"), ["s"])

    def test_doubled_quote_inside_argument(self):
        self.assertEqual(
            [a.strip() for a in editing.split_args('"a""b", c')],
            ['"a""b"', "c"],
        )


class LegalReceiverTests(unittest.TestCase):
    def test_legal_forms(self):
        for expr in ("s", "a.b", "f(x)", "f(x).g", "a(i).b(j)",
                     "Pad(s, 4).Split(d)", "f.Child(\"x\").Name",
                     "s.Trim.Uppercase",
                     # a paren or quote inside a string argument is not
                     # grammar -- this receiver compiles fine
                     'NthField(s, "(", 1)', 'f("a""b").Name'):
            self.assertTrue(editing.legal_receiver(expr), expr)

    def test_illegal_forms(self):
        # A string literal and a parenthesised expression are syntax
        # errors as receivers (hard rule 3); bare operators are not
        # receivers either.
        for expr in ('"literal"', '("00" + Hex(r))', "a + b", "", "  ",
                     "1x"):
            self.assertFalse(editing.legal_receiver(expr), expr)


class SourceIOTests(unittest.TestCase):
    def setUp(self):
        self.dir = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.dir)

    def test_invalid_utf8_round_trips_byte_for_byte(self):
        raw = b"Dim s As String\r\ns = \"caf\xe9\"\n' tail\n"
        p = self.dir / "Legacy.xojo_code"
        p.write_bytes(raw)
        text = editing.read_source(p)
        editing.write_source(p, text)
        self.assertEqual(p.read_bytes(), raw)

    def test_no_part_sibling_survives_a_successful_write(self):
        p = self.dir / "Legacy.xojo_code"
        p.write_bytes(b"x = 1\n")
        editing.write_source(p, "x = 2\n")
        self.assertEqual(list(self.dir.iterdir()), [p])

    @unittest.skipUnless(os.name == "posix", "POSIX permission bits")
    def test_permission_bits_survive_the_rewrite(self):
        for mode in (0o600, 0o755):
            p = self.dir / f"m{mode:o}.xojo_code"
            p.write_bytes(b"x = 1\n")
            p.chmod(mode)
            editing.write_source(p, "x = 2\n")
            self.assertEqual(stat.S_IMODE(p.stat().st_mode), mode,
                             oct(mode))

    @unittest.skipUnless(os.name == "posix", "symlinks")
    def test_writing_through_a_symlink_keeps_the_link(self):
        target = self.dir / "Real.xojo_code"
        target.write_bytes(b"x = 1\n")
        link = self.dir / "Link.xojo_code"
        link.symlink_to(target)
        editing.write_source(link, "x = 2\n")
        self.assertTrue(link.is_symlink())
        self.assertEqual(target.read_bytes(), b"x = 2\n")

    @unittest.skipUnless(os.name == "posix", "POSIX permission bits")
    def test_read_only_file_is_refused_not_replaced(self):
        # os.replace needs only directory write permission, so without
        # the explicit check a write-protected file would be edited.
        p = self.dir / "Legacy.xojo_code"
        p.write_bytes(b"x = 1\n")
        p.chmod(0o444)
        with self.assertRaises(PermissionError):
            editing.write_source(p, "x = 2\n")
        self.assertEqual(p.read_bytes(), b"x = 1\n")
        self.assertEqual(list(self.dir.iterdir()), [p])

    def test_failed_replace_leaves_the_original_and_no_part(self):
        # The point of the .part dance: the old open("w") truncated the
        # file before writing, so any failure lost the user's source.
        p = self.dir / "Legacy.xojo_code"
        p.write_bytes(b"x = 1\n")

        def boom(src, dst):
            raise OSError("simulated replace failure")

        real_replace = os.replace
        os.replace = boom
        self.addCleanup(setattr, os, "replace", real_replace)
        with self.assertRaises(OSError):
            editing.write_source(p, "x = 2\n")
        os.replace = real_replace
        self.assertEqual(p.read_bytes(), b"x = 1\n")
        self.assertEqual(list(self.dir.iterdir()), [p])


class MaskedPairsTests(unittest.TestCase):
    TEXT = (
        "#tag Note, Name = Old\n"
        "Len(archived)\n"
        "#tag EndNote\n"
        'x = Len(s) // Len(comment)\n'
        's = "Len(a)"\n'
        "Begin DesktopWindow Win\n"
        "   Left = 110\n"
        "End\n"
    )

    def test_alignment_and_length(self):
        pairs = editing.masked_pairs(self.TEXT)
        self.assertEqual(len(pairs), 9)  # trailing \n yields a final ""
        for real, masked in pairs:
            self.assertEqual(len(real), len(masked), real)

    def test_only_the_code_occurrence_survives(self):
        # Note slab, trailing comment, string content and layout block
        # are all blanked; the one real call site is not.
        pairs = editing.masked_pairs(self.TEXT)
        hits = [i for i, (_, masked) in enumerate(pairs)
                if "Len(" in masked]
        self.assertEqual(hits, [3])
        self.assertNotIn("Left = 110", pairs[6][1])

    def test_join_rebuilds_the_file_verbatim(self):
        # The documented reconstruction contract for every editor.
        pairs = editing.masked_pairs(self.TEXT)
        self.assertEqual("\n".join(real for real, _ in pairs), self.TEXT)

    def test_crlf_endings_stay_with_the_real_lines(self):
        text = 'x = Len(s)\r\ns = "Len(a)"\r\n'
        pairs = editing.masked_pairs(text)
        self.assertEqual(pairs[0][0], "x = Len(s)\r")
        self.assertEqual("\n".join(real for real, _ in pairs), text)


if __name__ == "__main__":
    unittest.main(verbosity=1)
