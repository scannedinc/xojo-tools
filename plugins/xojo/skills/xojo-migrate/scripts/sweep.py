#!/usr/bin/env python3
"""Final-pass bare-name sweep for a Xojo API 1 -> API 2 migration (stdlib only).

Usage:
  python3 sweep.py /path/to/xojo/project [--format text|json]
                                         [--only NAME[,NAME...]]
                                         [--all]        # include dotted hits
                                         [--context]    # print the source line

WHY THIS EXISTS, and why scan.py is not enough.

Every member rule in this skill is anchored on a literal dot -- `\\.Member\\b`.
In Xojo a call on your own instance needs no receiver at all: `Invalidate` and
`Self.Invalidate` are the same call, and older code writes the first. 149 of
the 263 rules are therefore structurally blind to a form that is common in
exactly the code they target. On one real desktop project a `.Invalidate` rule
saw roughly one occurrence in seven.

That is worse than a low hit rate, because a rule that cannot match a form
still reports **zero remaining**, and zero reads as finished. This sweep exists
so the last question of a migration is answered by a list you clear rather than
by a rule's silence.

It is deliberately cruder and stricter than scan.py: for every symbol in the
coverage matrix it searches the bare name, ignoring dots and parentheses, and
every hit must be accounted for in writing (workflow phase 8).

Hits are split by the thing that matters:

  BARE     no receiver on the line -- an implicit-Self call, a global, or an
           unrelated local. NO RULE IN THIS SKILL CAN SEE THESE. This is the
           section the sweep is for.
  dotted   `x.Member` -- the rules can see these; shown only with --all, as a
           cross-check that the category passes actually ran.

THE FILTER, AND ITS ONE WEAKNESS.

Raw bare-name search returns thousands of hits and is unusable. What makes it
usable is filtering out every identifier the project itself declares --
properties, method names, parameters, locals, constants, control names --
gathered across ALL files, so a member declared in a superclass suppresses
matches in its subclasses.

The weakness is unavoidable and is printed, never silent: a project that
defines its own member with a framework name (TextFont, ForeColor, FillRect...)
has the framework's occurrences of that name filtered out too. Those names are
listed under "SUPPRESSED" and must be reviewed by hand. A sweep that hid them
quietly would be worse than no sweep, because it would report clean.
"""
import argparse
import json
import pathlib
import re
import sys
from collections import defaultdict

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from scan import code_only, collect_files, orphaned  # noqa: E402

REFS = pathlib.Path(__file__).resolve().parent.parent / "references"

# Identifiers that are Xojo keywords or so universal that a hit says nothing.
# Deliberately short: the sweep's value is its noise, and over-filtering here
# reintroduces exactly the blind spot it exists to close.
KEYWORDS = {
    "if", "then", "else", "elseif", "end", "sub", "function", "return", "var",
    "dim", "as", "new", "true", "false", "nil", "and", "or", "not", "for",
    "next", "each", "in", "to", "downto", "step", "while", "wend", "do",
    "loop", "until", "select", "case", "try", "catch", "finally", "raise",
    "self", "me", "super", "call", "const", "static", "public", "private",
    "protected", "shared", "global", "byref", "byval", "optional", "paramarray",
    "assigns", "handles", "implements", "inherits", "extends", "of", "is",
    "isa", "mod", "continue", "exit", "declare", "lib", "soft", "using",
    "namespace", "module", "class", "interface", "structure", "enum", "event",
    "property", "get", "set", "window", "string", "integer", "double", "boolean",
}

