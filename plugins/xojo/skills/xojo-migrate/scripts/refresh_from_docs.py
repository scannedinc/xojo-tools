#!/usr/bin/env python3
"""Cross-check coverage.json against the xojo skill's generated doc indexes.

Maintenance tool, not part of a migration. The sibling xojo skill regenerates
its classes.tsv/members.tsv indexes from the live documentation about weekly;
this matrix is committed and does not refresh itself. Run this after a docs
rebuild to pull the documentation's facts back into the matrix and to hear
about anything the two datasets disagree on.

    python3 refresh_from_docs.py --dry-run       # report, change nothing
    python3 refresh_from_docs.py                 # apply the safe fixes
    python3 refresh_from_docs.py --docs PATH     # a non-sibling index location

What it applies (safe, additive, never overwrites an answer):

- **Backfills empty `since` values** from the indexes' `deprecated_in` column,
  which is read off the documentation's own deprecation banners. An existing
  `since` is never changed, and every value is normalized to drop a trailing
  period ("2019r2." -> "2019r2").
- **Re-verifies the `src: xojo-ide-db` rows** against members.tsv, the index
  of members the documentation actually lists, and rewrites each row's
  confirmation sentence to claim exactly that much. The original import
  checked the destination page as a bag of words, which a prose mention could
  satisfy; the index lookup is member-level.

What it only reports (each needs a human decision):

- Status conflicts: rows the matrix calls Deprecated/Removed whose symbol the
  indexes list as current, and IDE-imported replacements that members.tsv
  does not know.
- Replacement disagreements between the matrix and the indexes.
- Deprecations the indexes carry on SURVIVING desktop classes that the matrix
  lacks: candidates for new rows. Members of classes that are themselves
  deprecated are not candidates -- the matrix records those renames at class
  level -- and the iOS/Web/Android surface is out of scope.

Requires the documentation indexes the xojo skill builds (or --docs). They do
not ship in this repository; build them with that skill's docs.py.
"""
import argparse
import json
import os
import pathlib
import re
import stat
import sys

HERE = pathlib.Path(__file__).resolve().parent
COVERAGE = HERE.parent / "references" / "coverage.json"
DOCS = HERE.parent.parent / "xojo" / "references" / "documentation"

# The out-of-scope surfaces, by name prefix. Path checks catch the rest.
FOREIGN = ("ios", "mobile", "web", "android", "xojo.")

# The sentence the original bag-of-words import wrote, and the sentence this
# tool writes: rewriting matches either, so a repaired note repairs again to
# the same text and the pass stays idempotent. The member half can carry a
# whole signature ("Pressed(button As ToolbarItem)"), so it is matched
# lazily up to the period that the next sentence's text anchors.
CONFIRMED = re.compile(
    r"(?:confirmed against the [A-Za-z0-9_]+ documentation page, "
    r"which lists .*?|checked against the documentation index, "
    r"which lists .*? as a documented (?:member|event))"
    r"\.(?= Imported because)"
)


def norm_name(text):
    """A joinable symbol: no signature, no page-title decorations."""
    text = re.sub(r"\(.*", "", text or "").strip()
    text = text.removesuffix(" (deprecated)").strip()
    return text


def norm_release(text):
    return (text or "").strip().rstrip(".")


def load_tsv(path):
    rows = []
    lines = path.read_text(encoding="utf-8").splitlines()
    header = lines[0].split("\t")
    for line in lines[1:]:
        cells = line.split("\t")
        cells += [""] * (len(header) - len(cells))
        rows.append(dict(zip(header, cells)))
    return rows


