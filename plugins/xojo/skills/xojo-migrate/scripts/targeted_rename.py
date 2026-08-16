#!/usr/bin/env python3
"""Rename members only at the sites the analyzer flagged.

Type-blind member rules cannot tell Graphics.DrawRect from a user
class's own DrawRect. The analyzer already resolved the receiver -- that
is what produced the warning -- so its located site list is a
receiver-verified worklist, and this edits nothing else: the same member
name one line away is not touched.

The IDE reports no column, so precision stops at the line. The honest
maximum is occurrence accounting: when the flagged line holds exactly as
many `.Old` occurrences (in code -- strings and comments are masked) as
the IDE flagged, all of them rename; when the line holds MORE, nothing
on it renames and the site is reported for hand conversion -- renaming
both a flagged `g.DrawRect` and an unflagged user-class
`obj.DrawRect` sharing a line is exactly the corruption this tool
exists to prevent.

Usage:
  python3 targeted_rename.py <analyze.json|-> <map.json> [--project DIR]
                             [--apply] [--format text|json]
  map.json: {"FillRect": "FillRectangle", "ForeColor": "DrawingColor",
             "GetSaveInfo": null}
            a null or "" value means: report those sites, convert nothing.

The analyze document should have passed through locate.py (the pipe
adds file:line to each diagnostic); an unlocated document is enriched
here first, using --project or the document's result.session.project.
Located paths are held to a verified project root (--project or the
root the document records): a site outside it is reported, never
edited. The verification is structural, not provenance -- the root
must be a real project folder holding a top-level manifest, and only
Xojo source files are eligible targets -- so a forged document can
still only aim at real Xojo source under a real Xojo project. Dry run
by default; --apply writes. (stdlib only)
"""
import argparse
import collections
import json
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import locate  # noqa: E402
from editing import masked_pairs, read_source, write_source  # noqa: E402
from scan import MANIFEST_EXTS, SOURCE_EXTS  # noqa: E402


NO_MEMBER = re.compile(r'has no member named\s+"?([A-Za-z_]\w*)', re.I)


def symbol_of(d):
    """The member a diagnostic is about, warnings and errors both.

    Pass E's burn-down feeds this ERRORS -- 'Type "DesktopListBox" has
    no member named "ListCount"' -- and dropping them silently made the
    whole documented burn-down a no-op.
    """
    msg = d.get("message") or ""
    if d.get("severity") == "warning" and " is deprecated" in msg:
        return msg.split(" is deprecated")[0].strip()
    if d.get("severity") == "error":
        m = NO_MEMBER.search(msg)
        if m:
            return m.group(1)
    return None


def gather(doc, mapping, root):
    """Sort the mapped diagnostics into work, report-only and unresolved.

    work counts flagged occurrences per (file, line, old, new) -- the
    IDE emits one diagnostic per occurrence, and that count is what the
    line's actual occurrence count must equal before anything renames.
    A located path that resolves outside root never enters work -- a
    stale or forged document must not steer writes outside the project.
    """
    ci = {k.lower(): (k, v) for k, v in mapping.items()}
    work = collections.Counter()
    report_only, unresolved = [], []
    for d in doc.get("diagnostics", []):
        sym = symbol_of(d)
        if sym is None or sym.lower() not in ci:
            continue
        old, new = ci[sym.lower()]
        where = d.get("position") or d.get("location") or "?"
        located = (d.get("resolution") == "located"
                   and d.get("line_basis") != "signature")
        if not new:
            report_only.append(
                f"{d['file']}:{d['file_line']}  {old}" if located
                else f"{where}  {old}")
            continue
        if not located:
            unresolved.append(f"{old}: {where} "
                              f"({d.get('resolution') or 'not located'})")
            continue
        # locate.py only maps diagnostics onto collect_files' source
        # list, so a located diagnostic naming any other suffix is per
        # se forged or corrupt -- refuse it before the root check.
        if pathlib.Path(d["file"]).suffix.lower() not in SOURCE_EXTS:
            unresolved.append(f"{old}: {d['file']}:{d['file_line']} "
                              f"(not a Xojo source file)")
            continue
        if not pathlib.Path(d["file"]).resolve().is_relative_to(root):
            unresolved.append(f"{old}: {d['file']}:{d['file_line']} "
                              f"(file outside project root)")
            continue
        work[(d["file"], d["file_line"], old, new)] += 1
    return work, report_only, unresolved


