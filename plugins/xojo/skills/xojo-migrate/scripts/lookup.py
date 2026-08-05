#!/usr/bin/env python3
"""Query the bundled Xojo API1->API2 conversion data (stdlib only).

Usage:
  python3 lookup.py symbol <name>     rules + coverage entries matching a symbol
                                      (case-insensitive; try bare and dotted forms)
  python3 lookup.py rule <id>         full detail for one rule, e.g. c0r7
  python3 lookup.py category          list the 11 categories with rule counts
  python3 lookup.py category <id>     rule ids/names/confidence in one category
  python3 lookup.py tier <t> [cat]    rules at confidence tier high|medium|low|manual
                                      (manual-only is accepted as manual)
                                      optionally limited to one category id
"""
import json
import pathlib
import re
import sys

REFS = pathlib.Path(__file__).resolve().parent.parent / "references"
DATA = json.loads((REFS / "rules.json").read_text(encoding="utf-8"))
COVERAGE = json.loads((REFS / "coverage.json").read_text(encoding="utf-8"))


def tier_of(rule):
    return "manual" if rule["conf"] == "manual-only" else rule["conf"]


def print_rule(rule, cat, full=True):
    print(f"[{rule['id']}] {rule['name']}")
    print(f"  category:   {cat['id']} {cat['short']}")
    print(f"  confidence: {rule['conf']}   forms: {rule.get('forms', '-')}")
    print(f"  old: {rule.get('old', '-')}")
    print(f"  new: {rule.get('new', '-')}")
    if not full:
        print()
        return
    # `applies` and `conf` answer different questions: whether there is a
    # substitution to make at all, and how hard a human must look before making
    # it. A locate-only rule has no usable find/replace pair -- its `find` is
    # there to help you spot the shape, and running a substitution with it
    # either matches everywhere (empty find) or deletes the match (empty
    # replace). Say so on the line above the pattern, not in a footnote.
    if not rule.get("applies", True):
        print("  applies:  NO -- locate-only. Do NOT run this find/replace as a "
              "substitution; read `manual` and convert by hand.")
    for key in ("find", "replace", "note", "manual", "caveat"):
        if rule.get(key):
            print(f"  {key + ':':<9} {rule[key]}")
    for ex in rule.get("examples", []):
        print(f"  example:  before: {ex['b']}")
        print(f"            after:  {ex['a']}")
    print()


def iter_rules():
    for cat in DATA["categories"]:
        for rule in cat["rules"]:
            yield rule, cat


def cmd_symbol(name):
    q = name.lower().lstrip(".")
    ident = re.compile(r"[A-Za-z_][A-Za-z0-9_.]*")

    print(f"=== coverage matrix entries matching '{name}' ===")
    hits = 0
    for row in COVERAGE:
        old = row["old"].split("(")[0].lower()
        if q == old or q == old.split(".")[-1] or q in old:
            hits += 1
            since = row["since"].rstrip(".") if row["since"] else "-"
            note = f"   note: {row['note']}" if row["note"] else ""
            # `status` is Xojo's own Deprecated/Removed call. It decides whether
            # the symbol still compiles, which is the first thing you need to
            # know about it, so flag Removed loudly rather than burying it.
            status = row.get("status", "")
            flag = "  ** REMOVED - does not compile **" if status == "Removed" else ""
            print(f"  {row['old']} -> {row['new']}   [{row['cat']}] kind={row['kind']} "
                  f"status={status or '-'} since={since}{flag}{note}")
    if not hits:
        print("  (none: symbol is not in the deprecation matrix; it may already be API 2.0)")

    print(f"\n=== conversion rules matching '{name}' ===")
    matched = []
    for rule, cat in iter_rules():
        # match against the DEPRECATED side only (old field + left half of
        # the name's arrow), else a symbol matches rules that produce it
        name_old = re.split(r"→|->", rule.get("name", ""))[0]
        toks = set()
        for field in (rule.get("old", ""), name_old):
            for t in ident.findall(field):
                toks.add(t.lower())
                toks.add(t.split(".")[-1].lower())
        if q in toks:
            matched.append((rule, cat))
    if not matched:
        print("  (no rule: if the coverage entry above says Source, convert per its "
          "replacement + references/conversion-traps.md)")
    for rule, cat in matched:
        print_rule(rule, cat)


def cmd_rule(rid):
    for rule, cat in iter_rules():
        if rule["id"].lower() == rid.lower():
            print_rule(rule, cat)
            return
    sys.exit(f"no rule with id '{rid}' (ids look like c0r7; list with: category <catN>)")


def cmd_category(cid=None):
    if cid is None:
        for cat in DATA["categories"]:
            counts = {}
            for r in cat["rules"]:
                counts[tier_of(r)] = counts.get(tier_of(r), 0) + 1
            tiers = ", ".join(f"{k}:{v}" for k, v in sorted(counts.items()))
            print(f"  {cat['id']:6} {cat['short']:48} {len(cat['rules']):3} rules  ({tiers})")
        return
    for cat in DATA["categories"]:
        if cat["id"].lower() == cid.lower():
            print(f"{cat['id']} {cat['short']}\n{cat.get('intro', '')}\n")
            for r in cat["rules"]:
                print(f"  {r['id']:7} {r['conf']:12} {r['name']}")
            return
    sys.exit(f"no category '{cid}' (cat0..cat{len(DATA['categories']) - 1})")


def cmd_tier(t, cid=None):
    # `manual-only` is what rules.json stores and what scan.py and `lookup.py
    # rule` both print, so it has to be accepted here too -- reading
    # `c4r25(manual-only)` off a scan report and being told the tier does not
    # exist is a dead end. tier_of() already normalizes on the way out.
    t = "manual" if t.lower() == "manual-only" else t.lower()
    if t not in ("high", "medium", "low", "manual"):
        sys.exit("tier must be high | medium | low | manual (manual-only is accepted for manual)")
    if cid and not any(cat["id"].lower() == cid.lower() for cat in DATA["categories"]):
        sys.exit(f"no category '{cid}' (cat0..cat{len(DATA['categories']) - 1})")
    found = 0
    for rule, cat in iter_rules():
        if tier_of(rule) != t:
            continue
        if cid and cat["id"].lower() != cid.lower():
            continue
        found += 1
        old = rule.get("old", "") or rule["name"]
        print(f"  {rule['id']:7} {cat['id']:6} {old} -> {rule.get('new', '')}")
    if not found:
        where = f" in {cid}" if cid else ""
        print(f"  (no {t}-confidence rules{where})")


def main(argv):
    if len(argv) < 2:
        sys.exit(__doc__.strip())
    cmd, args = argv[1], argv[2:]
    if cmd == "symbol" and len(args) == 1:
        cmd_symbol(args[0])
    elif cmd == "rule" and len(args) == 1:
        cmd_rule(args[0])
    elif cmd == "category" and len(args) <= 1:
        cmd_category(args[0] if args else None)
    elif cmd == "tier" and 1 <= len(args) <= 2:
        cmd_tier(*args)
    else:
        sys.exit(__doc__.strip())


if __name__ == "__main__":
    main(sys.argv)
