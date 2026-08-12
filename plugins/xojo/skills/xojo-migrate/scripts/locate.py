#!/usr/bin/env python3
"""Enrich `xojoctl analyze --json` diagnostics with real file:line positions.

The IDE reports each diagnostic as "Owner.Member, line N" where N counts
from the start of the METHOD BODY, not the file, so nothing mechanical
can act on the raw document. This filter indexes every method, event and
computed-property body in the project's text files and adds to each
diagnostic that carries a location:

  file        absolute path of the source file
  file_line   1-based line in that file (signature line + body offset)
  line_basis  "body-offset" normally; "signature" when the IDE sent no line
  resolution  "located" | "ambiguous" | "unresolved"
  candidates  ambiguous only: the competing {file, file_line} positions

Sites it cannot settle stay honest: ambiguous and unresolved diagnostics
carry no file/file_line and are the caller's manual queue. Guessing here
would hand targeted_rename.py a wrong line, and a wrong edit is silent
where a skipped site fails loudly at the next analyze.

Used as a filter it re-emits the whole document -- every field it does
not understand passes through untouched -- so it slots between analyze
and the worklist:

Usage:
  python3 -m xojoctl analyze --project P --discard --json | python3 locate.py | python3 worklist.py
  python3 locate.py analyze.json --project /path/to/project
  python3 locate.py analyze.json --project DIR --format text [--only Len,Mid]

The project root comes from --project (a directory or a .xojo_project
manifest), or else from the document's result.session.project -- present
when the analyze ran as a bracketed `analyze --project` session, which
is also what guarantees the disk matches what the IDE analyzed. With
neither, the document passes through unenriched with a warning: no
enrichment beats a file:line the disk cannot back. (stdlib only)
"""
import argparse
import json
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from editing import SIGNATURE, read_source, masked_pairs  # noqa: E402
from scan import collect_files  # noqa: E402

EVENTS = re.compile(r"^\s*#tag\s+Events\s+(\S+)", re.I)
END_EVENTS = re.compile(r"^\s*#tag\s+EndEvents\b", re.I)
CLASS = re.compile(
    r"^\s*(?:Protected\s+|Private\s+)?(?:Class|Module|Interface)\s+"
    r"([A-Za-z_]\w*)", re.I)
# The window/container name comes from the file's opening layout block.
# Matched on the raw line (layout blocks are blanked in the mask) and only
# near the top of the file, so nested control Begins never rename the
# container.
BEGIN = re.compile(r"^\s*Begin\s+[A-Za-z_][\w.]*\s+([A-Za-z_]\w*)")
CP_OPEN = re.compile(r"^\s*#tag\s+ComputedProperty\b", re.I)
CP_CLOSE = re.compile(r"^\s*#tag\s+EndComputedProperty\b", re.I)
GETTER = re.compile(r"^\s*#tag\s+Getter\b", re.I)
END_GETTER = re.compile(r"^\s*#tag\s+EndGetter\b", re.I)
SETTER = re.compile(r"^\s*#tag\s+Setter\b", re.I)
END_SETTER = re.compile(r"^\s*#tag\s+EndSetter\b", re.I)
GET_LINE = re.compile(r"^\s*Get\s*$", re.I)
SET_LINE = re.compile(r"^\s*Set\s*$", re.I)
PROP_DECL = re.compile(r"^\s*([A-Za-z_]\w*)\s+As\s", re.I)


def _computed_property(pairs, start, register):
    """Index one #tag ComputedProperty block; return the index after it.

    The property's NAME sits on the trailing `Name As Type` line, after
    both bodies, so the block is scanned to its end tag first. The Get
    and Set lines are the signature lines their bodies count from. A
    bare `Prop` key maps to both bodies -- a diagnostic that names only
    the property resolves ambiguous with both candidates, which is
    honest, where the draft tooling could not resolve it at all.
    """
    name, get_line, set_line = None, None, None
    in_get = in_set = False
    j = start + 1
    while j < len(pairs):
        raw = pairs[j][0]
        if CP_CLOSE.match(raw):
            break
        if GETTER.match(raw):
            in_get = True
        elif END_GETTER.match(raw):
            in_get = False
        elif SETTER.match(raw):
            in_set = True
        elif END_SETTER.match(raw):
            in_set = False
        elif in_get and get_line is None and GET_LINE.match(raw):
            get_line = j + 1
        elif in_set and set_line is None and SET_LINE.match(raw):
            set_line = j + 1
        elif not in_get and not in_set and name is None:
            pd = PROP_DECL.match(raw)
            if pd:
                name = pd.group(1)
        j += 1
    if name:
        if get_line:
            register(f"{name}.Get", get_line)
            register(name, get_line)
        if set_line:
            register(f"{name}.Set", set_line)
            register(name, set_line)
    return j + 1