class Indexes:
    """The two TSVs, keyed for the joins this tool needs."""

    def __init__(self, docs):
        classes = load_tsv(docs / "classes.tsv")
        members = load_tsv(docs / "members.tsv")

        # Every row for a normalized name, deprecated rows first so the
        # deprecation facts win when a name has both a deprecated page and a
        # current member ("Database.Connect" has each).
        self.by_name = {}
        for row in classes + members:
            name = norm_name(row["name"]).lower()
            if name:
                self.by_name.setdefault(name, []).append(row)
        for rows in self.by_name.values():
            rows.sort(key=lambda r: "deprecated" not in r.get("flags", ""))

        # "Screen Method" / "Window Method" pages describe the global
        # function, whose symbol in code is the bare name.
        for row in classes:
            name = norm_name(row["name"])
            if name.lower().endswith(" method"):
                bare = name[: -len(" method")].strip().lower()
                self.by_name.setdefault(bare, []).append(row)

        self.member_names = {
            norm_name(row["name"]).lower() for row in members
        }
        # kind per member ("event", "method", "property", ...), so a note can
        # say what the index actually records rather than echo the row.
        self.member_kinds = {
            norm_name(row["name"]).lower(): row.get("kind", "")
            for row in members
        }
        # The current (unflagged) surface, for validating live_on entries: a
        # name is only "live" where the index documents it without a
        # deprecated flag.
        self.current_members = {
            norm_name(row["name"]).lower()
            for row in members
            if "deprecated" not in row.get("flags", "")
        }
        self.current_classes = {
            norm_name(row["name"]).lower()
            for row in classes
            if "deprecated" not in row.get("flags", "")
            and "." not in norm_name(row["name"])
        }
        self.deprecated_classes = {
            norm_name(row["name"]).lower()
            for row in classes
            if "deprecated" in row.get("flags", "") and "." not in row["name"]
        }

    def deprecated_row(self, old, kind):
        """The docs row carrying the deprecation facts for a matrix row.

        Event rows never join: the IDE-imported event renames collide with
        same-named current methods (WebControl.Close the method vs Close the
        event), and members.tsv records the current member. A Method row
        prefers the docs' "<Name> Method" page over the same-named class
        page -- the Window global function and the Window class are separate
        deprecations with different releases and replacements.
        """
        if kind == "Event":
            return None
        rows = [
            row
            for row in self.by_name.get(norm_name(old).lower(), [])
            if "deprecated" in row.get("flags", "")
        ]
        if kind == "Method":
            for row in rows:
                if norm_name(row["name"]).lower().endswith(" method"):
                    return row
        return rows[0] if rows else None

    def lists_member(self, reference):
        """Does members.tsv list the Class.Member a replacement names?"""
        head = norm_name(reference).split()[0] if norm_name(reference) else ""
        return head.lower() in self.member_names


# The per-release tables on the docs' Deprecations page: "###### 2019
# release 2" headings over "| Symbol | Deprecated |" rows. They date many
# symbols whose detail pages carry no banner, so they are the second
# backfill source after the banners.
RELEASE_HEADING = re.compile(r"^#{2,6}\s+(\d{4}) release (\d+(?:\.\d+)?)\s*$")
TABLE_ROW = re.compile(r"^\|\s*(.+?)\s*\|\s*(Deprecated|Removed)\s*\|\s*$")
MD_LINK = re.compile(r"\[([^\]]+)\]\([^)]*\)")


def table_dates(docs):
    """symbol (lowercased) -> the release its table row says deprecated it.

    The page runs newest release first, so overwriting on every occurrence
    leaves the oldest listing -- the first deprecation -- as the value.
    """
    path = docs / "resources" / "deprecations.md"
    if not path.is_file():
        return {}
    out = {}
    release = ""
    for line in path.read_text(encoding="utf-8").splitlines():
        heading = RELEASE_HEADING.match(line)
        if heading:
            release = f"{heading.group(1)}r{heading.group(2)}"
            continue
        row = TABLE_ROW.match(line)
        if not row or not release or row.group(2) != "Deprecated":
            continue
        name = MD_LINK.sub(r"\1", row.group(1))
        name = norm_name(name.split(" (")[0])
        if name and " " not in name:
            out[name.lower()] = release
    return out


