#!/usr/bin/env python3
"""Tests for analysis_warnings.py (stdlib only, Python 3.9+).

The script patches a binary block inside the user's project state, so the
tests pin the safety contract harder than the feature: every malformed or
unexpected input must be refused with the file untouched, patches must be
byte-surgical (only the targeted value fields change, size never does), and
path resolution must never guess between candidates.

The synthetic blocks here are built from the WrnPGrup format observed in
IDE-written uistate files:

    "WrnPGrup" | uint32 BE length | uint32 BE groupID
    entries: "nameInt " int32 BE warningID "dataInt " int32 BE enabled
    trailer: "EndGInt " uint32 BE groupID     (at 12 + length)

with length = 4 + 24 * entryCount.

Run:  python3 test_analysis_warnings.py
"""
import contextlib
import io
import pathlib
import struct
import sys
import tempfile
import unittest

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import analysis_warnings as aw  # noqa: E402

# The seven IDs the IDE writes (the default-off warnings), in the order
# observed in real files, all disabled -- a freshly materialized block.
FRESH = [(5, 0), (6, 0), (7, 0), (14, 0), (2, 0), (-2, 0), (16, 0)]


def block(entries, gid=0x43, end_gid=None, mangle_entry=None,
          mangle_entry_data=None, end_marker=b"EndGInt "):
    body = b""
    for i, (wid, val) in enumerate(entries):
        name, data = b"nameInt ", b"dataInt "
        if mangle_entry == i:
            name = b"nameXXX "
        if mangle_entry_data == i:
            data = b"dataXXX "
        body += name + struct.pack(">i", wid) + data + struct.pack(">i", val)
    length = 4 + len(body)
    return (b"WrnPGrup" + struct.pack(">II", length, gid) + body +
            end_marker + struct.pack(">I", gid if end_gid is None else end_gid))


# Realistic surroundings: uistate files carry other record groups after (and,
# in binary projects, arbitrary bytes before) the WrnP block.
TRAILING = b"SwStGrup" + struct.pack(">II", 4, 0x40) + b"EndGInt " + struct.pack(">I", 0x40)


class DecodeTests(unittest.TestCase):
    def test_decode_fresh_block(self):
        data = block(FRESH) + TRAILING
        b = aw.decode(data)
        self.assertEqual(b.offset, 0)
        self.assertEqual([(e.warning_id, e.value) for e in b.entries], FRESH)

    def test_decode_finds_embedded_block(self):
        # Binary projects embed the same block mid-file rather than at 0.
        prefix = b"\x00garbage prefix\xff"
        b = aw.decode(prefix + block(FRESH) + TRAILING)
        self.assertEqual(b.offset, len(prefix))
        self.assertEqual(len(b.entries), 7)

    def test_missing_block_refused(self):
        with self.assertRaises(aw.BlockError):
            aw.decode(TRAILING)

    def test_trailer_group_id_mismatch_refused(self):
        with self.assertRaises(aw.BlockError):
            aw.decode(block(FRESH, gid=0x43, end_gid=0x44))

    def test_malformed_entry_refused(self):
        with self.assertRaises(aw.BlockError):
            aw.decode(block(FRESH, mangle_entry=3))

    def test_malformed_entry_data_marker_refused(self):
        with self.assertRaises(aw.BlockError):
            aw.decode(block(FRESH, mangle_entry_data=3))

    def test_trailer_marker_mismatch_refused(self):
        # The group id still matches; only the marker bytes are wrong.
        with self.assertRaises(aw.BlockError):
            aw.decode(block(FRESH, end_marker=b"GARBAGE!"))

    def test_truncated_block_refused(self):
        data = block(FRESH)
        with self.assertRaises(aw.BlockError):
            aw.decode(data[:len(data) - 6])

    def test_truncated_within_header_refused(self):
        # Truncation inside the 16-byte header must refuse, not raise
        # struct.error: main() only catches BlockError.
        with self.assertRaises(aw.BlockError):
            aw.decode(b"junk" + b"WrnPGrup" + b"\x00\x00")

    def test_unknown_ids_are_decoded_not_refused(self):
        b = aw.decode(block([(99, 1), (2, 0), (-2, 0), (16, 0)]))
        self.assertEqual(b.entries[0].warning_id, 99)