# ---------------------------------------------------------------- the census
DECL_PATTERNS = [
    # Sub / Function name, plus the whole parameter list (handled separately)
    re.compile(r"^\s*(?:Private\s+|Protected\s+|Public\s+|Shared\s+)*"
               r"(?:Sub|Function)\s+([A-Za-z_]\w*)", re.I),
    # A property declaration inside #tag Property / #tag ComputedProperty
    re.compile(r"^\s*(?:Private\s+|Protected\s+|Public\s+|Shared\s+)*"
               r"([A-Za-z_]\w*)\s*(?:\([^)]*\))?\s+As\s+", re.I),
    # #tag Constant, Name = kFoo
    re.compile(r"^\s*#tag\s+Constant\s*,\s*Name\s*=\s*([A-Za-z_]\w*)", re.I),
    # Begin <Class> <ControlName>  -- layout metadata, but the NAME is code
    re.compile(r"^\s*Begin\s+[A-Za-z_]\w*\s+([A-Za-z_]\w*)", re.I),
    # Sub Foo() Handles Bar.Action -- Bar is a menu item the project declares
    re.compile(r"\bHandles\s+([A-Za-z_]\w*)", re.I),
]
# `Var a, b As Integer, c As String` -- every name before an `As`, per clause.
VAR_LINE = re.compile(r"^\s*(?:Var|Dim)\s+(.+)$", re.I)
PARAM_LIST = re.compile(r"^\s*(?:Private\s+|Protected\s+|Public\s+|Shared\s+)*"
                        r"(?:Sub|Function)\s+[A-Za-z_]\w*\s*\((.*)\)", re.I)
PARAM_NAME = re.compile(r"(?:ByRef\s+|ByVal\s+|Optional\s+|ParamArray\s+|Assigns\s+)*"
                        r"([A-Za-z_]\w*)\s*(?:\([^)]*\))?\s*(?:As\b|=|$)", re.I)


def declared_names(files):
    """Every identifier the project declares, mapped name -> {where}.

    Gathered project-wide on purpose: a member declared in a superclass file
    must suppress matches in its subclasses, and nothing in a single file says
    which class it inherits from in a form worth parsing.
    """
    names = defaultdict(set)
    for path in files:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        where = path.name
        for line in text.splitlines():
            for rx in DECL_PATTERNS:
                m = rx.search(line)
                if m:
                    names[m.group(1).lower()].add(where)
            m = PARAM_LIST.match(line)
            if m:
                for part in m.group(1).split(","):
                    pm = PARAM_NAME.match(part.strip())
                    if pm:
                        names[pm.group(1).lower()].add(where)
            m = VAR_LINE.match(line)
            if m:
                # Strip the `As Type` tails, then take every bare identifier
                # left. `Var p As Picture, g As Graphics` yields p and g.
                decl = re.sub(r"\bAs\s+[A-Za-z_][\w.]*", " ", m.group(1), flags=re.I)
                decl = re.sub(r"=.*$", " ", decl)
                for tok in re.findall(r"[A-Za-z_]\w*", decl):
                    names[tok.lower()].add(where)
    for kw in KEYWORDS:
        names.pop(kw, None)
    return names


RULE_MEMBER = re.compile(r"^\\\.([A-Za-z_]\w*)")


def rule_member_names():
    """Member names that a rule converts, keyed off its `find` pattern.

    Swept in addition to the matrix because the two can disagree: `Invalidate`
    had rule c3r28 and no coverage row for a long time, so the inventory never
    mentioned it and this sweep could not see it either. Reading both means a
    rule can never be the only thing that knows about a symbol.
    """
    path = REFS / "rules.json"
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    out = {}
    for cat in data["categories"]:
        for rule in cat["rules"]:
            m = RULE_MEMBER.match(rule.get("find", "") or "")
            if m:
                out.setdefault(m.group(1), []).append(rule["id"])
    return out


