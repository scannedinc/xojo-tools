#!/usr/bin/env python3
"""Fill gaps in coverage.json from the Xojo IDE's own deprecation database.

Maintenance tool, not part of a migration. Run it when a new Xojo release
ships; it rewrites `references/coverage.json` in place.

    python3 enrich_from_ide_db.py --dry-run          # report, change nothing
    python3 enrich_from_ide_db.py                    # apply
    python3 enrich_from_ide_db.py --db PATH --docs PATH

The IDE ships `Contents/Resources/deprecation_cache.db`, a small SQLite
file holding the control-member and event renames behind Project ▸ Update
Controls to API 2.0 and the Desktop-control deprecation warnings. It is
Xojo's own data rather than a reading of their documentation, and it
covers ground the bundled matrix does not -- but it is narrow (no
framework functions at all: no Left, InStr, GetFolderItem) and it is not
always right about where a migration should land, so nothing is imported
on its say-so alone.

**Every replacement is checked against the documentation's member index
before it is imported.** The IDE will tell you
`GridLinesHorizontal is deprecated.  You should use GridLinesHorizontalStyle
instead`, and that property does exist -- on the deprecated `ListBox`
class. `DesktopListBox` has no such member; its property is
`GridLineStyle`. Following that suggestion moves you from one deprecated
member to another on the class you are trying to leave. A replacement
that the index does not list on the destination class is reported and
skipped. The check reads members.tsv, the index the xojo skill's docs.py
generates, which lists exactly the members the documentation declares. An
earlier version of this tool tokenized the destination class's page as a
bag of words, and a prose mention could satisfy it: "Value" appears in
running text on pages whose control has no Value property, and several
wrong rows were imported that way before the check was tightened.

Two more rules keep the import conservative:

- **Blanks are filled; answers are never overwritten.** Where the matrix
  already records a replacement it was read off a documentation page and
  stays. That is what keeps the GridLineStyle answer we have.
- **Imported rows are marked** with `"src": "xojo-ide-db"`, so a later
  reader can tell which rows came from Xojo's table rather than their
  prose, and a row's note names the IDE release it came from.

Requires: a local Xojo installation (or --db) and the documentation
indexes the xojo skill builds (or --docs). Neither ships in this
repository.
"""
import argparse
import json
import pathlib
import re
import sqlite3
import sys

HERE = pathlib.Path(__file__).resolve().parent
COVERAGE = HERE.parent / "references" / "coverage.json"
DOCS = HERE.parent.parent / "xojo" / "references" / "documentation"
XOJO_APPS = pathlib.Path("/Applications/Xojo")
SRC = "xojo-ide-db"


def usable(path):
    """True if `path` is a deprecation database this tool can read.

    Old installations ship a file of the same name that is not SQLite at
    all (Xojo 2019r3.2's is a DOS executable), so the file has to be
    opened before it can be chosen.
    """
    try:
        con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        con.execute("select class_name, old_name, new_name from items "
                    "limit 1").fetchall()
        return True
    except sqlite3.Error:
        return False


# A Xojo release is [Year].[ReleaseNumber].[MinorRelease] -- 2026.2.1 --
# and older ones spell the same thing 2019R3.2. Both forms turn up in an
# installation path, either as the folder name or in parentheses after it.
VERSION = re.compile(r"(20\d{2})[.rR](\d+)(?:\.(\d+))?")


def parse_version(path):
    """(year, release, minor) for an installation path, or None.

    Read from the path rather than assumed from its order. Folder names
    under /Applications/Xojo are whatever the user calls them -- "Xojo
    138 (2024.4.2)" pairs a private numbering with the real version --
    so sorting the names sorts nothing meaningful: "Xojo 79" lands after
    "Xojo 2026.2.1", and that install is from 2019.
    """
    best = None
    for m in VERSION.finditer(str(path)):
        found = (int(m.group(1)), int(m.group(2)), int(m.group(3) or 0))
        if best is None or found > best:
            best = found
    return best