def build_index(root):
    """{(container, member) lowercased: [(path, signature_lineno)], ...}.

    Signatures are matched against the code_only-masked line, so a
    `Sub Foo` quoted inside a #tag Note slab or a comment is not a
    method. Keys are lowercased: Xojo is case-insensitive and the IDE's
    spelling of a location need not match the source's.
    """
    idx = {}
    src, _, _, _ = collect_files(pathlib.Path(root))
    for path in src:
        pairs = masked_pairs(read_source(path))
        container = path.stem
        ev_owner = None

        def register(member, lineno, _path=path):
            key = (container.lower(), member.lower())
            idx.setdefault(key, []).append((str(_path), lineno))

        i = 0
        while i < len(pairs):
            raw, masked = pairs[i]
            # Structural #tag markers and Begin blocks are blanked in the
            # mask (code_only blanks every fence line), so they match on
            # the raw line. Signatures and class headers match the MASK,
            # which is what keeps a `Sub Foo` quoted in a #tag Note slab
            # out of the index.
            c = CLASS.match(masked)
            if c:
                container = c.group(1)
            if i < 3:
                b = BEGIN.match(raw)
                if b:
                    container = b.group(1)
            e = EVENTS.match(raw)
            if e:
                ev_owner = e.group(1)
            elif END_EVENTS.match(raw):
                ev_owner = None
            elif CP_OPEN.match(raw):
                i = _computed_property(pairs, i, register)
                continue
            m = SIGNATURE.match(masked)
            if m:
                member = m.group(1)
                register(member, i + 1)
                if ev_owner:
                    register(f"{ev_owner}.{member}", i + 1)
                    key = (ev_owner.lower(), member.lower())
                    idx.setdefault(key, []).append((str(path), i + 1))
            i += 1
    return idx


def resolve(idx, location, line):
    """One diagnostic's position: ("located", path, file_line) or
    ("ambiguous", candidates) or ("unresolved",).

    Every key shape is tried most-specific-first across every split of
    the dotted location; the first shape with exactly one hit wins. Only
    after all shapes are exhausted does the most specific multi-hit
    shape come back as ambiguous -- the draft tooling stopped at the
    first multi-hit shape and missed unique resolutions hiding behind
    it (two controls sharing an event name, resolvable through the
    "Owner.Event" key).
    """
    parts = [p for p in location.lower().split(".") if p]
    keys, seen = [], set()
    for split_at in range(len(parts) - 1, 0, -1):
        cont = ".".join(parts[:split_at])
        mem = ".".join(parts[split_at:])
        for key in ((cont, mem), (parts[0], mem), (cont, parts[-1])):
            if key not in seen:
                seen.add(key)
                keys.append(key)
    first_multi = None
    for key in keys:
        hits = idx.get(key)
        if not hits:
            continue
        if len(hits) == 1:
            path, start = hits[0]
            return ("located", path, start + (line or 0))
        if first_multi is None:
            first_multi = hits
    if first_multi is not None:
        return ("ambiguous",
                [{"file": p, "file_line": s + (line or 0)}
                 for p, s in first_multi])
    return ("unresolved",)


def enrich(doc, root):
    """Mutate doc's diagnostics in place; return the summary counts."""
    idx = build_index(root)
    stats = {"project_root": str(pathlib.Path(root).resolve()),
             "located": 0, "ambiguous": 0, "unresolved": 0,
             "no_location": 0}
    for d in doc.get("diagnostics", []):
        loc = d.get("location")
        if not isinstance(loc, str) or not loc:
            stats["no_location"] += 1
            continue
        res = resolve(idx, loc, d.get("line"))
        d["resolution"] = res[0]
        if res[0] == "located":
            d["file"] = str(pathlib.Path(res[1]).resolve())
            d["file_line"] = res[2]
            d["line_basis"] = ("body-offset" if isinstance(d.get("line"), int)
                               else "signature")
        elif res[0] == "ambiguous":
            d["candidates"] = res[1]
        stats[res[0]] += 1
    doc["located"] = stats
    return stats


