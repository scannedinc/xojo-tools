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
    The replacement narrows instead ("KeyCount" picks Dictionary.Count
    from the four rows owning bare Count), and candidates that survive
    the narrowing still settle when they agree on the member's new name:
    ListBox and PopupMenu both rename ListCount to .RowCount.
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


def ide_disagrees(rows, new):
    """True when the IDE's proposed replacement contradicts the matrix.

    The IDE's suggestion is not always the API 2 destination. Verified
    against Xojo 2026.2.1: it reports "GridLinesHorizontal is deprecated.
    You should use GridLinesHorizontalStyle instead", and that property
    does exist -- on the deprecated ListBox class. DesktopListBox has no
    such member; its property is GridLineStyle. Taking the suggestion
    moves you from one deprecated member to another on the class you are
    leaving. The matrix's replacements were read off the API 2 class
    pages, so where the two disagree the matrix is the one to follow --
    but silently preferring it would hide that the IDE said otherwise,
    and the reader is looking at the IDE's message.
    """
    if not new or not rows:
        return False
    known = [r for r in rows if known_replacement(r)]
    if not known:
        return False
    wanted = _tokens(_head(new))
    return bool(wanted) and not any(_tokens(_head(r["new"])) & wanted
                                    for r in known)


def _new_leaf(row):
    """The member name this row's replacement renames the call site to.

    None when the row is not a member-to-member rename: a global row, an
    unrecorded replacement, or a replacement that is not a dotted member
    (Database.Error -> DatabaseException redirects; it does not rename).
    """
    if "." not in (row.get("old") or "").split("(")[0]:
        return None
    if not known_replacement(row):
        return None
    head = re.split(r"[(\s]", _head(row.get("new", "")))[0].rstrip(".")
    if "." not in head:
        return None
    return head.split(".")[-1].lower()


def is_ambiguous(rows):
    """True when the candidate rows do not settle on one replacement.

    Several rows owning a name is not itself ambiguity: `Date` and
    `Xojo.Core.Date` both become `DateTime`, so the reader has nothing to
    resolve. But rows whose replacement is *unrecorded* do not agree with
    each other either -- three classes owning `.InsertRow` with no
    documented replacement is three open questions, not a settled join,
    and reading it as agreement printed it as a mechanical rename.

    Member renames also agree when their replacements differ only by
    class: a bare `ListCount` warning may belong to DesktopListBox or
    DesktopPopupMenu, but both rows rename the site to `.RowCount`, so
    the edit is settled either way and there is nothing to resolve.
    """
    if len(rows) < 2:
        return False
    if any(not known_replacement(r) for r in rows):
        return True
    if len({(r.get("new") or "").strip().lower() for r in rows}) == 1:
        return False
    leaves = {_new_leaf(r) for r in rows}
    return None in leaves or len(leaves) > 1


def action_for(rows, rules, confirmed=True, disagrees=False):
    """What this symbol asks of the reader."""
    if rows and all(r.get("cat") == IDE_BUCKET for r in rows):
        return CONVERTER
    if disagrees:
        # The reader is holding two different answers; that is never a
        # rename to make without looking.
        return REVIEW
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


