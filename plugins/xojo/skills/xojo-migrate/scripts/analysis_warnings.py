#!/usr/bin/env python3
"""Report or enable the Xojo IDE's per-project deprecation analysis warnings.

Usage:
  python3 analysis_warnings.py <target>            # report current state
  python3 analysis_warnings.py <target> --enable   # turn the deprecation
                                                   # warnings on

<target> is a project directory, a .xojo_project manifest, a .xojo_uistate
file, or a .xojo_binary_project file.

Why this exists: Analyze Project only reports deprecated API 1.0 calls when the
"Item1 is deprecated" warnings are enabled, and they are off by default. The
setting is per-project -- there is no global preference to set once, no key in
com.xojo.xojo.plist, and no IDE-scripting command that reaches it (DoCommand
offers CheckProjectErrors but nothing that touches warning settings). What the
IDE stores is a binary "WrnPGrup" record: at offset 0 of the project's hidden
.xojo_uistate in text-format projects, embedded near the end of the container
in .xojo_binary_project files.

    "WrnPGrup" | uint32 BE length | uint32 BE groupID
    entries, 24 bytes each:
        "nameInt " int32 BE warningID | "dataInt " int32 BE enabled (0/1)
    trailer, at 12 + length: "EndGInt " uint32 BE groupID
    (length = 4 + 24 * entryCount)

Only the default-off warnings are recorded; a warning absent from the block is
one that defaults to on. The three that matter for migration are -2 ("Item1 is
deprecated"), 2 ("Item1 is deprecated. You should use Item2 instead") and 16
("Show API 2 Desktop control deprecations").

Two ordering rules, both load-bearing:

- **The project must be closed in the IDE while you patch.** The IDE keeps
  warning preferences on the in-memory document and rewrites this file when
  the project closes, so a patch made while the project is open is silently
  clobbered. Close (xojoctl close --save), patch, reopen.
- **Patch existing entries in place; never append one.** Appending would have
  to rewrite the length and the trailer and whatever outer framing surrounds
  the block; a same-size value flip cannot corrupt anything. A freshly
  created project has no block at all -- one open + close in the IDE
  materializes it with every entry present -- so appending is never needed.
"""
import argparse
import collections
import pathlib
import struct
import sys

# The warning ids to enable: both deprecation warnings plus the API 2.0 Desktop
# control deprecations toggle, which gates exactly the control renames an API
# 1 -> 2 migration is chasing.
DEPRECATION_IDS = (-2, 2, 16)

# Labels for the ids observed in IDE-written blocks. Unknown ids decode and
# report as "?" rather than failing: the set may grow with the IDE.
LABELS = {
    -2: "Item1 is deprecated",
    2: "Item1 is deprecated. You should use Item2 instead",
    5: "conversion may lose precision",
    6: "conversion loses sign information",
    7: "floating-point equality comparison",
    14: "pre-2014r3 Item1/Item2 reference change",
    16: "Show API 2 Desktop control deprecations",
}

MATERIALIZE = ("open the project in the Xojo IDE, run Analyze Project once, "
               "and close it (the warning block is analysis state: the IDE "
               "writes it when a project that has been analyzed closes -- "
               "closing a never-analyzed project writes none), then re-run "
               "this script")

Entry = collections.namedtuple("Entry", "value_offset warning_id value")
Block = collections.namedtuple("Block", "offset length group_id entries")


class BlockError(Exception):
    """Anything that means: do not touch this file."""


def decode(data):
    """Parse the first WrnPGrup block in `data`, verifying every byte of its
    framing. Raises BlockError rather than guessing: this tool writes into
    the user's project state, so an unrecognized layout is a hard stop."""
    off = data.find(b"WrnPGrup")
    if off < 0:
        raise BlockError(f"no WrnPGrup warning block found; {MATERIALIZE}")
    if off + 16 > len(data):
        raise BlockError("WrnPGrup block is truncated at its header")
    length, group_id = struct.unpack_from(">II", data, off + 8)
    if length < 4 or (length - 4) % 24 != 0:
        raise BlockError(f"WrnPGrup length {length} is not 4 + 24*n")
    count = (length - 4) // 24
    trailer = off + 12 + length
    if trailer + 12 > len(data):
        raise BlockError("WrnPGrup block is truncated before its trailer")
    entries = []
    for k in range(count):
        e = off + 16 + 24 * k
        if data[e:e + 8] != b"nameInt " or data[e + 12:e + 20] != b"dataInt ":
            raise BlockError(f"WrnPGrup entry {k} has unexpected framing")
        wid = struct.unpack_from(">i", data, e + 8)[0]
        val = struct.unpack_from(">i", data, e + 20)[0]
        entries.append(Entry(e + 20, wid, val))
    if data[trailer:trailer + 8] != b"EndGInt ":
        raise BlockError("WrnPGrup trailer marker missing")
    if struct.unpack_from(">I", data, trailer + 8)[0] != group_id:
        raise BlockError("WrnPGrup trailer group id does not match the header")
    return Block(off, length, group_id, entries)


