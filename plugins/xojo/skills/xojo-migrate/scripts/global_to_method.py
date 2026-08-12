#!/usr/bin/env python3
"""Convert global function calls to method form, and audit what remains.

    Fn(source, a, b)  ->  source.Fn(a, b)

The bundled regex rules skip any argument containing a nested call, by
design ([^()] cannot count parens); this walks the call with a balanced
scan, so `ReplaceAll(NthField(s, ",", 1), a, b)` converts. The source
argument must be a LEGAL RECEIVER -- an identifier or a member/call
chain off one (hard rule 3, conversion-traps.md section 4). A string
literal or parenthesised expression is refused and reported: those
sites need a local introduced, or a deferral with its #Pragma marker --
the two legal outcomes.

THE DRY RUN IS THE DEFERRAL ORACLE. What it would convert is unfinished
work or a PARKED queue entry; what it refuses as an illegal receiver is
a genuine deferral that must carry its marker. Run `--oracle` at every
category boundary and reconcile both lists against the queues -- an
orphan in either direction is a forgotten site. (--oracle derives the
function list from rules.json's global-form rules; no spec needed.)

Usage:
  python3 global_to_method.py <project> <spec.json> [--apply] [--format text|json]
  python3 global_to_method.py <project> --oracle [--format text|json]
  spec: [{"fn": "ReplaceAll", "method": "", "drop_parens": false}, ...]
        "method" empty means the same name; drop_parens renders a
        zero-extra-argument call as a property (Trim(s) -> s.Trim).

Dry run by default; --apply writes (never with --oracle). Calls that
span lines (unbalanced parens on the line) are reported for hand
conversion, not guessed. (stdlib only)
"""
import argparse
import json
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from editing import (find_call, legal_receiver, masked_pairs,  # noqa: E402
                     read_source, split_args, write_source)
from scan import collect_files, mask_line  # noqa: E402

REFS = HERE.parent / "references"
ORACLE_NEW = re.compile(r"^\s*[A-Za-z_]\w*\.([A-Za-z_]\w*)(\s*\()?")
ORACLE_OLD = re.compile(r"^([A-Za-z_]\w*)\s*\(")


def oracle_spec():
    """Every global-with-a-method-replacement rules.json knows.

    A rule qualifies when its forms say global/both, it is mechanically
    applicable, its old is a call form and its new is a method form.
    The oracle never edits, so an imperfect derived method name costs a
    cosmetic preview line, never a wrong edit.
    """
    data = json.loads((REFS / "rules.json").read_text(encoding="utf-8"))
    spec, seen = [], set()
    for cat in data["categories"]:
        for r in cat["rules"]:
            if not (r.get("forms") or "").startswith(("global", "both")):
                continue
            if not r["applies"]:
                continue
            old_m = ORACLE_OLD.match(r.get("old") or "")
            new_m = ORACLE_NEW.match(r.get("new") or "")
            if not old_m or not new_m:
                continue
            fn = old_m.group(1)
            if fn.lower() in seen:
                continue
            seen.add(fn.lower())
            spec.append({"fn": fn, "method": new_m.group(1),
                         "drop_parens": new_m.group(2) is None})
    return spec


def convert_line(real, masked, pat, fn, method, drop, lineno, path, state):
    """One spec entry over one code line. Returns the new real line.

    Scans the mask (parens in strings are invisible there), splits the
    REAL argument text, and after a conversion re-masks and rescans
    from the same offset -- the converted call renders as .Method(...),
    which the lookbehind no longer matches, so nested same-name calls
    convert in one pass and the loop always terminates. Re-masking with
    mask_line is sound here because callers only pass in-code lines;
    block-blanked lines never reach this function.
    """
    pos = 0
    while True:
        mo = pat.search(masked, pos)
        if not mo:
            return real
        span = find_call(masked, mo.start())
        if span is None:
            state["multiline"].append(
                f"{path}:{lineno} {mo.group(0).strip()} -- the call spans "
                f"lines or its parens do not balance; convert by hand")
            pos = mo.end()
            continue
        o, c = span
        args = split_args(real[o + 1:c])
        src = args[0].strip()
        if not legal_receiver(src):
            state["skipped"].append(
                f"{path}:{lineno} {mo.group(0).strip()[:-1].strip()}: "
                f"source is not a legal receiver: {src[:50]!r}")
            pos = mo.end()
            continue
        rest = [a.strip() for a in args[1:]]
        if rest:
            new = f"{src}.{method}({', '.join(rest)})"
        else:
            new = f"{src}.{method}" if drop else f"{src}.{method}()"
        real = real[:mo.start()] + new + real[c + 1:]
        masked = mask_line(real)
        state["converted"] += 1
        # Every conversion is recorded with its position: the boundary
        # reconciles would-convert sites against the PARKED queue site
        # by site, which bare counts cannot do.
        state["sites"].append(f"{path}:{lineno} {fn} -> {new[:60]}")
        # rescan from the same offset: the receiver text may itself
        # hold an unconverted global-form call
    return real