def _symbol(d):
    msg = d.get("message") or ""
    if " is deprecated" in msg:
        return msg.split(" is deprecated")[0].strip()
    return None


def report(doc, only=None):
    root = pathlib.Path(doc.get("located", {}).get("project_root", "."))
    wanted = {s.strip().lower() for s in only.split(",")} if only else None
    rows = {"located": [], "ambiguous": [], "unresolved": []}
    for d in doc.get("diagnostics", []):
        res = d.get("resolution")
        if res not in rows:
            continue
        sym = _symbol(d)
        if wanted is not None and (sym or "").lower() not in wanted:
            continue
        label = sym or d.get("severity", "?")
        if res == "located":
            try:
                rel = pathlib.Path(d["file"]).resolve().relative_to(
                    root.resolve())
            except ValueError:
                rel = d["file"]
            rows[res].append(f"  {label:22} {rel}:{d['file_line']}  "
                             f"{(d.get('message') or '')[:70]}")
        else:
            rows[res].append(f"  {label:22} {d.get('location', '?')}  "
                             f"({len(d.get('candidates', []))} candidates)"
                             if res == "ambiguous" else
                             f"  {label:22} {d.get('location', '?')}")
    for section in ("located", "ambiguous", "unresolved"):
        if rows[section]:
            print(f"{section.upper()} ({len(rows[section])})")
            for row in rows[section]:
                print(row)
            print()


def _project_root(args, doc):
    """The directory to index, or (None, why-not)."""
    if args.project:
        p = pathlib.Path(args.project)
        if not p.exists():
            sys.exit(f"--project path does not exist: {p}")
        return (p.parent if p.is_file() else p), None
    session = (doc.get("result") or {}).get("session") or {}
    sp = session.get("project")
    if not sp:
        return None, ("the document has no result.session.project and no "
                      "--project was given")
    p = pathlib.Path(sp)
    if not p.exists():
        return None, f"result.session.project does not exist on disk: {p}"
    if session.get("closed") is False:
        print("warning: session.closed is false -- the project is still "
              "open in the IDE, so the disk may not match what was "
              "analyzed. Close it before editing.", file=sys.stderr)
    return (p.parent if p.is_file() else p), None


def main(argv=None, stdin=None):
    ap = argparse.ArgumentParser(
        description=__doc__.split("\n\n")[0])
    ap.add_argument("document", nargs="?",
                    help="analyze JSON file; omit or '-' to read stdin")
    ap.add_argument("--project",
                    help="project directory or .xojo_project manifest; "
                         "overrides the document's session record")
    ap.add_argument("--format", choices=("json", "text"), default="json",
                    help="json (default) re-emits the enriched document "
                         "for the next pipe stage; text prints a report")
    ap.add_argument("--only",
                    help="text report only: comma-separated deprecated "
                         "symbols to show")
    args = ap.parse_args(argv)

    stream = stdin or sys.stdin
    try:
        if args.document and args.document != "-":
            with open(args.document, encoding="utf-8") as f:
                doc = json.load(f)
        else:
            doc = json.load(stream)
    except (OSError, json.JSONDecodeError) as e:
        sys.exit(f"cannot read the analyze document: {e}")
    if not isinstance(doc, dict) or "diagnostics" not in doc:
        sys.exit("this is not an 'xojoctl analyze --json' document: "
                 "no 'diagnostics' key.")

    root, why_not = _project_root(args, doc)
    if root is None:
        if args.format == "text":
            sys.exit(f"cannot locate: {why_not}. Pass --project, or use a "
                     "document from `analyze --project ... --discard`.")
        print(f"warning: passing the document through UNENRICHED -- "
              f"{why_not}. No file:line was added.", file=sys.stderr)
        print(json.dumps(doc, indent=1))
        return

    stats = enrich(doc, root)
    print(f"note: located {stats['located']} site(s); "
          f"{stats['ambiguous']} ambiguous, "
          f"{stats['unresolved']} unresolved, "
          f"{stats['no_location']} without a location.", file=sys.stderr)
    if args.format == "json":
        print(json.dumps(doc, indent=1))
    else:
        report(doc, args.only)


if __name__ == "__main__":
    main()