class EnableTests(unittest.TestCase):
    def test_enable_patches_only_the_three_value_fields(self):
        before = bytearray(block(FRESH) + TRAILING)
        after = bytearray(before)
        changed = aw.enable(after, aw.decode(after))
        self.assertEqual(changed, 3)
        self.assertEqual(len(after), len(before))
        diffs = [i for i, (a, c) in enumerate(zip(before, after)) if a != c]
        # Each patched value is an int32 whose 0 -> 1 flip changes exactly the
        # final byte; anything beyond three single-byte diffs is collateral.
        self.assertEqual(len(diffs), 3)
        result = aw.decode(after)
        want = {wid: (1 if wid in aw.DEPRECATION_IDS else val)
                for wid, val in FRESH}
        self.assertEqual({e.warning_id: e.value for e in result.entries}, want)

    def test_enable_is_idempotent(self):
        data = bytearray(block(FRESH))
        aw.enable(data, aw.decode(data))
        again = bytearray(data)
        self.assertEqual(aw.enable(again, aw.decode(again)), 0)
        self.assertEqual(bytes(again), bytes(data))

    def test_enable_refuses_when_a_target_id_is_absent(self):
        # A 3-6 entry block from an older save can lack one of the targets;
        # the fix is materialization by the IDE, never appending entries.
        data = bytearray(block([(5, 0), (6, 0), (7, 0)]))
        with self.assertRaises(aw.BlockError) as ctx:
            aw.enable(data, aw.decode(data))
        self.assertIn("open", str(ctx.exception).lower())
        self.assertEqual(bytes(data), bytes(block([(5, 0), (6, 0), (7, 0)])))


class WriteTests(unittest.TestCase):
    """Patching writes into the user's project state, so it is done in
    place: seek to each value field and overwrite four bytes. A whole-file
    rewrite would truncate first, and for a .xojo_binary_project -- a
    supported target -- the file being truncated IS the user's project."""

    def setUp(self):
        self.dir = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(self.dir))

    def test_patch_touches_only_the_value_fields_of_a_large_file(self):
        # Shaped like a binary project: the block sits deep inside a large
        # container with arbitrary bytes on both sides.
        head = bytes(range(256)) * 4096
        tail = b"\xa5" * 65536
        original = head + block(FRESH) + TRAILING + tail
        target = self.dir / "My App.xojo_binary_project"
        target.write_bytes(original)

        data = bytearray(original)
        changed = aw.enable(data, aw.decode(data))
        aw.write_patch(target, original, data)

        after = target.read_bytes()
        self.assertEqual(changed, 3)
        self.assertEqual(len(after), len(original))
        self.assertEqual([i for i, (a, b) in enumerate(zip(original, after))
                          if a != b],
                         [i for i, (a, b) in enumerate(zip(original, data))
                          if a != b])
        self.assertEqual(after, bytes(data))

    def test_patch_refuses_a_size_change(self):
        target = self.dir / ".x.xojo_uistate"
        original = block(FRESH)
        target.write_bytes(original)
        with self.assertRaises(aw.BlockError):
            aw.write_patch(target, original, bytearray(original + b"extra"))
        self.assertEqual(target.read_bytes(), original)


class ResolveTests(unittest.TestCase):
    def setUp(self):
        self.dir = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(self.dir))

    def touch(self, name, content=b""):
        p = self.dir / name
        p.write_bytes(content)
        return p

    def test_uistate_path_is_itself(self):
        p = self.touch(".My App.xojo_uistate")
        self.assertEqual(aw.resolve_target(p), p)

    def test_project_manifest_resolves_hidden_sibling(self):
        self.touch("My App.xojo_project")
        u = self.touch(".My App.xojo_uistate")
        self.assertEqual(aw.resolve_target(self.dir / "My App.xojo_project"), u)

    def test_hidden_sibling_wins_over_visible(self):
        # The IDE reads the dot-file; a visible one is a stale leftover, and
        # patching it would report success while changing nothing.
        self.touch("My App.xojo_project")
        hidden = self.touch(".My App.xojo_uistate")
        self.touch("My App.xojo_uistate")
        self.assertEqual(aw.resolve_target(self.dir / "My App.xojo_project"),
                         hidden)

    def test_directory_with_one_uistate(self):
        u = self.touch(".My App.xojo_uistate")
        self.touch("App.xojo_code")
        self.assertEqual(aw.resolve_target(self.dir), u)

    def test_binary_project_is_itself(self):
        p = self.touch("My App.xojo_binary_project")
        self.assertEqual(aw.resolve_target(p), p)

    def test_directory_with_only_a_binary_project(self):
        p = self.touch("My App.xojo_binary_project")
        self.assertEqual(aw.resolve_target(self.dir), p)

    def test_uistate_wins_over_binary_project_in_a_directory(self):
        u = self.touch(".My App.xojo_uistate")
        self.touch("My App.xojo_binary_project")
        self.assertEqual(aw.resolve_target(self.dir), u)

    def test_unrecognized_file_refused(self):
        p = self.touch("App.xojo_code")
        with self.assertRaises(aw.BlockError):
            aw.resolve_target(p)

    def test_nonexistent_path_refused(self):
        with self.assertRaises(aw.BlockError):
            aw.resolve_target(self.dir / "nope")

    def test_directory_with_none_errors_with_materialize_hint(self):
        self.touch("App.xojo_code")
        with self.assertRaises(aw.BlockError) as ctx:
            aw.resolve_target(self.dir)
        self.assertIn("close", str(ctx.exception).lower())

    def test_directory_with_two_errors_listing_both(self):
        self.touch(".A.xojo_uistate")
        self.touch(".B.xojo_uistate")
        with self.assertRaises(aw.BlockError) as ctx:
            aw.resolve_target(self.dir)
        msg = str(ctx.exception)
        self.assertIn(".A.xojo_uistate", msg)
        self.assertIn(".B.xojo_uistate", msg)