def vet(doc):
    """Accept or refuse an analyze document. Returns (fatal, warnings).

    xojoctl emits a document for every outcome. Refused (fatal is the
    message to exit with): documents whose ANALYSIS never ran -- command
    failures (an error object), a project that would not load (outcome
    open_errors, whose diagnostics are load errors, not analysis), and
    ok:false with nothing in it. Accepted: outcome project_errors, an
    analysis that RAN on a project that does not compile -- the normal
    condition of a freshly converted tree -- whose diagnostics are the
    worklist, errors included; `warnings` carries the stderr advisories.
    checkpoint.py imports this so both consumers hold one policy.
    """
    outcome = doc.get("outcome") or "unknown"
    session = (doc.get("result") or {}).get("session") or {}
    bracket_broken = session.get("closed") is False
    if (doc.get("error") or outcome == "open_errors"
            or (doc.get("ok") is False and not doc.get("diagnostics"))):
        err = doc.get("error") or {}
        detail = err.get("message") or doc.get("summary") or ""
        if bracket_broken and not doc.get("error") and outcome != "open_errors":
            return ("the analysis ran, but the session could not close the "
                    "project -- it is still open in the IDE. Close it "
                    "(xojoctl close --discard) before editing anything, "
                    "then re-run the checkpoint.", [])
        if outcome == "open_errors":
            return (f"the project would not load, so nothing was analyzed"
                    f"{': ' + detail if detail else ''}.\n"
                    f"Fix the load errors (open the project by hand to see "
                    f"them), or take the scanner path (workflow phase 2b): "
                    f"python3 scan.py <project-dir>", [])
        return (f"the analysis did not run: outcome {outcome}"
                f"{': ' + detail if detail else ''}.\n"
                f"Nothing here says anything about deprecations. Fix the "
                f"IDE connection and re-run, or take the scanner path "
                f"(workflow phase 2b): python3 scan.py <project-dir>", [])
    warnings = []
    if doc.get("ok") is False:
        if bracket_broken:
            warnings.append(
                "warning: the session could not close the project -- it "
                "is still open in the IDE. Close it (xojoctl close "
                "--discard) before editing anything. The diagnostics "
                "below are still the worklist.")
        elif outcome == "project_errors":
            warnings.append(
                "note: analyze exited nonzero (outcome project_errors) -- "
                "the project does not compile, which is normal after the "
                "phase-1 converter. The diagnostics below are the "
                "worklist, errors included.")
        else:
            warnings.append(
                f"note: analyze exited nonzero (outcome {outcome}); the "
                f"diagnostics below are still the worklist.")
    return None, warnings


def build(doc):
    """Group an analyze document into a worklist. Lossless: every diagnostic
    leaves in exactly one of errors / groups / unmatched / other."""
    errors, other, unmatched, related = [], [], [], []
    groups = {}
    matrix = load_matrix()
    for d in doc.get("diagnostics") or []:
        if d.get("severity") == "error":
            errors.append(d)
            continue
        parsed = parse_deprecation(d.get("message", ""))
        if not parsed:
            # The two "%1 is deprecated..." templates are not the only
            # deprecation findings the IDE writes. Its string table also
            # carries "This class is based on a deprecated class", the
            # old-style constructor and destructor warnings, and the
            # deprecated-Windows menu bar error -- all migration work in a
            # different wording. Filing those with the unused-variable
            # warnings would dismiss them.
            (related if "deprecat" in d.get("message", "").lower()
             else other).append(d)
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
            disagrees = ide_disagrees(rows, new)
            group = groups[key] = {
                "symbol": old, "replacement": new,
                "action": action_for(rows, rules, confirmed, disagrees),
                "ambiguous": is_ambiguous(rows),
                "ide_disagrees": disagrees,
                "rules_confirmed": confirmed,
                "rows": [{"old": r["old"], "new": r["new"], "cat": r["cat"],
                          "note": r.get("note", "")}
                         for r in rows],
                "rules": rules,
                "categories": sorted({r["cat_name"] for r in rules}),
                "sites": [],
            }
        site = {
            "message": d.get("message", ""),
            "where": d.get("position") or d.get("location") or "?",
            "line": d.get("line"), "source": d.get("source", ""),
        }
        # locate.py's enrichment, when the document passed through it.
        for key in ("file", "file_line", "resolution"):
            if key in d:
                site[key] = d[key]
        group["sites"].append(site)
    ordered = sorted(groups.values(),
                     key=lambda g: (ACTION_ORDER.index(g["action"]),
                                    -len(g["sites"]), g["symbol"].lower()))
    wl = {"errors": errors, "groups": ordered, "unmatched": unmatched,
          "related": related, "other": other,
          "counts": {"diagnostics": len(doc.get("diagnostics") or []),
                     "symbols": len(ordered),
                     "sites": sum(len(g["sites"]) for g in ordered)}}
    located = doc.get("located")
    if isinstance(located, dict) and located.get("project_root"):
        wl["project_root"] = located["project_root"]
    return wl


