#!/usr/bin/env python3
"""Execute conversion rules over a project's code -- never its metadata.

Runs the bundled rules.json rules by id, or an ad-hoc edits file, across
a Xojo project. Matching is masked: a match counts only when its span is
byte-identical between the real line and its scan.code_only mask, which
suppresses -- and reports -- every hit inside string literals, comments,
`Begin` layout blocks and `#tag` metadata, including a match that starts
in code and runs into a string. On a real project the metadata hits
outnumbered code hits ten to one for some symbols; applying them
corrupts the IDE's stored layout.

Rules run IN THE ORDER NAMED. Order is load-bearing: a paren-removing
rule (Len(x) -> x.Length) must run before a rule whose find matches
inside argument lists, or `Left(s, Len(x))` never becomes matchable.
The category playbook's rule lists encode the safe orders.

Two rule sources, two dialects:
  --rules c0r0,c0r4   bundled rules; their find/replace is the Xojo IDE
                      Find-panel dialect, translated here exactly as
                      references/applying-rules-by-script.md specifies
                      ($1 -> \\1 backreferences, case-insensitive).
                      A rule with applies:false is LOCATE-ONLY: its
                      empty replace would delete matched text, so it is
                      skipped with a loud message, never run.
  --edits FILE        ad-hoc [{"label", "find", "replace"}, ...] in
                      PYTHON regex dialect, used verbatim.

Usage:
  python3 apply_rules.py <project> --rules c0r0,c0r4 [--apply]
                         [--path SUB]... [--verbose] [--format text|json]
  python3 apply_rules.py <project> --edits edits.json [--apply] ...

Dry run by default: counts, sample rewrites and suppressed hits, and
nothing written. --apply writes. (stdlib only)
"""
import argparse
import json
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from editing import read_source, write_source  # noqa: E402
from scan import code_only, collect_files  # noqa: E402

REFS = HERE.parent / "references"


def load_ruleset(ids_arg):
    """The named bundled rules, in the order named, dialect-translated.

    Locate-only rules (applies: false) are excluded with a loud stderr
    message: their find locates the shape, their replace is empty, and
    a driver that runs one deletes the matched text (the c3r54 hazard
    applying-rules-by-script.md documents).
    """
    data = json.loads((REFS / "rules.json").read_text(encoding="utf-8"))
    by_id = {r["id"]: r for cat in data["categories"] for r in cat["rules"]}
    runnable = []
    for rid in [i.strip() for i in ids_arg.split(",") if i.strip()]:
        rule = by_id.get(rid)
        if rule is None:
            sys.exit(f"unknown rule id: {rid}. "
                     f"python3 lookup.py rule <id> lists real ones.")
        if not rule["applies"]:
            print(f"SKIPPED {rid}: locate-only (applies: false) -- its "
                  f"empty replace would DELETE the matched text. Read "
                  f"`python3 lookup.py rule {rid}` and convert those "
                  f"sites by hand.", file=sys.stderr)
            continue
        # The IDE Find-panel dialect: $1 backreferences, case
        # sensitivity as an external checkbox. The translation below is
        # the one every rule's bundled examples are machine-checked
        # against (applying-rules-by-script.md).
        replace = re.sub(r"\$(\d)", r"\\\1", rule["replace"])
        runnable.append({
            "label": f"{rid}  {rule['name']}",
            "pattern": re.compile(rule["find"], re.IGNORECASE),
            "replace": replace,
        })
    if not runnable:
        sys.exit("every rule named is locate-only; there is nothing "
                 "mechanical to run. Convert those sites by hand.")
    return runnable


def load_edits(path):
    try:
        with open(path, encoding="utf-8") as f:
            edits = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        sys.exit(f"cannot read the edits file: {e}")
    runnable = []
    for e in edits:
        try:
            runnable.append({"label": e.get("label") or e["find"],
                             "pattern": re.compile(e["find"]),
                             "replace": e["replace"]})
        except (KeyError, re.error) as exc:
            sys.exit(f"bad edit entry {e!r}: {exc}")
    if not runnable:
        sys.exit("the edits file is empty.")
    return runnable


