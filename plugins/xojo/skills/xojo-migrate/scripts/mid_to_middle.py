#!/usr/bin/env python3
"""Audit Mid's lower bounds, then convert Mid -> Middle (1-based to 0-based).

API 1.0 `Mid` CLAMPS a start below 1; `Middle` does not. A loop written
`For i = 0 To n ... Mid(s, i, 1)` works today because of the clamp and
breaks after a mechanical decrement. So the audit is the default and is
inseparable: every run walks each site's enclosing `For` stack, finds
the bound feeding the start argument, and groups sites by bound -- on a
real project a few hundred sites collapsed to sixteen distinct bounds,
turning read-every-site into a one-screen review (conversion-traps.md
section 1).

--apply REFUSES while the audit proves a risky site (a start that can
be < 1) unless --force. Bounds it cannot evaluate -- no enclosing loop,
For Each, a non-literal bound, a start fed by a parameter -- warn
loudly and go to the hand-review list without blocking: those are
answered by reading, and making --force routine would be worse.

The conversion simplifies the decrement instead of emitting (X) - 1
everywhere: literal L -> L-1 computed now, `X+1` -> `X`, identifier ->
`X - 1`, anything else -> `(X) - 1`. The global form requires a legal
receiver; the METHOD form (s.Mid(...)) is textually type-blind -- a
user class's own Mid would convert too -- so every method-form site is
listed in the dry preview for review before --apply.

Usage:  python3 mid_to_middle.py <project> [--apply] [--force]
                                 [--format text|json]

Dry run by default; --apply writes. (stdlib only)
"""
import argparse
import json
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from editing import (SIGNATURE, find_call, masked_pairs,  # noqa: E402
                     read_source, split_args, write_source)
from scan import collect_files, mask_line  # noqa: E402

MID = re.compile(r"(?<![\w.])mid\s*\(", re.I)
DOTMID = re.compile(r"(?<=\.)mid\s*\(", re.I)
IDENT = re.compile(r"^[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*$")
SIMPLE = re.compile(r"^[A-Za-z_]\w*$")
# `For i = A To B` / `For i As Integer = A DownTo B` / `For Each x In y`
FOR_RE = re.compile(r"^\s*For\s+(Each\s+)?([A-Za-z_]\w*)(.*)$", re.I)
FOR_RANGE = re.compile(
    r"^(?:\s+As\s+[A-Za-z_][\w.]*)?\s*=\s*(.+?)\s+(To|DownTo)\s+(.+?)"
    r"(?:\s+Step\s+.+)?\s*$", re.I)
NEXT_RE = re.compile(r"^\s*Next\b\s*([A-Za-z_]\w*)?", re.I)
# a start argument the audit can reason about: var, var+K, var-K
START = re.compile(r"^([A-Za-z_]\w*)\s*(?:([+-])\s*(\d+))?$")


def decrement(expr):
    """Return expr - 1, simplified."""
    e = expr.strip()
    if re.fullmatch(r"\d+", e):
        return str(int(e) - 1)
    m = re.fullmatch(r"(.+?)\s*\+\s*1", e)
    if m:
        return m.group(1).strip()
    if SIMPLE.fullmatch(e):
        return f"{e} - 1"
    return f"({e}) - 1"


def classify(start, stack):
    """One site's audit verdict from its start expression and For stack.

    Returns (bucket_label, verdict, detail) where verdict is "safe",
    "risky" or "review". A literal start is its own evidence. A
    variable start is judged by the innermost enclosing For whose
    counter it is: bound + offset < 1 relies on the clamp. Everything
    the walk cannot settle is "review" -- never silently safe.
    """
    e = start.strip()
    if re.fullmatch(r"\d+", e):
        return ("LITERAL", "risky" if int(e) < 1 else "safe",
                f"literal start {e}")
    m = START.fullmatch(e)
    if not m:
        return ("COMPLEX", "review", f"start {e!r} is not a counter form")
    var = m.group(1).lower()
    offset = int(m.group(3) or 0) * (-1 if m.group(2) == "-" else 1)
    for each, counter, bound in reversed(stack):
        if counter != var:
            continue
        if each:
            return (f"{m.group(1)} (For Each)", "review",
                    "the counter is a For Each element, not an index")
        if bound is None:
            return (f"{m.group(1)}=?", "review",
                    "the For bound could not be parsed")
        if re.fullmatch(r"-?\d+", bound):
            low = int(bound) + offset
            return (f"{m.group(1)}={bound}",
                    "risky" if low < 1 else "safe",
                    f"lower bound {bound}, start offset {offset:+d} "
                    f"-> effective {low}")
        return (f"{m.group(1)}={bound}", "review",
                f"non-literal lower bound {bound!r}")
    return (f"{m.group(1)} (no loop)", "review",
            "no enclosing For declares this counter")