def run(project, spec, apply_):
    files, _, _, _ = collect_files(project)
    cache, changed = {}, set()
    per_fn = {}
    state = {"converted": 0, "sites": [], "skipped": [], "multiline": []}
    for item in spec:
        fn = item["fn"]
        method = item.get("method") or fn
        drop = bool(item.get("drop_parens"))
        pat = re.compile(r"(?<![\w.])" + re.escape(fn) + r"\s*\(", re.I)
        before = state["converted"]
        for path in files:
            text = cache.get(path)
            if text is None:
                text = cache[path] = read_source(path)
            pairs = masked_pairs(text)
            lines = [real for real, _ in pairs]
            file_changed = False
            for i, (real, masked) in enumerate(pairs):
                if real.strip() and not masked.strip():
                    # Block-blanked: layout metadata or a #tag Note slab
                    # (often archived old code). Deliberately silent --
                    # a hit there is not migration work.
                    continue
                if not pat.search(masked):
                    continue
                new_line = convert_line(real, masked, pat, fn, method,
                                        drop, i + 1, path, state)
                if new_line != real:
                    lines[i] = new_line
                    file_changed = True
            if file_changed:
                cache[path] = "\n".join(lines)
                changed.add(path)
        per_fn[fn] = {"method": method,
                      "converted": state["converted"] - before}
    if apply_:
        for path in sorted(changed):
            write_source(path, cache[path])
    return per_fn, state, sorted(changed)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("project", type=pathlib.Path,
                    help="project directory (or its .xojo_project file)")
    ap.add_argument("spec", nargs="?",
                    help="spec JSON; omit with --oracle")
    ap.add_argument("--oracle", action="store_true",
                    help="dry-run every rules.json global with a method "
                         "replacement: the boundary reconciliation")
    ap.add_argument("--apply", action="store_true",
                    help="write the conversions (default is a dry run)")
    ap.add_argument("--format", choices=("text", "json"), default="text")
    args = ap.parse_args(argv)

    project = args.project
    if project.is_file():
        project = project.parent
    if not project.is_dir():
        sys.exit(f"not a project directory: {args.project}")
    if args.oracle and args.apply:
        sys.exit("--oracle never writes; drop --apply.")
    if args.oracle:
        spec = oracle_spec()
    elif args.spec:
        try:
            with open(args.spec, encoding="utf-8") as f:
                spec = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            sys.exit(f"cannot read the spec: {e}")
        if not isinstance(spec, list) or not all(
                isinstance(s, dict) and s.get("fn") for s in spec):
            sys.exit('the spec must be a JSON list of {"fn": ...} objects.')
    else:
        sys.exit("name a spec JSON, or pass --oracle.")

    per_fn, state, changed = run(project, spec, args.apply)

    if args.format == "json":
        print(json.dumps({
            "converted": state["converted"], "sites": state["sites"],
            "per_function": per_fn,
            "skipped": state["skipped"], "multiline": state["multiline"],
            "files_changed": [str(p) for p in changed],
            "applied": args.apply, "oracle": args.oracle}, indent=1))
        return
    for fn, info in per_fn.items():
        if info["converted"] or not args.oracle:
            print(f"{info['converted']:5}  {fn} -> .{info['method']}")
    print(f"\ntotal: {state['converted']}")
    if state["skipped"]:
        print(f"\nSKIPPED ({len(state['skipped'])}) -- each needs a local "
              f"or a deferral with its marker (conversion-traps.md "
              f"section 4):")
        for s in state["skipped"]:
            print("  " + s)
    if state["multiline"]:
        print(f"\nSPANS LINES ({len(state['multiline'])}) -- convert by "
              f"hand:")
        for s in state["multiline"]:
            print("  " + s)
    if args.oracle:
        if state["sites"]:
            print(f"\nWOULD CONVERT ({len(state['sites'])}) -- each is "
                  f"unfinished work or a PARKED queue entry:")
            for s in state["sites"][:40]:
                print("  " + s)
            if len(state["sites"]) > 40:
                print(f"  ... {len(state['sites']) - 40} more "
                      f"(--format json lists all)")
        print(f"\noracle: {state['converted']} would-convert site(s) -- "
              f"each is unfinished work or a PARKED queue entry; "
              f"{len(state['skipped'])} illegal-receiver site(s) -- each "
              f"is a genuine deferral that must carry its #Pragma marker.")
    elif not args.apply:
        print("\n(dry run -- nothing written; pass --apply)")


if __name__ == "__main__":
    main()
