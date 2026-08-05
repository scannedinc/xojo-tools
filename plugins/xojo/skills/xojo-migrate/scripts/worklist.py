#!/usr/bin/env python3
"""Turn the Xojo IDE's analysis into a migration worklist (stdlib only).

Usage:
  python3 -m xojoctl analyze --json | python3 worklist.py
  python3 worklist.py analyze.json [--format text|json]

The IDE's deprecation warnings already name a replacement -- "Left is
deprecated.  You should use String.Left instead" -- and that is exactly the
problem this script exists to solve. The message reads as a complete
instruction, so it invites the rename, and for a handful of symbols the
rename is the part that compiles and is still wrong: `InStr`'s not-found
sentinel moves from 0 to -1, several functions change index base, and
`Date.TotalSeconds` -> `DateTime.SecondsFrom1970` shifts the epoch by 66
years. The IDE never mentions any of that. The bundled matrix does.

So this joins each warning to the conversion rules that cover it and leads
with the sites that need more than a rename. What it does NOT do is decide
anything: it reports rule ids for `lookup.py rule <id>`, and where the join
is ambiguous it says so rather than picking.

Two facts about the real messages shape the join, both captured from a live
IDE rather than assumed:

  - Member deprecations carry NO receiver ("ListCount is deprecated.  You
    should use RowCount instead"), so the receiver cannot key the join.
    The replacement disambiguates instead: "RowCount" picks
    ListBox.ListCount over PopupMenu.ListCount.
  - The IDE spells names in its own casing ("Listbox") and puts two spaces
    after "deprecated.", so all matching is case-insensitive and
    whitespace-tolerant.

The warning being present is itself authoritative: the compiler resolved the
receiver to raise it, so unlike a scan.py hit, no receiver check is needed to
believe the *site*. The caveats still apply to the *conversion*.
"""
import argparse
import json
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
REFS = HERE.parent / "references"
sys.path.insert(0, str(HERE))

import scan  # noqa: E402  -- symbol_tokens is the vetted rule-name extractor

# What a site needs from the reader, most demanding first. These strings are
# the section headings too, so they say what to do, not what tier it is.
HAND = "hand conversion required"
REVIEW = "read the caveat before renaming"
MECHANICAL = "mechanical rename"
CONVERTER = "the IDE converter handles this"
ACTION_ORDER = (HAND, REVIEW, MECHANICAL, CONVERTER)

# Coverage rows in this bucket are control/class renames that Project ▸
# Update Controls to API 2.0 performs. They must not pull in the member
# rules of their category: a `ListBox` type warning shares its name with
# every ListBox member rule, and attaching all 46 buried the real traps
# under a wall of text for a site that needs no source edit at all.
IDE_BUCKET = "IDE handles"

# "<Old> is deprecated[.  You should use <New> instead]". Anchored at the
# start so a message merely *mentioning* deprecation cannot parse, and the
# replacement is taken whole -- it can be a bare name, a dotted name, or a
# constructor signature with its own punctuation.
DEPRECATED = re.compile(
    r"^(?P<old>[A-Za-z_][\w.]*)\s+is\s+deprecated\b\s*\.?"
    r"(?:\s*You\s+should\s+use\s+(?P<new>.+?)\s+instead\s*\.?)?$",
    re.IGNORECASE | re.DOTALL)

# Filler that carries no identifying information. Deliberately excludes
# words that ARE decisive replacement names: `Text -> String` is settled
# entirely by "String", and dropping it emptied the token set, which turned
# both narrowings off for one of the most common symbols in the matrix.
GENERIC = frozenset(("the", "a", "an", "as", "instead", "new", "of", "to",
                     "or", "and", "is", "use", "you", "should"))

# What coverage.json writes when no replacement is recorded. It is an
# absence of knowledge, not a value: several rows all carrying it are not
# rows that agree.
UNRECORDED = frozenset(("", "-", "—", "–", "?", "none", "n/a"))

# Caps on the text report only; --format json always carries everything.
RULES_SHOWN = 5
SITES_SHOWN = 12
ROWS_SHOWN = 3


def parse_deprecation(message):
    """(old, new) for a deprecation warning, or None for anything else."""
    m = DEPRECATED.match(" ".join((message or "").split()))
    if not m:
        return None
    new = m.group("new")
    return m.group("old"), new.strip() if new else None


def load_matrix():
    coverage = json.loads((REFS / "coverage.json").read_text(encoding="utf-8"))
    rules = json.loads((REFS / "rules.json").read_text(encoding="utf-8"))
    by_name = {}
    for row in coverage:
        bare = row["old"].split("(")[0].strip().split(".")[-1].lower()
        by_name.setdefault(bare, []).append(row)
    return {"by_name": by_name, "rules": rules}