def apply_rule(rule, text):
    """One rule over one file's text: (new_text, hits, skips, matches).

    hits are (lineno, before, after) per changed line; matches counts
    individual applied substitutions (a line holding two converts as
    two -- the count the checkpoint differ's per-symbol deltas must
    reconcile against); skips are (lineno, reason) for matches
    suppressed as non-code. The code test is span identity: a match
    applies only when the real line and the code_only mask agree
    byte-for-byte across the WHOLE matched span, so a match starting in
    code and running into a string is suppressed, not half-applied. A
    line's trailing \\r is held out of the match entirely, so a
    $-anchored rule cannot swallow a CRLF file's carriage return.
    """
    pat, rep = rule["pattern"], rule["replace"]
    real_lines = text.split("\n")
    masked_lines = code_only(text).split("\n")
    hits, skips = [], []
    matches = 0
    for i, (real, masked) in enumerate(zip(real_lines, masked_lines)):
        cr = "\r" if real.endswith("\r") else ""
        if cr:
            real, masked = real[:-1], masked[:-1]
        out, last, before = [], 0, real
        for m in pat.finditer(real):
            if masked[m.start():m.end()] != real[m.start():m.end()]:
                skips.append((i + 1, "in a string, comment or metadata"))
                continue
            out.append(real[last:m.start()])
            out.append(m.expand(rep))
            last = m.end()
            matches += 1
        if last:
            out.append(real[last:])
            real_lines[i] = "".join(out) + cr
            hits.append((i + 1, before, "".join(out)))
    return "\n".join(real_lines), hits, skips, matches


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("project", type=pathlib.Path,
                    help="project directory (or its .xojo_project file)")
    src_group = ap.add_mutually_exclusive_group(required=True)
    src_group.add_argument("--rules",
                           help="comma-separated bundled rule ids, run in "
                                "this order (IDE dialect, translated)")
    src_group.add_argument("--edits",
                           help="ad-hoc edits JSON (Python regex dialect)")
    ap.add_argument("--path", action="append", default=[],
                    help="limit to files whose project-relative path "
                         "starts with this prefix (repeatable)")
    ap.add_argument("--apply", action="store_true",
                    help="write the edits (default is a dry run)")
    ap.add_argument("--verbose", action="store_true",
                    help="print every rewrite and every suppressed hit")
    ap.add_argument("--format", choices=("text", "json"), default="text")
    args = ap.parse_args(argv)

    project = args.project
    if project.is_file():
        project = project.parent
    if not project.is_dir():
        sys.exit(f"not a project directory: {args.project}")
    rules = (load_ruleset(args.rules) if args.rules
             else load_edits(args.edits))

    files, _, _, _ = collect_files(project)
    if args.path:
        prefixes = tuple(p.rstrip("/") for p in args.path)
        files = [f for f in files
                 if str(f.relative_to(project)).startswith(prefixes)]
    if not files:
        sys.exit("no source files under that project (and --path filter).")

    cache = {f: read_source(f) for f in files}
    changed = set()
    results = []
    for rule in rules:
        applied, skipped, samples = 0, 0, []
        for f in files:
            new_text, hits, skips, matches = apply_rule(rule, cache[f])
            if hits:
                cache[f] = new_text
                changed.add(f)
                applied += matches
                samples.extend((f, ln, b, a) for ln, b, a in hits)
            skipped += len(skips)
            if args.verbose:
                for ln, why in skips:
                    print(f"        suppressed {f}:{ln} ({why})")
        results.append({"label": rule["label"], "applied": applied,
                        "suppressed_non_code": skipped})
        if args.format == "text":
            zero = "   <-- ZERO" if not applied else ""
            extra = (f"   [{skipped} suppressed in non-code]"
                     if skipped else "")
            print(f"{applied:5}  {rule['label']}{zero}{extra}")
            shown = samples if args.verbose else samples[:3]
            for f, ln, b, a in shown:
                print(f"        {f.name}:{ln}: {b.strip()[:60]}")
                print(f"          -> {a.strip()[:60]}")
            if len(samples) > len(shown):
                print(f"        ... {len(samples) - len(shown)} more "
                      f"(--verbose lists all)")

    if args.apply:
        for f in sorted(changed):
            write_source(f, cache[f])

    total = sum(r["applied"] for r in results)
    if args.format == "json":
        print(json.dumps({"rules": results, "total": total,
                          "files_changed": sorted(str(f) for f in changed),
                          "applied": args.apply}, indent=1))
    else:
        note = "" if args.apply else "  (dry run, nothing written)"
        print(f"\ntotal: {total} across {len(changed)} file(s){note}")


if __name__ == "__main__":
    main()