class CliTests(unittest.TestCase):
    def setUp(self):
        self.dir = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(self.dir))
        self.uistate = self.dir / ".My App.xojo_uistate"
        self.uistate.write_bytes(block(FRESH) + TRAILING)

    def run_cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        code = 0
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                aw.main(list(argv))
            except SystemExit as e:
                # sys.exit(str) carries the message in the exception; the
                # interpreter would print it to stderr only if it escaped.
                if isinstance(e.code, int):
                    code = e.code
                else:
                    code = 1
                    err.write(str(e.code or ""))
        return code, out.getvalue(), err.getvalue()

    def state_lines(self, out):
        """{warning_id: reported state} parsed from the report's rows."""
        found = {}
        for line in out.splitlines():
            parts = line.split()
            if len(parts) >= 3 and parts[0] == "id":
                found[int(parts[1])] = parts[2]
        return found

    def test_report_lists_all_entries(self):
        code, out, _ = self.run_cli(str(self.dir))
        self.assertEqual(code, 0)
        # Every id present, and every one reported OFF -- a report that
        # mislabels state is worse than no report, since phase 0 reads it to
        # decide whether the warnings still need enabling.
        self.assertEqual(self.state_lines(out),
                         {wid: "off" for wid, _ in FRESH})
        self.assertIn("0 of 3 enabled", out)
        self.assertIn("deprecated", out.lower())

    def test_report_shows_enabled_state(self):
        data = bytearray(self.uistate.read_bytes())
        aw.enable(data, aw.decode(data))
        self.uistate.write_bytes(data)
        code, out, _ = self.run_cli(str(self.dir))
        self.assertEqual(code, 0)
        want = {wid: ("ON" if wid in aw.DEPRECATION_IDS else "off")
                for wid, _ in FRESH}
        self.assertEqual(self.state_lines(out), want)
        self.assertIn("3 of 3 enabled", out)

    def test_enable_writes_and_reports(self):
        before = self.uistate.read_bytes()
        code, out, err = self.run_cli(str(self.dir), "--enable")
        self.assertEqual(code, 0)
        after = self.uistate.read_bytes()
        entries = aw.decode(after).entries
        self.assertEqual({e.warning_id: e.value for e in entries
                          if e.warning_id in aw.DEPRECATION_IDS},
                         {-2: 1, 2: 1, 16: 1})
        # The write itself must be byte-surgical on disk, not merely in
        # memory: same size, and only the three value bytes touched.
        self.assertEqual(len(after), len(before))
        self.assertEqual(
            len([i for i, (a, b) in enumerate(zip(before, after)) if a != b]), 3)
        # The report must describe the patched state, not the pre-patch one.
        self.assertIn("3 of 3 enabled", out)
        # The close-the-project-first caveat must reach the user every time.
        self.assertIn("closed", (out + err).lower())

    def test_enable_missing_block_exits_nonzero_with_hint(self):
        self.uistate.write_bytes(TRAILING)
        code, out, err = self.run_cli(str(self.dir), "--enable")
        self.assertNotEqual(code, 0)
        self.assertIn("close", (out + err).lower())


if __name__ == "__main__":
    unittest.main(verbosity=1)