def backfill_since(coverage, indexes, tables):
    filled, normalized = [], 0
    for row in coverage:
        clean = norm_release(row.get("since"))
        if clean != row.get("since"):
            row["since"] = clean
            normalized += 1
        if clean:
            continue
        docs_row = indexes.deprecated_row(row["old"], row.get("kind"))
        version = norm_release(docs_row["deprecated_in"]) if docs_row else ""
        version = version or tables.get(norm_name(row["old"]).lower(), "")
        if version:
            row["since"] = version
            filled.append((row["old"], version))
    return filled, normalized


def reverify_ide_rows(coverage, indexes):
    """Rewrite the IDE-import confirmation sentence to what the index shows.

    The original import's sentence claimed confirmation "against the
    documentation page", a bag-of-words check a prose mention could satisfy.
    Where the member index really does list the replacement, the sentence is
    rewritten to claim exactly that much (the same sentence a fresh
    enrich_from_ide_db.py import writes); where it does not, the row is
    reported for a human decision.
    """
    rewritten, unknown = [], []
    for row in coverage:
        if row.get("src") != "xojo-ide-db":
            continue
        target = norm_name(row.get("new", ""))
        if not target:
            continue
        if indexes.lists_member(target):
            # What the index calls the replacement, not what the row calls
            # the deprecated member: WebApplication.Open is an event whose
            # row says kind Property, and the sentence must not repeat that.
            kind = indexes.member_kinds.get(target.lower(), "")
            what = "event" if kind == "event" else "member"
            sentence = (
                f"checked against the documentation index, which lists "
                f"{target} as a documented {what}."
            )
            new_note, count = CONFIRMED.subn(sentence, row.get("note", ""))
            if count and new_note != row.get("note", ""):
                row["note"] = new_note
                rewritten.append(row["old"])
        else:
            unknown.append((row["old"], target))
    return rewritten, unknown


def report_disagreements(coverage, indexes):
    status, replacement = [], []
    for row in coverage:
        # A row can assert something other than a deprecation -- Redim's
        # status is Superseded, meaning "current but the docs prefer another
        # form" -- and the indexes agreeing it is current is agreement.
        if row.get("status") not in ("Deprecated", "Removed"):
            continue
        name = norm_name(row["old"]).lower()
        rows = indexes.by_name.get(name, [])
        if not rows or row.get("kind") == "Event":
            continue
        docs_row = indexes.deprecated_row(row["old"], row.get("kind"))
        if docs_row is None:
            # A row that names its own symbol as the replacement records a
            # deprecated OVERLOAD of a member that survives (Crypto.HMAC,
            # Report.Run). The indexes list the current member, so the
            # bare-name comparison would report a conflict that is not one.
            ours = norm_name(row.get("new", "")).lower().replace("—", "")
            if not (ours and same_replacement(norm_name(row["old"]).lower(), ours)):
                status.append((row["old"], row["status"]))
            continue
        # The em dash is the matrix's deliberate "no replacement recorded";
        # comparing it against the docs' class-blanket notice reports noise.
        ours = norm_name(row.get("new", "")).lower().replace("—", "")
        theirs = norm_name(docs_row.get("replacement", "")).lower()
        if ours and theirs and not same_replacement(ours, theirs):
            replacement.append(
                (row["old"], row.get("new"), docs_row.get("replacement"))
            )
    return status, replacement


def same_replacement(ours, theirs):
    """Wording differences are not conflicts.

    The docs side is harvested prose, so it arrives as "the Database.AddRow
    method signature that returns a rowid", a blanket class name where the
    matrix answers member-by-member, or a name with emphasis warts. Compare
    the first symbol-shaped token of each side, and accept a prefix match in
    either direction (matrix "DesktopUIControl.Refresh(...)" against docs
    "DesktopUIControl").
    """

    def head(text):
        text = re.sub(r"[*`]", "", text)
        text = re.sub(r"^the\s+", "", text.strip())
        text = re.split(r"\s+(?:or|and)\s+|\s*/\s*", text)[0]
        return re.split(r"[(\s]", text)[0].strip(".")

    a, b = head(ours), head(theirs)
    if a == b or a.startswith(b + ".") or b.startswith(a + "."):
        return True
    # A notice that names the member without its class ("ShowPrinterDialog")
    # against the matrix's qualified form ("PrinterSetup.ShowPrinterDialog").
    return a.split(".")[-1] == b or b.split(".")[-1] == a