def mid_sites(real, masked):
    """Every Mid call on this line: (kind, start_expr) with kind
    "global"|"method"; the audit and the converter must agree on what a
    site is, so both go through this."""
    sites = []
    for kind, pat, start_index in (("method", DOTMID, 0),
                                   ("global", MID, 1)):
        pos = 0
        while True:
            mo = pat.search(masked, pos)
            if not mo:
                break
            span = find_call(masked, mo.start())
            if span is None:
                sites.append((kind, None, mo.start(), None))
                pos = mo.end()
                continue
            o, c = span
            args = split_args(real[o + 1:c])
            if len(args) <= start_index or not args[start_index].strip():
                sites.append((kind, "", mo.start(), (o, c, args)))
            else:
                sites.append((kind, args[start_index].strip(), mo.start(),
                              (o, c, args)))
            pos = c + 1
    return sites


def audit(cache):
    """Walk every file's For stacks; classify every Mid start."""
    from collections import Counter, defaultdict
    histogram = Counter()
    risky, review = [], []
    total = 0
    for path, text in cache.items():
        stack = []  # (is_for_each, counter_lower, lower_bound_expr|None)
        for i, (real, masked) in enumerate(masked_pairs(text)):
            if real.strip() and not masked.strip():
                continue
            if SIGNATURE.match(masked):
                stack = []          # a new method body: loops reset
            f = FOR_RE.match(masked)
            if f:
                each = bool(f.group(1))
                counter = f.group(2).lower()
                bound = None
                if not each:
                    r = FOR_RANGE.match(f.group(3))
                    if r:
                        bound = (r.group(3) if r.group(2).lower() == "downto"
                                 else r.group(1)).strip()
                stack.append((each, counter, bound))
            elif NEXT_RE.match(masked) and stack:
                named = NEXT_RE.match(masked).group(1)
                if named:
                    while stack and stack[-1][1] != named.lower():
                        stack.pop()
                if stack:
                    stack.pop()
            for kind, start, _, parsed in mid_sites(real, masked):
                if start is None or start == "" or parsed is None:
                    continue    # the converter reports these shapes
                total += 1
                label, verdict, detail = classify(start, stack)
                histogram[label] += 1
                entry = (f"{path}:{i + 1}  start={start!r}  {detail}")
                if verdict == "risky":
                    risky.append(entry)
                elif verdict == "review":
                    review.append(entry)
    return {"total": total, "histogram": dict(histogram),
            "risky": risky, "review": review}


def convert(cache, apply_):
    converted, changed = [], set()
    skipped, not_framework, unbalanced = [], [], []
    for path in sorted(cache):
        pairs = masked_pairs(cache[path])
        lines = [real for real, _ in pairs]
        file_changed = False
        for i, (real, masked) in enumerate(pairs):
            if real.strip() and not masked.strip():
                continue
            if not MID.search(masked) and not DOTMID.search(masked):
                continue
            before = real
            real, masked, records = _convert_line(
                real, masked, path, i + 1, skipped, not_framework,
                unbalanced)
            if real != before:
                lines[i] = real
                converted.extend(records)
                file_changed = True
        if file_changed:
            cache[path] = "\n".join(lines)
            changed.add(path)
    if apply_:
        for path in sorted(changed):
            write_source(path, cache[path])
    return converted, skipped, not_framework, unbalanced, sorted(changed)