def wrap(text, indent, width=78):
    import textwrap
    return textwrap.fill(text, width=width, initial_indent=indent,
                         subsequent_indent=indent)


def located_at(d, root):
    """' [path:line]' when locate.py resolved this diagnostic, else ''."""
    if not d.get("file") or d.get("file_line") is None:
        return ""
    path = d["file"]
    if root:
        try:
            path = str(pathlib.Path(path).resolve().relative_to(
                pathlib.Path(root).resolve()))
        except ValueError:
            pass
    return f"  [{path}:{d['file_line']}]"


def report(wl):
    c = wl["counts"]
    root = wl.get("project_root")
    print(f"{c['diagnostics']} diagnostics from the IDE: "
          f"{c['sites']} deprecation site(s) across {c['symbols']} symbol(s), "
          f"{len(wl['unmatched'])} unrecognized, {len(wl['related'])} in "
          f"another wording, {len(wl['other'])} other warning(s), "
          f"{len(wl['errors'])} error(s)")
    print()

    if wl["errors"]:
        print(f"== Build errors ({len(wl['errors'])}) -- fix before converting ==")
        print("  These do not compile today. Removed API 1.0 symbols land here.")
        for d in wl["errors"]:
            print(f"  {d.get('position') or d.get('location')}: {d['message']}"
                  f"{located_at(d, root)}")
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
            if g["ide_disagrees"]:
                targets = ", ".join(r["new"] for r in g["rows"]
                                    if known_replacement(r))
                print(wrap(f"THE IDE'S SUGGESTION DISAGREES WITH THE MATRIX. "
                           f"It proposes {g['replacement']}; the matrix, read "
                           f"off the documentation, says {targets}. The "
                           f"IDE sometimes names another member of the "
                           f"deprecated class, which is not a migration "
                           f"target. Verify on the API 2 class page before "
                           f"converting.", "      "))
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
                print(f"      at {site['where']}"
                      f"{located_at(site, root)}{src}")
            if len(g["sites"]) > SITES_SHOWN:
                print(f"      ... {len(g['sites']) - SITES_SHOWN} more site(s)"
                      f" -- --format json lists them all")
        print()

    if wl["unmatched"]:
        print(f"== Deprecations the matrix does not cover ({len(wl['unmatched'])}) ==")
        print("  The IDE flagged these; no coverage row owns the name. Convert")
        print("  from the IDE's own replacement, and treat it as a matrix gap.")
        for d in wl["unmatched"]:
            print(f"  {d.get('position') or d.get('location')}: {d['message']}"
                  f"{located_at(d, root)}")
        print()

    if wl["related"]:
        print(f"== Deprecation findings in another wording ({len(wl['related'])}) ==")
        print("  Migration work the standard warning form does not cover: a")
        print("  class or control whose Super is deprecated, an old-style")
        print("  constructor, a menu bar mixing Desktop and deprecated types.")
        print("  Convert these too; they carry no symbol to look up.")
        for d in wl["related"]:
            print(f"  {d.get('position') or d.get('location')}: {d['message']}"
                  f"{located_at(d, root)}")
        print()

    if wl["other"]:
        print(f"== Other warnings ({len(wl['other'])}) ==")
        print("  Not deprecation findings. Judge them on their own merits;")
        print("  this migration neither fixes nor licenses ignoring them.")
        for d in wl["other"]:
            print(f"  {d.get('position') or d.get('location')}: {d['message']}")
        print()

    if not wl["groups"] and not wl["unmatched"] and not wl["related"]:
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
    fatal, warnings = vet(doc)
    if fatal:
        sys.exit(fatal)
    for w in warnings:
        print(w, file=sys.stderr)

    wl = build(doc)
    if args.format == "json":
        print(json.dumps(wl, indent=1))
    else:
        report(wl)


if __name__ == "__main__":
    main()