def _tokens(text):
    found = {t.lower() for t in re.findall(r"[A-Za-z_][A-Za-z0-9_]*", text or "")}
    # Filtering to nothing would silently disable the narrowing that uses
    # this set, so keep the raw tokens rather than return an empty one.
    return (found - GENERIC) or found


def known_replacement(row):
    """True when the matrix actually records a replacement for this row."""
    return (row.get("new") or "").strip().lower() not in UNRECORDED


def _head(text):
    """The replacement expression, without the commentary that follows it.

    A rule's `new` often continues into prose, and that prose names other
    members: c3r20's reads "...CellBorderColorAt(row, col) As ColorGroup is
    the ONLY cell-border member... There are NO per-side
    CellBorder{Bottom|Left|Right|Top}At members." Tokenizing the whole field
    finds "Left" there and attaches a ListBox border rule to a `Left(s, 5)`
    string call. Only the expression itself is the replacement.
    """
    text = (text or "").strip()
    cut = len(text)
    for mark in (". ", " is ", " -- ", "\n"):
        found = text.find(mark)
        if 0 <= found < cut:
            cut = found
    return text[:cut]


def match_rows(old, new, matrix):
    """Coverage rows for a warned symbol.

    Returns every row owning the bare name, narrowed by the IDE's replacement
    when that narrowing is decisive. An indecisive replacement returns the
    full candidate set on purpose -- the caller reports the ambiguity, and a
    wrong caveat is worse than an acknowledged unknown.
    """
    rows = matrix["by_name"].get(old.split(".")[-1].lower(), [])
    if len(rows) < 2 or not new:
        return list(rows)
    wanted = _tokens(new)
    if not wanted:
        return list(rows)
    narrowed = [r for r in rows if _tokens(r.get("new", "")) & wanted]
    return narrowed or list(rows)


def rules_for(rows, matrix, new=None):
    """Rules that convert one of these rows' symbols toward `new`.

    Returns (rules, confirmed). Selection uses scan.symbol_tokens, which
    already extracts the identifiers naming the symbol a rule *converts*:
    it takes only the left of the rule name's arrow, and strips parameter
    lists, quoted doc excerpts and `As <Type>` tails. Matching the raw text
    instead handed a `Timer.Mode` warning the StrComp rule, because
    "mode" is one of StrComp's parameter names -- and since that rule is
    manual-only it then drove the whole group to the top of the report.

    The IDE's replacement filters second, since one name can be converted
    by rules belonging to different classes. When that filter would empty
    the set, the rules are kept but `confirmed` is False: an unrelated rule
    must never be believed enough to escalate a group.
    """
    names = {row["old"].split("(")[0].strip().split(".")[-1].lower()
             for row in rows}
    out = []
    for cat in matrix["rules"]["categories"]:
        for rule in cat["rules"]:
            if not (names & scan.symbol_tokens(rule)):
                continue
            out.append({"id": rule["id"], "conf": rule["conf"],
                        "cat": cat["id"], "cat_name": cat["short"],
                        "name": rule.get("name", ""),
                        "applies": rule.get("applies", True),
                        "manual": rule.get("manual", ""),
                        "note": rule.get("note", ""),
                        "new": rule.get("new", "")})
    confirmed = True
    wanted = _tokens(_head(new)) if new else set()
    if wanted and out:
        kept = [r for r in out if _tokens(_head(r["new"])) & wanted]
        if kept:
            out = kept
        else:
            confirmed = False
    for rule in out:
        rule.pop("new", None)
    return out, confirmed


def is_ambiguous(rows):
    """True when the candidate rows do not settle on one replacement.

    Several rows owning a name is not itself ambiguity: `Date` and
    `Xojo.Core.Date` both become `DateTime`, so the reader has nothing to
    resolve. But rows whose replacement is *unrecorded* do not agree with
    each other either -- three classes owning `.InsertRow` with no
    documented replacement is three open questions, not a settled join,
    and reading it as agreement printed it as a mechanical rename.
    """
    if len(rows) < 2:
        return False
    if any(not known_replacement(r) for r in rows):
        return True
    return len({(r.get("new") or "").strip().lower() for r in rows}) > 1


def action_for(rows, rules, confirmed=True):
    """What this symbol asks of the reader."""
    if rows and all(r.get("cat") == IDE_BUCKET for r in rows):
        return CONVERTER
    if confirmed and any(r["conf"] == "manual-only" or not r["applies"]
                         for r in rules):
        return HAND
    if is_ambiguous(rows):
        return REVIEW          # the join could not settle which row applies
    if not confirmed:
        return REVIEW          # rules found, none confirmed to match
    if not rules:
        return REVIEW          # a matrix row with no rule: convert from the row
    if any(not known_replacement(r) for r in rows):
        # "Mechanical rename" is the one heading that licenses editing
        # without reading anything, so it must never cover a row whose
        # replacement the matrix does not record.
        return REVIEW
    if any(r["conf"] in ("medium", "low") or r["manual"] for r in rules):
        return REVIEW
    return MECHANICAL