def report_candidates(coverage, indexes):
    """Deprecations on surviving desktop classes the matrix does not know."""
    known = {norm_name(row["old"]).lower() for row in coverage}
    out = []
    for name, rows in sorted(indexes.by_name.items()):
        row = rows[0]
        if "deprecated" not in row.get("flags", "") or name in known:
            continue
        if " " in name or name.startswith(FOREIGN):
            continue
        path = row.get("path", "")
        if any(f"/{part}/" in path for part in ("ios", "mobile", "web", "android")):
            continue
        owner = name.split(".")[0]
        if "." in name and owner in indexes.deprecated_classes:
            continue  # class-level rename already covers it
        if "." not in name:
            # Bare names are classes (recorded at class level long ago) or
            # keywords and globals, which want a hand decision, not a
            # candidate row -- Redim is advice, not a deprecation.
            continue
        out.append(
            (
                norm_name(row["name"]),
                norm_release(row.get("deprecated_in", "")),
                norm_name(row.get("replacement", "")),
            )
        )
    return out


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--docs", type=pathlib.Path, default=DOCS)
    parser.add_argument("--coverage", type=pathlib.Path, default=COVERAGE)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    if not all((args.docs / name).is_file()
               for name in ("classes.tsv", "members.tsv")):
        sys.exit(
            f"no documentation indexes at {args.docs}. Build them with the "
            f"xojo skill's docs.py, or pass --docs."
        )

    coverage = json.loads(args.coverage.read_text(encoding="utf-8"))
    indexes = Indexes(args.docs)

    filled, normalized = backfill_since(coverage, indexes, table_dates(args.docs))
    rewritten, unknown = reverify_ide_rows(coverage, indexes)
    status, replacement = report_disagreements(coverage, indexes)
    candidates = report_candidates(coverage, indexes)

    print(f"since: {len(filled)} backfilled, {normalized} normalized")
    for old, version in filled[:15]:
        print(f"  {old} <- {version}")
    if len(filled) > 15:
        print(f"  ... and {len(filled) - 15} more")
    print(f"ide-db notes: {len(rewritten)} re-verified against members.tsv")

    if unknown:
        print(f"\nIDE-imported replacements members.tsv does NOT list "
              f"({len(unknown)}) -- review each:")
        for old, target in unknown:
            print(f"  {old} -> {target}")
    if status:
        print(f"\nmatrix says deprecated, indexes say current "
              f"({len(status)}) -- review each:")
        for old, state in status:
            print(f"  {old} ({state})")
    if replacement:
        print(f"\nreplacement disagreements ({len(replacement)}) -- review each:")
        for old, ours, theirs in replacement:
            print(f"  {old}: matrix {ours!r} vs docs {theirs!r}")
    if candidates:
        print(f"\ndeprecations on surviving desktop classes the matrix lacks "
              f"({len(candidates)}) -- candidates for new rows:")
        for name, version, target in candidates:
            print(f"  {name} -> {target or '(none)'} [{version or '?'}]")

    if args.dry_run:
        print("\n--dry-run: coverage.json not written")
        return
    # coverage.json is curated by hand, so write a sibling .part and
    # rename: an interrupted run never leaves it truncated. realpath
    # first: os.replace on the symlink itself would break the link. The
    # rename needs only directory write permission, so refuse a
    # write-protected file explicitly.
    dest = pathlib.Path(os.path.realpath(args.coverage))
    if dest.exists() and not os.access(dest, os.W_OK):
        sys.exit(f"{args.coverage} is not writable")
    tmp = dest.with_name(dest.name + ".part")
    try:
        tmp.write_text(
            json.dumps(coverage, indent=1, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        if dest.exists():
            os.chmod(tmp, stat.S_IMODE(os.stat(dest).st_mode))
        os.replace(tmp, dest)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    print(f"\nwrote {args.coverage}")


if __name__ == "__main__":
    main()