def rename(work, apply_):
    """Apply the renames per file; return (renamed, files, misses)."""
    member, bare = {}, {}
    for (_, _, old, _) in work:
        member.setdefault(old, re.compile(
            r"(?<=\.)" + re.escape(old) + r"\b", re.I))
        # An occurrence with no dot: an implicit-Self member reference
        # or a global use. The IDE flags those too, so their presence
        # on the line makes the dotted-occurrence count unattributable.
        bare.setdefault(old, re.compile(
            r"(?<![\w.])" + re.escape(old) + r"\b", re.I))
    by_file = collections.defaultdict(lambda: collections.defaultdict(list))
    for (path, line_no, old, new), flagged in work.items():
        by_file[path][line_no].append((old, new, flagged))

    renamed, files_changed = 0, []
    ambiguous, not_found = [], []
    for path in sorted(by_file):
        text = read_source(path)
        lines = text.split("\n")
        masked = [m for _, m in masked_pairs(text)]
        changed = False
        for line_no in sorted(by_file[path]):
            if not 0 < line_no <= len(lines):
                not_found.append(f"{path}:{line_no} out of range")
                continue
            mline = masked[line_no - 1]
            spans = []
            for old, new, flagged in sorted(by_file[path][line_no]):
                occ = list(member[old].finditer(mline))
                undotted = list(bare[old].finditer(mline))
                if undotted:
                    # The IDE may be flagging the implicit-Self use, not
                    # the dotted one; renaming the dotted occurrence
                    # would convert an unflagged site and leave the
                    # flagged one -- exactly the corruption this tool
                    # exists to prevent. Refuse the symbol on this line.
                    beside = (f"beside {len(occ)} dotted" if occ
                              else "and no dotted occurrence")
                    ambiguous.append(
                        f"{path}:{line_no} {old}: {len(undotted)} "
                        f"undotted (implicit-Self or global) "
                        f"occurrence(s) {beside} -- the flag cannot be "
                        f"attributed to a dotted site; convert by hand")
                    continue
                if not occ:
                    not_found.append(
                        f"{path}:{line_no} .{old} not found in code on: "
                        f"{lines[line_no - 1].strip()[:70]}")
                    continue
                if len(occ) != flagged:
                    ambiguous.append(
                        f"{path}:{line_no} .{old}: {len(occ)} occurrence(s) "
                        f"in code, {flagged} flagged -- convert by hand")
                    continue
                spans.extend((m.start(), m.end(), new) for m in occ)
            # All spans are measured against the ORIGINAL line and
            # spliced right-to-left, so one symbol's replacement can
            # never feed another's pattern (no A->B->C chaining) and the
            # result does not depend on map order.
            spans.sort()
            overlap = any(b[0] < a[1] for a, b in zip(spans, spans[1:]))
            if overlap:
                ambiguous.append(f"{path}:{line_no} overlapping renames -- "
                                 f"convert by hand")
                continue
            real = lines[line_no - 1]
            for start, end, new in reversed(spans):
                real = real[:start] + new + real[end:]
                renamed += 1
            if spans:
                lines[line_no - 1] = real
                changed = True
        if changed:
            files_changed.append(path)
            if apply_:
                write_source(path, "\n".join(lines))
    return renamed, files_changed, ambiguous, not_found