def build(doc):
    """Group an analyze document into a worklist. Lossless: every diagnostic
    leaves in exactly one of errors / groups / unmatched / other."""
    errors, other, unmatched = [], [], []
    groups = {}
    matrix = load_matrix()
    for d in doc.get("diagnostics") or []:
        if d.get("severity") == "error":
            errors.append(d)
            continue
        parsed = parse_deprecation(d.get("message", ""))
        if not parsed:
            other.append(d)
            continue
        old, new = parsed
        rows = match_rows(old, new, matrix)
        if not rows:
            unmatched.append(d)
            continue
        key = (old.lower(), (new or "").lower())
        group = groups.get(key)
        if group is None:
            converter = bool(rows) and all(r.get("cat") == IDE_BUCKET
                                           for r in rows)
            rules, confirmed = (([], True) if converter
                                else rules_for(rows, matrix, new))
            group = groups[key] = {
                "symbol": old, "replacement": new,
                "action": action_for(rows, rules, confirmed),
                "ambiguous": is_ambiguous(rows),
                "rules_confirmed": confirmed,
                "rows": [{"old": r["old"], "new": r["new"], "cat": r["cat"],
                          "note": r.get("note", "")}
                         for r in rows],
                "rules": rules,
                "categories": sorted({r["cat_name"] for r in rules}),
                "sites": [],
            }
        group["sites"].append({
            "message": d.get("message", ""),
            "where": d.get("position") or d.get("location") or "?",
            "line": d.get("line"), "source": d.get("source", ""),
        })
    ordered = sorted(groups.values(),
                     key=lambda g: (ACTION_ORDER.index(g["action"]),
                                    -len(g["sites"]), g["symbol"].lower()))
    return {"errors": errors, "groups": ordered, "unmatched": unmatched,
            "other": other,
            "counts": {"diagnostics": len(doc.get("diagnostics") or []),
                       "symbols": len(ordered),
                       "sites": sum(len(g["sites"]) for g in ordered)}}


def wrap(text, indent, width=78):
    import textwrap
    return textwrap.fill(text, width=width, initial_indent=indent,
                         subsequent_indent=indent)