def matrix_names():
    """Bare symbol name -> the coverage rows that use it."""
    coverage = json.loads((REFS / "coverage.json").read_text(encoding="utf-8"))
    out = defaultdict(list)
    for row in coverage:
        if row["cat"] in ("Out of scope", "IDE handles"):
            continue
        old = row["old"].split("(")[0]
        # `Xojo.Math.Max`, `Xojo.IO.FolderItem` and the rest of the old "new
        # framework" namespace are NAMESPACED GLOBALS, not instance members.
        # Their last component is a common word, so treating a bare `Max` or
        # `Round` as a receiverless member call buries the real findings under
        # hundreds of ordinary arithmetic lines.
        if old.startswith("Xojo."):
            continue
        name = old.split(".")[-1]
        if name and name.lower() not in KEYWORDS:
            out[name].append(row)
    return out


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("project", type=pathlib.Path)
    ap.add_argument("--format", choices=("text", "json"), default="text")
    ap.add_argument("--only", help="comma-separated symbol names to sweep")
    ap.add_argument("--all", action="store_true",
                    help="also list dotted hits (the rules can already see those)")
    ap.add_argument("--context", action="store_true", help="print each hit's source line")
    args = ap.parse_args()

    root = args.project
    if not root.exists():
        sys.exit(f"path does not exist: {root}")
    if root.is_file():
        root = root.parent
    src, binary, xml, manifests = collect_files(root)
    if not src:
        sys.exit(f"No Xojo source files (*.xojo_code etc.) found under {root}")
    stale = set(orphaned(src, manifests, root))
    live = [p for p in src if p not in stale]

    declared = declared_names(live)
    wanted = matrix_names()
    # A member name that only a RULE knows about still has to be swept.
    for name, rule_ids in rule_member_names().items():
        if name not in wanted and name.lower() not in KEYWORDS:
            wanted[name] = [{"old": f"(rule only).{name}", "new": "—",
                             "cat": "Source — member",
                             "note": f"No coverage row; known only to rule(s) "
                                     f"{', '.join(rule_ids)}."}]
    if args.only:
        keep = {n.strip().lower() for n in args.only.split(",")}
        wanted = {k: v for k, v in wanted.items() if k.lower() in keep}

    suppressed = {n: sorted(declared[n.lower()])
                  for n in wanted if n.lower() in declared}
    active = {n: rows for n, rows in wanted.items() if n.lower() not in declared}

    # Where each suppressed name is actually USED as a member, so the list can
    # rank itself. "The project declares Border" is a fact about a declaration;
    # it is not evidence that every `.Border` in the project is that property.
    # On a real migration the reviewer read the former as the latter and left
    # four `CurveShape.Border` sites unconverted. A name used in files that do
    # not declare it is the cheap signal that the two are not the same set.
    used_in = defaultdict(set)
    if suppressed:
        s_alt = "|".join(re.escape(n) for n in sorted(suppressed, key=len, reverse=True))
        s_rx = re.compile(r"(?<=\.)(" + s_alt + r")\b", re.I)
        for path in live:
            try:
                seg = code_only(path.read_text(encoding="utf-8", errors="replace"))
            except OSError:
                continue
            rel_p = str(path.relative_to(root))
            for mo in s_rx.finditer(seg):
                used_in[mo.group(1).lower()].add(rel_p)

    results = defaultdict(lambda: {"bare": [], "dotted": []})
    if not active:
        bare_rx = dotted_rx = None
    else:
        # ONE alternation over every swept name, not one regex per name per
        # line. Per-name search is O(files x lines x symbols) -- ~800 symbols
        # over 40,000 lines is 32M searches and takes minutes. Longest-first so
        # the alternation prefers `SelStart` over a hypothetical `Sel`.
        alt = "|".join(re.escape(n) for n in sorted(active, key=len, reverse=True))
        bare_rx = re.compile(r"(?<![\w.])(" + alt + r")\b", re.I)
        dotted_rx = re.compile(r"(?<=\.)(" + alt + r")\b", re.I)
    canonical = {n.lower(): n for n in active}

    for path in live:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        # Reuse scan.py's segmentation: layout metadata and #tag Note prose
        # would otherwise flood a sweep whose whole point is that you read
        # every line of its output.
        if bare_rx is None:
            continue
        code = code_only(text)
        orig = text.splitlines()
        rel = str(path.relative_to(root))
        for i, line in enumerate(code.splitlines()):
            if not line.strip():
                continue
            for m in bare_rx.finditer(line):
                name = canonical[m.group(1).lower()]
                results[name]["bare"].append((rel, i + 1, orig[i].strip()[:120]))
            if args.all:
                for m in dotted_rx.finditer(line):
                    name = canonical[m.group(1).lower()]
                    results[name]["dotted"].append((rel, i + 1, orig[i].strip()[:120]))

    # Split by what the bare form MEANS for each symbol, which is the whole
    # point of the sweep:
    #
    #   member-only  -- the matrix knows this name only as `Class.Member`, so a
    #                   bare occurrence is a receiverless call on the enclosing
    #                   instance. NO RULE CAN SEE IT. This is the blind spot.
    #   global       -- the matrix has a global form, so appearing bare is its
    #                   NORMAL shape and the global rules already cover it. Not
    #                   a discovery; useful only as a did-the-pass-run check.
    #
    # Without this split the report is drowned by Len/Mid/Ubound, which are
    # supposed to look like that.
    def is_global(name):
        return any("." not in r["old"].split("(")[0] for r in active[name])

    bare_hits = {n: v["bare"] for n, v in results.items() if v["bare"]}
    blind = {n: v for n, v in bare_hits.items() if not is_global(n)}
    globals_ = {n: v for n, v in bare_hits.items() if is_global(n)}
    n_blind = sum(len(v) for v in blind.values())
    n_glob = sum(len(v) for v in globals_.values())

    if args.format == "json":
        print(json.dumps({
            "scanned_files": len(live),
            "symbols_swept": len(active),
            "suppressed": suppressed,
            "receiverless_members": {n: [{"file": f, "line": ln, "text": t}
                                         for f, ln, t in v] for n, v in blind.items()},
            "global_forms": {n: len(v) for n, v in globals_.items()},
        }, indent=1))
        return

    def live_receivers(name):
        """Receivers where this name is valid API 2, from the matrix's live_on."""
        return sorted({r for row in active[name] for r in (row.get("live_on") or [])})

    def dump(title, group, blurb):
        print(f"== {title} ==")
        for line in blurb:
            print(line)
        print()
        # Symbols that are live API 2 on some receiver sink to the bottom. On a
        # real project `Close` and `Graphics` alone were two-thirds of the
        # receiverless hits, and `Self.Close` on a DesktopWindow is correct code
        # -- leading
        # with them buries the handful that are actually work. Phase 8 requires
        # accounting for every hit in writing, and a required step whose output
        # is five times longer than it needs to be is a step that gets skipped.
        for name in sorted(group, key=lambda n: (bool(live_receivers(n)), -len(group[n]))):
            rows = active[name]
            repl = next((r["new"] for r in rows if r["new"] not in ("—", "")), "—")
            recv = ", ".join(sorted({r["old"].split(".")[0]
                                     for r in rows if "." in r["old"]})[:4])
            live = live_receivers(name)
            flag = "   [LIKELY FINE]" if live else ""
            print(f"  {name:<26} {len(group[name]):>4} hit(s)   -> {repl}{flag}")
            # Printing a target signature next to a call that already passes an
            # argument reads as an invitation to carry the argument across, and
            # on a real migration it was taken: `invalidate(false)` next to
            # `Refresh(immediately As Boolean = False)` became `Refresh(False)`.
            # The two Booleans are different parameters -- API 1's was
            # EraseBackground -- so it compiles and silently changes redraw
            # behaviour. Nothing here can tell whether the parameters
            # correspond, which is exactly why the signature must not be
            # offered without the warning.
            passes_arg = sum(1 for _f, _l, t in group[name]
                             if re.search(re.escape(name) + r"\s*\(\s*[^)\s]", t, re.I))
            if passes_arg and "(" in repl:
                print(f"      ARGUMENT WARNING: {passes_arg} of these calls pass an "
                      f"argument, and the replacement takes one too. They are not "
                      f"necessarily the SAME parameter -- do not carry the argument "
                      f"across on the strength of this line. Check the rule "
                      f"(lookup.py symbol {name}) before converting.")
            if live:
                print(f"      LIVE API 2 on: {', '.join(live)} -- if the enclosing class is "
                      f"one of these, the call is already correct")
            if recv:
                print(f"      deprecated on: {recv}")
            shown = group[name] if args.context else group[name][:6]
            for f, ln, text in shown:
                print(f"      {f}:{ln}" + (f"   {text}" if args.context else ""))
            if not args.context and len(group[name]) > 6:
                print(f"      ... {len(group[name]) - 6} more (--context to see all)")
        if not group:
            print("  (none)")
        print()

    print(f"Bare-name sweep over {len(live)} source files under {root}")
    print(f"Symbols swept: {len(active)}   ({len(suppressed)} suppressed by the "
          f"project's own declarations)")
    n_live = sum(len(v) for n, v in blind.items()
                 if any(r.get("live_on") for r in active[n]))
    print(f"Receiverless member calls: {n_blind} across {len(blind)} symbols  "
          f"<- the blind spot")
    if n_live:
        print(f"  of which {n_live} are names that are LIVE API 2 on some receiver "
              f"(listed last, marked LIKELY FINE)")
    print(f"Global-form occurrences:   {n_glob} across {len(globals_)} symbols  "
          f"(rules cover these)\n")

    dump("Receiverless member calls -- NO RULE CAN SEE THESE", blind, [
        "   The matrix knows each of these names only as `Class.Member`, and every",
        "   hit below has no receiver on the line. In Xojo that means a call on the",
        "   enclosing instance (`Invalidate` for `Self.Invalidate`), and every member",
        "   rule in this skill is anchored on a literal dot, so none of them fired.",
        "",
        "   The receiver is the enclosing class: take its type from the file's",
        "   `Inherits` line or its `Begin <Class>` header, not from the line itself.",
        "   Account for every hit in writing -- converted, deliberately left",
        "   deprecated, or an unrelated identifier.",
    ])
    dump("Global-form occurrences -- expected shape, shown as a cross-check", globals_, [
        "   These names have a global form in the matrix, so appearing without a",
        "   receiver is normal and the global rules target them directly. A non-zero",
        "   count here is not a finding; it means that category's pass has not run,",
        "   or the leftovers are the compound-receiver calls hard rule 3 says to",
        "   leave deprecated. Confirm which, per symbol.",
    ])

    if suppressed:
        print(f"\n== SUPPRESSED: {len(suppressed)} names the project itself declares ==")
        print("   Filtered out to keep this list readable, and THIS IS THE FILTER'S")
        print("   ONE WEAKNESS: where the project defines its own member with a")
        print("   framework name, the framework's occurrences are hidden too. Review")
        print("   these by hand -- resolve each match individually, because a")
        print("   project-defined name makes matches ambiguous, not the symbol absent.")
        print("   Names marked ELSEWHERE are used as `.Member` in a file that does")
        print("   NOT declare them, so the declaration cannot account for every")
        print("   occurrence. Open those first.")

        def elsewhere(name):
            # `declared_names` reports basenames; `used_in` holds paths relative
            # to the project root. Compare basenames or the difference is never
            # taken and a name's own declaring file reads as evidence against it.
            decl = set(suppressed[name])
            return sorted(p for p in used_in.get(name.lower(), set())
                          if p.rsplit("/", 1)[-1] not in decl)

        others_of = {n: elsewhere(n) for n in suppressed}
        # Flagged first, then fewest files: a name used in one file it does not
        # declare is the one worth opening. A name used in forty is the
        # project's own and saying so is the useful part.
        for name in sorted(suppressed, key=lambda n: (not others_of[n], len(others_of[n]), n)):
            others = others_of[name]
            tag = f"   ELSEWHERE: {len(others)} file(s), e.g. {others[0]}" if others else ""
            print(f"   {name:<26} declared in {', '.join(suppressed[name][:3])}"
                  + (" ..." if len(suppressed[name]) > 3 else "") + tag)


if __name__ == "__main__":
    main()