def enable(data, block):
    """Set every DEPRECATION_IDS entry in `data` (a bytearray) to 1, in
    place. Returns how many entries changed. Raises BlockError -- with the
    file untouched -- if any target id is absent, because the fix for an
    incomplete block is IDE materialization, never appending entries."""
    present = {e.warning_id: e for e in block.entries}
    missing = [wid for wid in DEPRECATION_IDS if wid not in present]
    if missing:
        raise BlockError(
            f"warning id(s) {missing} are not in this block; {MATERIALIZE}")
    changed = 0
    for wid in DEPRECATION_IDS:
        e = present[wid]
        if e.value != 1:
            struct.pack_into(">i", data, e.value_offset, 1)
            changed += 1
    return changed


def write_patch(target, original, patched):
    """Write `patched` over `target` in place, byte by changed byte.

    Deliberately not write_bytes(): that truncates the file and rewrites it
    whole, so an interruption mid-write leaves a truncated file. For a
    .xojo_uistate that would only cost the IDE's window positions, but a
    .xojo_binary_project is a supported target and there the file *is* the
    user's project. Seeking to each changed run and overwriting it never
    shortens the file, and cannot touch a byte outside the patch."""
    if len(patched) != len(original):
        raise BlockError("refusing to write: patch changed the file size")
    runs = []
    for i, (a, b) in enumerate(zip(original, patched)):
        if a != b:
            if runs and runs[-1][1] == i:
                runs[-1][1] = i + 1
            else:
                runs.append([i, i + 1])
    if not runs:
        return 0
    with open(target, "r+b") as fh:
        for start, stop in runs:
            fh.seek(start)
            fh.write(bytes(patched[start:stop]))
        fh.flush()
    return len(runs)


def resolve_target(path):
    """Map what the user gave us to the one file holding the block.

    Never guesses between candidates: a directory with several uistate files
    is an error naming them all, not a pick."""
    path = pathlib.Path(path)
    if not path.exists():
        raise BlockError(f"path does not exist: {path}")
    if path.is_file():
        if path.name.endswith((".xojo_uistate", ".xojo_binary_project")):
            return path
        if path.name.endswith(".xojo_project"):
            # The IDE writes the uistate as a hidden dot-file sibling of the
            # manifest (".My App.xojo_uistate" next to "My App.xojo_project").
            stem = path.name[:-len(".xojo_project")]
            for cand in (path.parent / f".{stem}.xojo_uistate",
                         path.parent / f"{stem}.xojo_uistate"):
                if cand.exists():
                    return cand
            raise BlockError(f"no uistate found for {path.name}; {MATERIALIZE}")
        raise BlockError(f"{path.name}: expected a .xojo_project, "
                         ".xojo_uistate, .xojo_binary_project, or a "
                         "project directory")
    uistates = sorted(p for p in path.iterdir()
                      if p.is_file() and p.name.endswith(".xojo_uistate"))
    if len(uistates) == 1:
        return uistates[0]
    if len(uistates) > 1:
        names = ", ".join(p.name for p in uistates)
        raise BlockError(f"{path} holds several uistate files ({names}); "
                         f"name the one to use")
    binaries = sorted(p for p in path.iterdir()
                      if p.is_file() and p.name.endswith(".xojo_binary_project"))
    if len(binaries) == 1:
        return binaries[0]
    raise BlockError(f"no .xojo_uistate found under {path}; {MATERIALIZE}")


def report(target, block):
    print(f"{target}: WrnPGrup at offset {block.offset}, "
          f"{len(block.entries)} entries, group {block.group_id:#x}")
    for e in block.entries:
        state = "ON " if e.value == 1 else "off" if e.value == 0 else str(e.value)
        print(f"  id {e.warning_id:>3}  {state}  "
              f"{LABELS.get(e.warning_id, '?')}")
    on = sum(1 for e in block.entries
             if e.warning_id in DEPRECATION_IDS and e.value == 1)
    print(f"deprecation warnings: {on} of {len(DEPRECATION_IDS)} enabled "
          f"(ids {', '.join(str(i) for i in DEPRECATION_IDS)})")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("target", help="project directory, .xojo_project, "
                                   ".xojo_uistate, or .xojo_binary_project")
    ap.add_argument("--enable", action="store_true",
                    help=f"set warning ids {DEPRECATION_IDS} to enabled")
    args = ap.parse_args(argv)

    try:
        target = resolve_target(args.target)
        original = target.read_bytes()
        data = bytearray(original)
        block = decode(data)
        if args.enable:
            changed = enable(data, block)
            if changed:
                write_patch(target, original, data)
            # Re-decode from the patched bytes so the report states what is
            # now on disk, not what was.
            block = decode(data)
            report(target, block)
            print(f"enabled {changed} warning(s); file size unchanged "
                  f"({len(data)} bytes)")
            print("note: this only sticks if the project was closed in the "
                  "Xojo IDE -- the IDE rewrites this file when the project "
                  "closes. Close, enable, then reopen.", file=sys.stderr)
        else:
            report(target, block)
    except BlockError as e:
        sys.exit(f"{args.target}: {e}")


if __name__ == "__main__":
    main()