def find_db():
    """The newest usable deprecation_cache.db installed, or None.

    Ordered by the Xojo version in the path, with modification time as
    the tiebreak for an install whose path states no version. Both beat
    sorting by name; see parse_version.
    """
    found = sorted(XOJO_APPS.glob("*/*.app/Contents/Resources/"
                                  "deprecation_cache.db"),
                   key=lambda p: (parse_version(p) or (0, 0, 0),
                                  p.stat().st_mtime),
                   reverse=True)
    return next((p for p in found if usable(p)), None)


def bare_name(text):
    """The identifier in a member reference, without signature or owner.

    The events table stores whole signatures -- "Activated()",
    "CancelClosing() As Boolean", "Pressed(button As ToolbarItem)" -- and a
    documentation page names only the identifier. Comparing the stored
    string as written rejected all 122 event renames for a difference in
    punctuation rather than in substance.
    """
    tail = (text or "").split(".")[-1].strip()
    match = re.match(r"[A-Za-z_][A-Za-z0-9_]*", tail)
    return match.group(0).lower() if match else ""


class Docs:
    """Membership test: does <Class> document a member called <name>?

    Reads members.tsv, which has one row per member the documentation
    declares, so the test is exact: the qualified name either is a
    documented member or it is not. No prose mention can satisfy it.
    """

    def __init__(self, docs):
        self.members = set()
        self.classes = set()
        path = pathlib.Path(docs) / "members.tsv"
        for line in path.read_text(encoding="utf-8").splitlines()[1:]:
            name = line.split("\t", 1)[0].split("(")[0].strip().lower()
            if "." in name:
                self.members.add(name)
                self.classes.add(name.split(".", 1)[0])

    def has(self, cls, member):
        key = cls.lower()
        if key not in self.classes:
            return None            # no rows: cannot judge, so do not import
        return f"{key}.{bare_name(member)}" in self.members


def api2_class(coverage):
    """Deprecated class name -> its API 2 name, from the matrix itself."""
    out = {}
    for row in coverage:
        old = row["old"]
        if "." in old or row["cat"] not in ("IDE handles", "Source — type"):
            continue
        new = (row.get("new") or "").strip()
        if new and new != "—":
            out[old.lower()] = new.split("(")[0].split(" ")[0]
    return out


def pair(old):
    """(class, member) for a dotted symbol, else None."""
    head = old.split("(")[0].strip()
    return (head.split(".")[0].lower(),
            head.split(".")[-1].lower()) if "." in head else None


def ide_rows(db):
    # Read-only: the database lives inside the Xojo application bundle and
    # is never ours to modify, not even to leave a journal beside.
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    items = [(c, o, n, "member") for c, o, n in
             con.execute("select class_name, old_name, new_name from items")]
    events = [(c, o, n, "event") for c, o, n in con.execute(
        "select cl.name, e.old_name, e.new_name from events e "
        "join classes cl on cl.id = e.class_id")]
    return items + events


def plan(coverage, rows, docs, release):
    """Decide what to fill, add and reject. Returns (fills, adds, rejects)."""
    by_pair = {}
    for row in coverage:
        p = pair(row["old"])
        if p:
            by_pair.setdefault(p, row)
    classes = api2_class(coverage)
    fills, adds, rejects = [], [], []
    seen = set()
    for cls, old, new, kind in rows:
        old_name = old.split("(")[0].strip()
        new_name = (new or "").strip()
        if not old_name or not new_name:
            continue
        key = (cls.lower(), old_name.lower(), kind)
        if key in seen:
            continue
        seen.add(key)
        target = classes.get(cls.lower(), cls)
        verdict = docs.has(target, new_name)
        if verdict is not True:
            rejects.append({"class": cls, "old": old_name, "new": new_name,
                            "target": target,
                            "why": ("no documentation page for the "
                                    f"destination class {target}"
                                    if verdict is None else
                                    f"{target} documents no {new_name}")})
            continue
        p = (cls.lower(), old_name.lower())
        existing = by_pair.get(p)
        if existing is not None:
            current = (existing.get("new") or "").strip()
            if current and current != "—":
                continue           # we already have an answer; keep it
            fills.append((existing, cls, old_name, new_name, target, kind))
        else:
            adds.append((cls, old_name, new_name, target, kind, release))
    return fills, adds, rejects