def main(argv=None, stdin=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("document",
                    help="analyze JSON (ideally locate.py-enriched); "
                         "'-' reads stdin")
    ap.add_argument("map", help="JSON object of {OldMember: NewMember}")
    ap.add_argument("--project",
                    help="project root, for enriching an unlocated document")
    ap.add_argument("--apply", action="store_true",
                    help="write the renames (default is a dry run)")
    ap.add_argument("--format", choices=("text", "json"), default="text")
    args = ap.parse_args(argv)

    stream = stdin or sys.stdin
    try:
        if args.document != "-":
            with open(args.document, encoding="utf-8") as f:
                doc = json.load(f)
        else:
            doc = json.load(stream)
        with open(args.map, encoding="utf-8") as f:
            mapping = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        sys.exit(f"cannot read input: {e}")
    if not isinstance(doc, dict) or "diagnostics" not in doc:
        sys.exit("this is not an 'xojoctl analyze --json' document: "
                 "no 'diagnostics' key.")
    if not isinstance(mapping, dict) or not mapping:
        sys.exit("the map must be a non-empty JSON object of "
                 '{"OldMember": "NewMember"}.')

    if "located" not in doc:
        root, why_not = locate._project_root(args, doc)
        if root is None:
            sys.exit(f"the document carries no file:line and none can be "
                     f"added: {why_not}. Pipe it through locate.py, or "
                     f"pass --project.")
        locate.enrich(doc, root)
        root = pathlib.Path(root).resolve()
    else:
        # A pre-located document's file paths are absolute and taken at
        # their word, so the root they must sit under is pinned here:
        # --project, the root locate.py recorded, or both in agreement.
        given = None
        if args.project:
            p = pathlib.Path(args.project)
            given = (p.parent if p.is_file() else p).resolve()
        meta = doc["located"] if isinstance(doc["located"], dict) else {}
        recorded = meta.get("project_root")
        recorded = pathlib.Path(recorded).resolve() if recorded else None
        if given and recorded and given != recorded:
            sys.exit(f"--project ({given}) disagrees with the project "
                     f"root the document records ({recorded}) -- the "
                     f"document looks stale or relocated. Re-run "
                     f"locate.py against the right project.")
        root = given or recorded
        if root is None:
            sys.exit("the document's 'located' record carries no "
                     "project_root, so its file paths cannot be "
                     "verified; pass --project.")
        # A degenerate root ("/" makes every absolute path pass the
        # containment check) defeats verification. locate.py records the
        # manifest's parent as the root, so a legitimate root always
        # holds a top-level manifest; demand that structure here.
        if root == root.parent or not root.is_dir() or not any(
                c.is_file() and c.suffix.lower() in MANIFEST_EXTS
                for c in root.iterdir()):
            sys.exit(f"the verified root ({root}) is not a Xojo project "
                     f"folder -- expected a directory holding a "
                     f"top-level .xojo_project manifest. Re-run "
                     f"locate.py against the real project, or pass "
                     f"--project.")

    work, report_only, unresolved = gather(doc, mapping, root)
    renamed, files, ambiguous, not_found = rename(work, args.apply)

    if args.format == "json":
        print(json.dumps({
            "renamed": renamed, "files": files, "applied": args.apply,
            "report_only": report_only, "unresolved": unresolved,
            "occurrence_ambiguous": ambiguous, "not_found": not_found,
        }, indent=1))
        return
    print(f"renamed: {renamed} site(s) across {len(files)} file(s)")
    for title, items, coda in (
            ("REPORT ONLY", report_only,
             "map value empty -- sites listed, nothing converted"),
            ("UNRESOLVED", unresolved,
             "no located line inside the project -- resolve by hand "
             "(see locate.py)"),
            ("OCCURRENCE-AMBIGUOUS", ambiguous,
             "the line holds more of the member than the IDE flagged"),
            ("NOT FOUND ON LINE", not_found, "check by hand")):
        if items:
            print(f"\n{title} ({len(items)}) -- {coda}:")
            for item in items:
                print("  " + item)
    if not args.apply:
        print("\n(dry run -- nothing written; pass --apply)")


if __name__ == "__main__":
    main()