def _convert_line(real, masked, path, lineno, skipped, not_framework,
                  unbalanced):
    records = []
    # Method form first, like the field draft: s.Mid(start[, len]).
    # Type-blind by nature; each conversion is recorded for the preview.
    for kind, pat, start_index in (("method", DOTMID, 0),
                                   ("global", MID, 1)):
        pos = 0
        while True:
            mo = pat.search(masked, pos)
            if not mo:
                break
            span = find_call(masked, mo.start())
            if span is None:
                unbalanced.append(f"{path}:{lineno} the call spans lines "
                                  f"or its parens do not balance")
                pos = mo.end()
                continue
            o, c = span
            args = split_args(real[o + 1:c])
            if kind == "global":
                if len(args) < 2:
                    not_framework.append(
                        f"{path}:{lineno} Mid({real[o + 1:c].strip()[:40]})"
                        f" -- one argument is not the framework Mid; "
                        f"probably a user method, left alone")
                    pos = mo.end()
                    continue
                src = args[0].strip()
                if not IDENT.fullmatch(src):
                    skipped.append(f"{path}:{lineno} source is not a legal "
                                   f"receiver: {src[:50]!r}")
                    pos = mo.end()
                    continue
                rest = [a.strip() for a in args[2:]]
                new = (f"{src}.Middle({decrement(args[1])}"
                       f"{', ' + ', '.join(rest) if rest else ''})")
                before = real
                real = real[:mo.start()] + new + real[c + 1:]
            else:
                if not args or not args[0].strip():
                    not_framework.append(
                        f"{path}:{lineno} .Mid() with no start argument; "
                        f"left alone")
                    pos = mo.end()
                    continue
                rest = [a.strip() for a in args[1:]]
                new = (f"Middle({decrement(args[0])}"
                       f"{', ' + ', '.join(rest) if rest else ''})")
                before = real
                real = real[:mo.start()] + new + real[c + 1:]
            masked = mask_line(real)
            records.append({"path": str(path), "line": lineno,
                            "kind": kind, "before": before.strip()[:90],
                            "after": real.strip()[:90]})
            pos = mo.start() + len(new)
    return real, masked, records


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("project", type=pathlib.Path,
                    help="project directory (or its .xojo_project file)")
    ap.add_argument("--apply", action="store_true",
                    help="write the conversions (refused while the audit "
                         "reports risky sites, unless --force)")
    ap.add_argument("--force", action="store_true",
                    help="convert despite risky audit findings")
    ap.add_argument("--format", choices=("text", "json"), default="text")
    args = ap.parse_args(argv)

    project = args.project
    if project.is_file():
        project = project.parent
    if not project.is_dir():
        sys.exit(f"not a project directory: {args.project}")

    files, _, _, _ = collect_files(project)
    cache = {f: read_source(f) for f in files}
    findings = audit(cache)

    if args.apply and findings["risky"] and not args.force:
        for entry in findings["risky"]:
            print("  RISKY " + entry, file=sys.stderr)
        sys.exit(f"the audit found {len(findings['risky'])} site(s) whose "
                 f"start can be < 1 -- they rely on Mid's clamp and break "
                 f"under Middle. Fix them first, or pass --force after "
                 f"deciding each one.")

    converted, skipped, not_framework, unbalanced, changed = convert(
        cache, args.apply)

    if args.format == "json":
        print(json.dumps({
            "audit": findings, "converted": len(converted),
            "conversions": converted, "skipped": skipped,
            "not_framework": not_framework, "unbalanced": unbalanced,
            "files_changed": [str(p) for p in changed],
            "applied": args.apply}, indent=1))
        return

    print(f"Mid lower-bound audit: {findings['total']} site(s)")
    for label, n in sorted(findings["histogram"].items(),
                           key=lambda kv: -kv[1]):
        print(f"{n:5}  {label}")
    if findings["risky"]:
        print(f"\nRISKY ({len(findings['risky'])}) -- relies on the clamp; "
              f"a decrement breaks it:")
        for entry in findings["risky"]:
            print("  " + entry)
    if findings["review"]:
        print(f"\nHAND REVIEW ({len(findings['review'])}) -- the audit "
              f"cannot settle these; read each:")
        for entry in findings["review"]:
            print("  " + entry)
    verdict = (f"{len(findings['risky'])} risky of {findings['total']}, "
               f"{len(findings['review'])} for hand review")
    print(f"verdict: {verdict}")

    print(f"\nconverted: {len(converted)}")
    method_form = [r for r in converted if r["kind"] == "method"]
    if method_form and not args.apply:
        print(f"\nMETHOD FORM ({len(method_form)}) -- textually "
              f"type-blind; confirm no user class defines its own Mid:")
        for r in method_form[:40]:
            print(f"  {r['path']}:{r['line']}  {r['before']}")
            print(f"    -> {r['after']}")
        if len(method_form) > 40:
            print(f"  ... {len(method_form) - 40} more (--format json "
                  f"lists all)")
    for title, items in (("SKIPPED -- source cannot receive a method",
                          skipped),
                         ("NOT THE FRAMEWORK SIGNATURE", not_framework),
                         ("SPANS LINES -- convert by hand", unbalanced)):
        if items:
            print(f"\n{title} ({len(items)}):")
            for s in items:
                print("  " + s)
    if not args.apply:
        print("\n(dry run -- nothing written; pass --apply)")


if __name__ == "__main__":
    main()