def note_for(target, new_name, release, kind):
    what = "event" if kind == "event" else "member"
    shown = (new_name or "").split("(")[0].split(".")[-1].strip()
    note = (f"Replacement from the Xojo IDE's own deprecation database "
            f"({release}); checked against the documentation index, which "
            f"lists {target}.{shown} as a documented {what}. Imported "
            f"because no documentation page stated the {what} rename in "
            f"prose.")
    if kind == "event":
        note += (" Event renames are the IDE converter's job (Project ▸ "
                 "Update Controls to API 2.0) on placed controls; rename by "
                 "hand only in subclass event definitions you wrote "
                 "yourself. A menu handler declared `Handles <Menu>.Action` "
                 "KEEPS .Action -- renaming it unbinds the menu command, and "
                 "it still compiles.")
    return note


def build_row(cls, old_name, new_name, target, kind, release):
    web = cls.lower().startswith("web") or target.lower().startswith("web")
    if kind == "event":
        cat = "Out of scope" if web else "IDE handles"
    else:
        cat = "Out of scope" if web else "Source — member"
    return {
        "old": f"{cls}.{old_name}",
        "new": f"{target}.{new_name}",
        "kind": "Event" if kind == "event" else "Property",
        "cat": cat,
        "covered": False,
        "since": "",
        "status": "Deprecated",
        "note": note_for(target, new_name, release, kind),
        "origin": "member",
        "src": SRC,
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--db", type=pathlib.Path, default=None)
    ap.add_argument("--docs", type=pathlib.Path, default=DOCS)
    ap.add_argument("--coverage", type=pathlib.Path, default=COVERAGE)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    db = args.db or find_db()
    if db is None or not pathlib.Path(db).exists():
        sys.exit("no deprecation_cache.db found. Install Xojo, or pass --db "
                 "<path to Contents/Resources/deprecation_cache.db>.")
    if not (pathlib.Path(args.docs) / "members.tsv").is_file():
        sys.exit(f"no documentation indexes at {args.docs}. Build them with "
                 f"the xojo skill's docs.py, or pass --docs.")
    release = pathlib.Path(db).parts[3] if len(
        pathlib.Path(db).parts) > 3 else str(db)

    coverage = json.loads(args.coverage.read_text(encoding="utf-8"))
    before = len(coverage)
    docs = Docs(args.docs)
    fills, adds, rejects = plan(coverage, ide_rows(db), docs, release)

    for row, cls, old_name, new_name, target, kind in fills:
        row["new"] = f"{target}.{new_name}"
        row["note"] = note_for(target, new_name, release, kind)
        row["src"] = SRC
    coverage.extend(build_row(*a) for a in adds)
    coverage.sort(key=lambda r: r["old"].lower())

    print(f"source: {db}")
    print(f"filled {len(fills)} blank replacement(s), added {len(adds)} row(s)"
          f", rejected {len(rejects)}; coverage {before} -> {len(coverage)}")
    print("\nrejected -- the IDE names a replacement the destination class "
          "does not document:")
    for r in rejects:
        print(f"  {r['class']}.{r['old']} -> {r['new']}   ({r['why']})")
    if args.dry_run:
        print("\n--dry-run: coverage.json not written")
        return
    args.coverage.write_text(
        json.dumps(coverage, indent=1, ensure_ascii=False) + "\n",
        encoding="utf-8")
    print(f"\nwrote {args.coverage}")


if __name__ == "__main__":
    main()