def report(wl):
    c = wl["counts"]
    print(f"{c['diagnostics']} diagnostics from the IDE: "
          f"{c['sites']} deprecation site(s) across {c['symbols']} symbol(s), "
          f"{len(wl['unmatched'])} unrecognized, {len(wl['other'])} other "
          f"warning(s), {len(wl['errors'])} error(s)")
    print()

    if wl["errors"]:
        print(f"== Build errors ({len(wl['errors'])}) -- fix before converting ==")
        print("  These do not compile today. Removed API 1 symbols land here.")
        for d in wl["errors"]:
            print(f"  {d.get('position') or d.get('location')}: {d['message']}")
        print()

    for action in ACTION_ORDER:
        group = [g for g in wl["groups"] if g["action"] == action]
        if not group:
            continue
        print(f"== {action.upper()} ({len(group)} symbol(s), "
              f"{sum(len(g['sites']) for g in group)} site(s)) ==")
        if action == HAND:
            print("  A rename here compiles and is still wrong. Convert by")
            print("  hand, following the named rules.")
        elif action == REVIEW:
            print("  Resolve the caveat before renaming.")
        elif action == CONVERTER:
            print("  Project ▸ Update Controls to API 2.0 performs these")
            print("  (workflow phase 1). No source edit belongs here.")
        for g in group:
            rids = " ".join(f"{r['id']}({r['conf']})" for r in g["rules"]) or "-"
            print(f"  {g['symbol']} -> {g['replacement'] or '(none named)'}"
                  f"   {len(g['sites'])} site(s)")
            if g["ambiguous"]:
                olds = ", ".join(r["old"] for r in g["rows"])
                print(wrap(f"AMBIGUOUS: the IDE named no receiver and the "
                           f"replacement did not settle it. Candidates: "
                           f"{olds}. Confirm the receiver before converting.",
                           "      "))
            for row in g["rows"][:ROWS_SHOWN]:
                print(f"      matrix: {row['old']} -> {row['new']}  [{row['cat']}]")
            if len(g["rows"]) > ROWS_SHOWN:
                print(f"      ... {len(g['rows']) - ROWS_SHOWN} more candidate "
                      f"row(s) -- lookup.py symbol {g['symbol']}")
            if not g["rules"]:
                # With no rule attached, the coverage row's own note is the
                # only guidance this group has.
                for row in g["rows"]:
                    if row.get("note"):
                        print(wrap(f"note: {row['note']}", "      "))
                        break
                else:
                    print("      No rule covers this symbol; convert from the "
                          "matrix replacement above.")
            if not g["rules_confirmed"]:
                print(wrap("The rules below name this symbol but none "
                           "converts it toward what the IDE proposed, so "
                           "they may govern a different class. Confirm "
                           "before using them.", "      "))
            if g["rules"]:
                print(wrap(f"rules ({len(g['rules'])}): {rids}", "      "))
            # A rule's NAME states the hazard in one line ("InStr/IndexOf
            # result comparison: '... > 0'"), where its `manual` field runs
            # to paragraphs. Printing every manual for every rule buried the
            # traps it was meant to surface, so name them and point at
            # lookup.py for the instructions.
            interesting = [r for r in g["rules"]
                           if r["conf"] == "manual-only" or not r["applies"]] \
                if action == HAND else g["rules"]
            for rule in interesting[:RULES_SHOWN]:
                print(wrap(f"{rule['id']}  {rule['name']}", "        "))
            if len(interesting) > RULES_SHOWN:
                print(f"        ... {len(interesting) - RULES_SHOWN} more")
            if g["rules"]:
                first = (interesting or g["rules"])[0]["id"]
                print(f"        read before converting: "
                      f"python3 lookup.py rule {first}")
            for site in g["sites"][:SITES_SHOWN]:
                src = f"   |{site['source']}" if site["source"] else ""
                print(f"      at {site['where']}{src}")
            if len(g["sites"]) > SITES_SHOWN:
                print(f"      ... {len(g['sites']) - SITES_SHOWN} more site(s)"
                      f" -- --format json lists them all")
        print()

    if wl["unmatched"]:
        print(f"== Deprecations the matrix does not cover ({len(wl['unmatched'])}) ==")
        print("  The IDE flagged these; no coverage row owns the name. Convert")
        print("  from the IDE's own replacement, and treat it as a matrix gap.")
        for d in wl["unmatched"]:
            print(f"  {d.get('position') or d.get('location')}: {d['message']}")
        print()

    if wl["other"]:
        print(f"== Other warnings ({len(wl['other'])}) -- not deprecations ==")
        print("  Outside this migration's scope; left for the user to judge.")
        for d in wl["other"]:
            print(f"  {d.get('position') or d.get('location')}: {d['message']}")
        print()

    if not wl["groups"] and not wl["unmatched"]:
        print("No deprecation warnings in this analysis.")
        print("Note what that does and does not mean: Analyze Project compiles")
        print("only the platform the IDE is running on, so other platforms'")
        print("#If branches were never looked at. Run scan.py and sweep.py")
        print("before calling the migration finished.")


def main(argv=None, stdin=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("document", nargs="?",
                    help="analyze --json output; omit to read stdin")
    ap.add_argument("--format", choices=("text", "json"), default="text")
    args = ap.parse_args(argv)

    stream = stdin if stdin is not None else sys.stdin
    try:
        raw = (pathlib.Path(args.document).read_text(encoding="utf-8")
               if args.document else stream.read())
    except OSError as e:
        sys.exit(f"cannot read {args.document}: {e}")
    try:
        doc = json.loads(raw)
    except ValueError as e:
        sys.exit(f"not JSON: {e}. Pipe `xojoctl analyze --json` in, or name "
                 f"a file holding its output.")
    if not isinstance(doc, dict) or "diagnostics" not in doc:
        sys.exit("this is not an `xojoctl analyze --json` document: no "
                 "`diagnostics` key.")
    # xojoctl emits a document for every outcome, including a failed
    # connection, a timeout and no-project-open -- each with an empty
    # diagnostics list. Summarizing one of those as "no deprecation
    # warnings" would report an analysis that never ran as a finished
    # migration, which is the worst answer this script could give.
    if doc.get("ok") is False or doc.get("error"):
        err = doc.get("error") or {}
        detail = err.get("message") or doc.get("summary") or ""
        sys.exit(f"the analysis did not run: outcome "
                 f"{doc.get('outcome') or 'unknown'}"
                 f"{': ' + detail if detail else ''}.\n"
                 f"Nothing here says anything about deprecations. Fix the "
                 f"IDE connection and re-run, or take the scanner path "
                 f"(workflow phase 2b): python3 scan.py <project-dir>")

    wl = build(doc)
    if args.format == "json":
        print(json.dumps(wl, indent=1))
    else:
        report(wl)


if __name__ == "__main__":
    main()
