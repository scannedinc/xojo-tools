#!/usr/bin/env python3
"""Diff two `xojoctl analyze --json` documents at a category boundary.

Answers the boundary's two questions -- did the last edit help, and did
it break anything -- from the documents alone: error and warning deltas,
NEW errors absent from the baseline (regressions), deprecation symbols
cleared to zero and newly appearing, and the remaining per-symbol counts
with their baseline values. The verdict line comes first; read top-down.

Exit is nonzero when there are NEW errors (do not commit) and when
either document fails the shared acceptance policy (worklist.vet): an
analysis that never ran proves nothing. A clean document -- ok:true and
zero diagnostics -- is a success to report, not a failure.

Two honesty rules learned in the field:
  - Identical error AND warning counts across an edit are a STALENESS
    signal, not a result: the IDE may have analyzed a stale in-memory
    copy. The verdict says SUSPECT; re-run the bracketed analyze before
    believing anything else.
  - Regressions key on (message, location), not line: any edit above a
    site shifts every later line number, and a line-keyed diff reports
    the whole file as new errors. Same-key line moves are counted
    separately, quietly.

Usage:  python3 checkpoint.py <new.json|-> <baseline.json>
                              [--format text|json]

(stdlib only)
"""
import argparse
import collections
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from worklist import vet  # noqa: E402


def load(source, stream, label):
    try:
        if source == "-":
            doc = json.load(stream)
        else:
            with open(source, encoding="utf-8") as f:
                doc = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        sys.exit(f"cannot read the {label} document: {e}")
    if not isinstance(doc, dict) or "diagnostics" not in doc:
        sys.exit(f"the {label} document is not 'xojoctl analyze --json' "
                 f"output: no 'diagnostics' key.")
    fatal, warnings = vet(doc)
    if fatal:
        sys.exit(f"{label} document: {fatal}")
    for w in warnings:
        print(f"{label}: {w}", file=sys.stderr)
    return doc


def symbol(d):
    m = d.get("message", "")
    return m.split(" is deprecated")[0] if " is deprecated" in m else None


def diff(new, base):
    nd = new.get("diagnostics") or []
    bd = base.get("diagnostics") or []
    ne = [x for x in nd if x.get("severity") == "error"]
    be = [x for x in bd if x.get("severity") == "error"]
    nw = [x for x in nd if x.get("severity") == "warning"]
    bw = [x for x in bd if x.get("severity") == "warning"]

    base_keys = {(x.get("message", ""), x.get("location", "")) for x in be}
    base_full = {(x.get("message", ""), x.get("location", ""),
                  x.get("line")) for x in be}
    regressions, moved = [], 0
    for x in ne:
        k = (x.get("message", ""), x.get("location", ""))
        if k not in base_keys:
            regressions.append(x)
        elif (*k, x.get("line")) not in base_full:
            moved += 1

    bs = collections.Counter(s for s in (symbol(x) for x in bw) if s)
    ns = collections.Counter(s for s in (symbol(x) for x in nw) if s)
    return {
        "errors": {"baseline": len(be), "new": len(ne)},
        "warnings": {"baseline": len(bw), "new": len(nw)},
        "regressions": regressions,
        "line_moved": moved,
        "cleared": sorted(s for s in bs if ns.get(s, 0) == 0),
        "introduced": sorted(s for s in ns if bs.get(s, 0) == 0),
        "remaining": {s: {"count": n, "was": bs.get(s, 0)}
                      for s, n in ns.most_common()},
        "stale_counts": (len(ne) == len(be) and len(nw) == len(bw)
                         and len(ne) + len(nw) > 0),
        "clean": not nd,
    }


def verdict_line(d):
    e, w = d["errors"], d["warnings"]
    if d["regressions"]:
        return (f"verdict: STOP -- {len(d['regressions'])} new error(s) "
                f"not in the baseline; do not commit")
    if d["stale_counts"]:
        return ("verdict: SUSPECT -- identical error and warning counts. "
                "If you edited since the baseline, the IDE may have "
                "analyzed a stale in-memory copy; re-run the bracketed "
                "analyze before believing this")
    if d["clean"]:
        return "verdict: clean -- 0 errors, 0 warnings"
    return (f"verdict: no new errors -- errors {e['baseline']} -> "
            f"{e['new']}, warnings {w['baseline']} -> {w['new']}")


def report(d):
    print(verdict_line(d))
    e, w = d["errors"], d["warnings"]
    print(f"errors    {e['baseline']:5} -> {e['new']:5}   "
          f"({e['new'] - e['baseline']:+d})")
    print(f"warnings  {w['baseline']:5} -> {w['new']:5}   "
          f"({w['new'] - w['baseline']:+d})")
    print(f"\nNEW errors not in baseline: {len(d['regressions'])}")
    for x in d["regressions"][:40]:
        print(f"  {x.get('location')}, line {x.get('line')}: "
              f"{x.get('message')}")
    if len(d["regressions"]) > 40:
        print(f"  ... {len(d['regressions']) - 40} more")
    if d["line_moved"]:
        print(f"  ({d['line_moved']} baseline error(s) reappear at "
              f"shifted line numbers; not regressions)")
    print(f"\nsymbols cleared to zero ({len(d['cleared'])}): "
          f"{', '.join(d['cleared']) or '-'}")
    print(f"symbols newly appearing ({len(d['introduced'])}): "
          f"{', '.join(d['introduced']) or '-'}")
    if d["remaining"]:
        print("\nremaining deprecation symbols by count:")
        for s, info in d["remaining"].items():
            print(f"  {info['count']:5} (was {info['was']:5})  {s}")


def main(argv=None, stdin=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("new", help="the fresh analyze JSON; '-' reads stdin")
    ap.add_argument("baseline",
                    help="the previous checkpoint's analyze JSON")
    ap.add_argument("--format", choices=("text", "json"), default="text")
    args = ap.parse_args(argv)

    stream = stdin or sys.stdin
    new = load(args.new, stream, "new")
    base = load(args.baseline, stream, "baseline")
    d = diff(new, base)

    if args.format == "json":
        print(json.dumps(dict(d, verdict=verdict_line(d)), indent=1))
    else:
        report(d)
    if d["regressions"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
