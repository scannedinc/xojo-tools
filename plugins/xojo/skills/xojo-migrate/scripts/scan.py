#!/usr/bin/env python3
"""Inventory deprecated API 1.0 symbols in a Xojo text-format project (stdlib only).

Usage:
  python3 scan.py /path/to/xojo/project [--format text|json]

Scans *.xojo_code / *.xojo_window / *.xojo_menu / *.xojo_toolbar / *.xojo_script
/ *.xojo_report (and legacy *.rbbas / *.rbfrm / *.rbmnu) files against the
bundled coverage matrix. Reports every deprecated symbol found, grouped by
bucket, with hit counts, files, and the conversion-rule ids that apply.

Counts are reported as "N in code (M raw)". The raw number counts every textual
match; the in-code number excludes layout metadata (`Left = 110`), #tag
ViewBehavior property tables, #tag Note prose, comments and string literals.
Only the in-code number is a worklist -- the gap runs 3-4x on a real project.

Member matches (.Name) are TYPE-BLIND: the same member name can be deprecated
on one class and valid API 2.0 on another. Treat member counts as leads to
review, not as a to-do list -- even the in-code number is an upper bound. Where
the matrix knows a name is live API 2.0 on some receiver, the report says so, and
where the receivers disagree about severity it says that too rather than
silently filing the symbol under the worst of them.
"""
import argparse
import json
import pathlib
import re
import sys
from collections import defaultdict

REFS = pathlib.Path(__file__).resolve().parent.parent / "references"
SOURCE_EXTS = {".xojo_code", ".xojo_window", ".xojo_menu", ".xojo_toolbar",
               ".xojo_script", ".xojo_report", ".rbbas", ".rbfrm", ".rbmnu"}
BINARY_EXTS = {".xojo_binary_project", ".rbp"}
XML_EXTS = {".xojo_xml_project", ".rbx"}
# The text-format manifest listing every item actually in the project. Deleted
# and renamed items are left on disk, so a stray .xojo_code file is not
# necessarily live code.
MANIFEST_EXTS = {".xojo_project", ".rbvcp"}
# Member names so generic that most matches are valid API 2.0 or user code.
NOISY_MEMBERS = {"append", "insert", "remove", "count", "value", "close",
                 "open", "text", "name", "type", "reset", "lookup", "column"}
# Global names common enough in prose, comments and unrelated identifiers that
# the hit count says little on its own. Same warning, different half of the
# namespace -- these were never flagged because the tag was gated on members.
NOISY_GLOBALS = {"line", "text", "mid", "left", "right", "split", "join",
                 "volume", "date", "format", "str", "val", "screen", "rectangle",
                 "oval", "separator", "control", "window", "application"}
# "Removed" sorts first when a symbol lands in several buckets: it is the only
# one that does not compile, so it outranks everything else. "No replacement"
# still compiles but has nowhere to go, which is a redesign, not a rename.
BUCKET_ORDER = ["Removed", "Source — global", "Source — member", "Source — type",
                "IDE handles", "No replacement", "Out of scope"]


# ---------------------------------------------------------------- segmentation
# A Xojo text-format file is mostly NOT code. Counting raw matches over the
# whole file over-reports by 3-4x on a real project: a window's `Left = 110`
# and `Text = "OK"` layout properties alone produced 502 `Left` and 494 `Text`
# hits where 45 and 30 were live code. Leading with that number sets the wrong
# expectation for the entire job, and anything that EDITS by raw line match
# will rewrite archived code sitting in a `#tag Note`.
#
# The format is regular enough to segment deterministically. Rather than
# enumerate the code tags (Method, Event, MenuHandler, Getter, Setter, Hook,
# ComputedProperty...) and risk missing one as Xojo adds them, invert it: mark
# the regions that are definitely not code and treat the rest as code.
NONCODE_TAGS = {
    "ViewBehavior",   # per-property IDE metadata: hundreds of Name=/Type= rows
    "ViewProperty",
    "Note",           # prose -- and often whole slabs of archived old code
    "Constant",       # Name=/Default= literal data
    "EnumValues",
}
TAG_OPEN = re.compile(r"^\s*#tag\s+(?!End)([A-Za-z]+)", re.I)
TAG_CLOSE = re.compile(r"^\s*#tag\s+End([A-Za-z]+)", re.I)
# Layout metadata is a `Begin <Class> <Name>` ... `End` block. A bare `End` on
# its own line closes one; Xojo code always spells the keyword out (`End If`,
# `End Sub`), so a lone `End` is unambiguous.
BEGIN_BLOCK = re.compile(r"^\s*Begin\s+[A-Za-z_][A-Za-z0-9_]*", re.I)
END_BLOCK = re.compile(r"^\s*End\s*$", re.I)


def mask_line(line):
    """Blank out string literals and comments, preserving length.

    Order matters: a `'` inside a literal is not a comment, and a `"` inside a
    comment does not open one. One left-to-right pass handles both. Xojo writes
    an embedded quote as `""`, which falls out of toggling on each `"`.
    """
    # Rem is Xojo's third comment form, and it can only open a line (Xojo has
    # no statement separator, and Rem is reserved, so no call starts this way).
    if re.match(r"\s*rem\b", line, flags=re.I):
        return " " * len(line)
    out = list(line)
    in_string = False
    i = 0
    while i < len(line):
        c = line[i]
        if in_string:
            out[i] = " "
            if c == '"':
                in_string = False
                out[i] = '"'      # keep the delimiters; only the content goes
        elif c == '"':
            in_string = True
        elif c == "'" or line[i:i + 2] == "//":
            for j in range(i, len(line)):
                out[j] = " "
            break
        i += 1
    return "".join(out)


def code_only(text):
    """Return `text` with every non-code region blanked to spaces.

    Length and line count are preserved so a caller can still map an offset
    back to a line. Returns the masked text; the caller keeps the original for
    the raw count.
    """
    lines = text.splitlines(keepends=True)
    out = []
    tag_stack = []
    layout_depth = 0
    for raw in lines:
        line = raw.rstrip("\n\r")
        nl = raw[len(line):]

        m_close = TAG_CLOSE.match(line)
        if m_close:
            if tag_stack and tag_stack[-1].lower() == m_close.group(1).lower():
                tag_stack.pop()
            out.append(" " * len(line) + nl)
            continue
        m_open = TAG_OPEN.match(line)
        if m_open:
            # Standalone records never get an End tag; pushing one would
            # wedge the stack (`#Tag Instance` inside `#tag Constant` is the
            # standard dynamic-constant serialization) and suppress every
            # line after it as non-code.
            if m_open.group(1).lower() not in ("instance", "compatibilityflags"):
                tag_stack.append(m_open.group(1))
            out.append(" " * len(line) + nl)
            continue

        suppressed = any(t in NONCODE_TAGS or t.rstrip("s") in NONCODE_TAGS
                         for t in tag_stack)
        if suppressed:
            # Checked before Begin/End: prose in a Note that happens to start
            # with `Begin <word>` (or an archived layout slab) must not bump
            # layout_depth, which never resets and would blank the rest of
            # the file.
            out.append(" " * len(line) + nl)
            continue

        if BEGIN_BLOCK.match(line):
            layout_depth += 1
            out.append(" " * len(line) + nl)
            continue
        if layout_depth and END_BLOCK.match(line):
            layout_depth -= 1
            out.append(" " * len(line) + nl)
            continue

        if layout_depth:
            out.append(" " * len(line) + nl)
        else:
            out.append(mask_line(line) + nl)
    return "".join(out)


COND_IF = re.compile(r"^\s*#if\b(.*)$", re.IGNORECASE)
COND_ELSEIF = re.compile(r"^\s*#elseif\b(.*)$", re.IGNORECASE)
COND_ENDIF = re.compile(r"^\s*#endif\b", re.IGNORECASE)


def conditional_only(code):
    """Return `code` with everything OUTSIDE `#If Target*` constructs blanked.

    The IDE analyzer compiles only the branch for the platform it runs on,
    so a hit inside ANY platform conditional is the analyzer's structural
    blind spot: it needs the text passes and a human, whatever the IDE
    reported. Length and line count are preserved, like code_only. The
    whole construct counts, `#Else` branches included; a nested `#If`
    inherits its enclosing construct's platform-ness; an `#ElseIf` naming
    a Target makes the rest of its construct platform-conditional even
    when the `#If` itself did not. Run this on code_only() output so
    archived slabs in `#tag Note` blocks stay excluded.
    """
    out = []
    stack = []          # one bool per open #If: does it involve Target*?
    for raw in code.splitlines(keepends=True):
        line = raw.rstrip("\n\r")
        nl = raw[len(line):]
        before = any(stack)
        m_elif = COND_ELSEIF.match(line)
        m_if = COND_IF.match(line)
        if m_elif:
            if stack and "target" in m_elif.group(1).lower():
                stack[-1] = True
        elif m_if:
            stack.append("target" in m_if.group(1).lower())
        elif COND_ENDIF.match(line):
            if stack:
                stack.pop()
        # Directive lines are kept too: `#if TargetCocoa` is itself a hit
        # for a deprecated compiler constant.
        keep = before or any(stack)
        out.append((line if keep else " " * len(line)) + nl)
    return "".join(out)


IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_.]*")
# Connectives and prose words that can never be a Xojo member name. Deliberately
# excludes words that ARE real symbols somewhere in the matrix -- Line, Text,
# Name, Value, Count, Index, Type, Row, Column, Item all name something.
STOPWORDS = {
    "as", "if", "then", "else", "end", "where", "is", "a", "an", "the", "and",
    "or", "not", "of", "to", "for", "in", "on", "with", "when", "form", "forms",
    "method", "property", "function", "sub", "var", "dim", "global", "verified",
    "confirmed", "deprecated", "removed", "replacement", "please", "use",
    "literal", "constant", "only", "also", "both", "any", "each", "per", "via",
    "from", "shared", "read", "write", "optional", "same", "new", "old", "etc",
    "see", "note", "based", "arg", "args", "argument", "arguments", "result",
    "leading", "trailing", "checks", "after", "before", "must", "no", "by",
    "that", "this", "it", "its", "was", "were", "has", "have", "will",
}


def symbol_tokens(rule):
    """Identifier tokens naming the DEPRECATED symbol a rule converts.

    Indexes the `old` field and the left half of `name`'s arrow -- indexing the
    replacement side too would link a symbol to rules that merely *produce* it.

    `old` is a signature, not a symbol, and often carries provenance prose
    ("... verified deprecated/recordset.md line 99"). Tokenizing it whole made
    every English word in it an index key, so scanning a file containing
    `Var Line As String` reported five unrelated RecordSet rules. Strip the
    parts that are never the symbol -- quoted doc excerpts, `.md` references,
    parameter lists, `[optional]` markers and `As <Type>` tails -- then drop
    pure connectives."""
    toks = set()
    for field in (re.split(r"→|->", rule.get("name", ""))[0], rule.get("old", "")):
        s = re.sub(r"['\"][^'\"]{20,}['\"]", " ", field)
        s = re.sub(r"[\w./-]*\.md\b(\s*lines?\s*[\d–-]+)?", " ", s, flags=re.I)
        for _ in range(3):
            s = re.sub(r"\([^()]*\)", " ", s)
        s = re.sub(r"\[[^\]]*\]", " ", s)
        s = re.sub(r"\bAs\s+[A-Za-z_][\w.]*", " ", s, flags=re.I)
        for t in IDENT.findall(s):
            for cand in (t.lower(), t.lower().split(".")[-1]):
                if cand and cand not in STOPWORDS:
                    toks.add(cand)
    return toks


def rule_index():
    data = json.loads((REFS / "rules.json").read_text(encoding="utf-8"))
    idx = defaultdict(list)
    for c in data["categories"]:
        for r in c["rules"]:
            for t in symbol_tokens(r):
                idx[t].append((r["id"], r["conf"]))
    return idx


# A rule's `find` is dot-anchored when it STARTS by escaping a `.` or looking
# behind for one, optionally after a `(?i)` flag. All three spellings are in
# use: `\.ListCount\b`, `(?<=\.)Len\b`, and `(?i)\.IsCancel\b`. Anchoring at
# the start is what keeps a namespace-prefix rule like `Xojo\.Core\.` from
# donating its interior `\.Core` as a bogus member name (which flagged user
# code like `Prefs.Core` as deprecated). sweep.py uses this same pattern; keep
# the two in sync so no rule-only member escapes the final sweep.
RULE_MEMBER = re.compile(r"^(?:\(\?i\))?(?:\\\.|\(\?<=\\\.\))([A-Za-z_]\w*)")


def rule_member_names(rules_data):
    """Member names that a dot-anchored rule searches for.

    The matrix records a symbol once, but a global function that also has a
    method form needs two rules -- `Mid(s, n)` is c0r8-c0r10 and `s.Mid(n)` is
    c0r11. Since the row is `Mid` (no dot), build_patterns only ever built the
    global key `(?<![\\w.])Mid\\b`, whose lookbehind excludes the dot form by
    construction. A live `NodeContents(node).Mid(1)` therefore scanned clean:
    invisible to the scanner while a shipped rule converts it.

    Fifteen names are in this state (`.Len`, `.Mid`, `.InStr`, `.UBound`,
    `.LTrim` ...). It is the same shape as the `Invalidate` miss that sweep.py
    was fixed for in round 2 -- a rule with no row to hang on -- so the fix is
    the same: read rules.json too, and derive the key rather than hand-adding
    member rows that would then need maintaining against the derivation.

    Returns {membername_lower: (Member, rule)}, first rule to claim the name.
    """
    found = {}
    for c in rules_data["categories"]:
        for r in c["rules"]:
            m = RULE_MEMBER.match(r.get("find") or "")
            if m:
                member = m.group(1)
                found.setdefault(member.lower(), (member, r))
    return found


def build_patterns(coverage, rules_data=None):
    """One compiled regex per unique search key; each key maps to the coverage
    rows it can indicate. Returns {key: (regex, is_member, [rows])}."""
    pats = {}
    for row in coverage:
        name = row["old"].split("(")[0]
        if "." in name:
            member = name.split(".")[-1]
            key = "." + member.lower()
            rx = re.compile(r"\." + re.escape(member) + r"\b", re.I)
            is_member = True
        else:
            key = name.lower()
            rx = re.compile(r"(?<![\w.])" + re.escape(name) + r"\b", re.I)
            is_member = False
        entry = pats.setdefault(key, (rx, is_member, []))
        entry[2].append(row)

    if rules_data is None:
        return pats

    # Second source: member names only a rule knows about (see above). The row
    # is synthesized, not authored, so it stays a pure function of the two
    # shipped files and cannot drift from either.
    #
    # The owning class comes from the global row's replacement -- `Mid ->
    # String.Middle` makes the method form `String.Mid -> String.Middle`, which
    # is the true statement and reads correctly in the report. Where no global
    # row exists (`.CellCheckBoxValue`, `.SelectedRow`) fall back to the rule's
    # own `new` field and leave the owner off rather than invent one.
    for lower, (member, rule) in rule_member_names(rules_data).items():
        key = "." + lower
        if key in pats:
            continue
        globalrow = pats.get(lower)
        new = owner = ""
        if globalrow:
            new = (globalrow[2][0].get("new") or "").strip()
            if "." in new:
                owner = new.split(".")[0]
        if not new:
            new = (rule.get("new") or "").split(" As ")[0].strip() or "—"
        pats[key] = (
            re.compile(r"\." + re.escape(member) + r"\b", re.I),
            True,
            [{
                "old": f"{owner}.{member}" if owner else f"?.{member}",
                "new": new,
                "cat": "Source — member",
                "status": "Deprecated",
                "origin": "rule",
                "note": f"Method form of a global-form deprecation, searched "
                        f"because rule {rule['id']} converts it. The matrix "
                        f"records the global form only.",
            }],
        )
    return pats


# ------------------------------------------------------------- token prefilter
# Scanning used to run every one of the ~950 compiled patterns over every
# file, and nearly all of that work is provably unnecessary. Both pattern
# shapes embed a literal ASCII identifier (`\.Member\b`, `(?<![\w.])Name\b`),
# so a match can only exist where that identifier appears as a whole token in
# the text: its characters are contiguous, the character after fails \w (the
# trailing \b), and the character before is either the literal `.` or fails
# the lookbehind. One tokenizing pass over the file therefore yields a
# necessary condition for every pattern at once, and only the patterns whose
# token is present need to run at all.
#
# CODE_TOKEN is deliberately ASCII-only while the patterns are Unicode-aware.
# That mismatch has two directions, and both must be covered for the
# necessary-condition argument to hold:
#
#   - Adjacency: a non-ASCII character next to a name splits the token early
#     (`éMid(` still yields a `Mid` token), so the tokenizer emits the bare
#     name MORE often than the pattern can match -- a wasted candidate, never
#     a miss, because a non-ASCII LETTER neighbor is `\w` and already defeats
#     `\b` or the lookbehind at that junction.
#   - The name itself: re.IGNORECASE folds exactly four non-ASCII codepoints
#     onto ASCII letters (U+0130 İ and U+0131 ı match i, U+017F ſ matches s,
#     U+212A Kelvin K matches k), so `\.Mid\b` matches `.Mıd` -- a span the
#     ASCII tokenizer would break apart. candidate_keys() folds those four to
#     their ASCII partners before tokenizing, mirroring the folding the
#     engine itself applies. The fold is harmless on any other input: each
#     impostor is a letter, so a token merged across one sits at a junction
#     where `\b` or the lookbehind already forbids a match.
#
# test_scan.py pins each direction and holds the filtered scan equal to the
# exhaustive one over every shipped key and the fixture projects.
CODE_TOKEN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
CASE_FOLD_IMPOSTORS = {0x130: "i", 0x131: "i", 0x17F: "s", 0x212A: "k"}


def build_prefilter(pats):
    """Index pattern keys by the identifier token that must be present.

    Returns (by_token, residual): {token: [keys]} plus the keys carrying no
    plain-identifier token, which always run. Every shipped key is an
    identifier today, so the residual is empty; it exists so a future exotic
    key degrades to the old scan-everything behavior instead of silently
    never matching.
    """
    by_token = {}
    residual = []
    for key in pats:
        name = key[1:] if key.startswith(".") else key
        if CODE_TOKEN.fullmatch(name):
            by_token.setdefault(name.lower(), []).append(key)
        else:
            residual.append(key)
    return by_token, residual


def candidate_keys(text, prefilter):
    """The pattern keys that could match `text`, from one tokenizing pass."""
    by_token, residual = prefilter
    cand = set(residual)
    folded = text.translate(CASE_FOLD_IMPOSTORS)
    for token in {t.lower() for t in CODE_TOKEN.findall(folded)}:
        cand.update(by_token.get(token, ()))
    return cand


def scan_text(text, pats, prefilter=None):
    """Per-key (raw, in-code, in-platform-conditional) counts for one file.

    With a prefilter, only candidate patterns run; the result is identical
    to running every pattern -- dict order included, because iteration stays
    in `pats` order and a skipped pattern is one whose token is absent and
    so cannot match. Report assembly and JSON output follow this dict order,
    which is why preserving it is part of the contract.
    """
    code = code_only(text)
    cond = None
    cand = candidate_keys(text, prefilter) if prefilter is not None else None
    out = {}
    for key, (rx, _m, _rows) in pats.items():
        if cand is not None and key not in cand:
            continue
        n = len(rx.findall(text))
        if n:
            n_code = len(rx.findall(code))
            n_cond = 0
            if n_code:
                if cond is None:
                    cond = conditional_only(code)
                n_cond = len(rx.findall(cond))
            out[key] = (n, n_code, n_cond)
    return out


def collect_files(root):
    src, binary, xml, manifests = [], [], [], []
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        ext = p.suffix.lower()
        if ext in SOURCE_EXTS:
            src.append(p)
        elif ext in BINARY_EXTS:
            binary.append(p)
        elif ext in XML_EXTS:
            xml.append(p)
        elif ext in MANIFEST_EXTS:
            manifests.append(p)
    return src, binary, xml, manifests


def orphaned(src, manifests, root):
    """Source files on disk that no .xojo_project manifest references.

    Xojo leaves deleted and renamed items on disk in text format, so an
    unreferenced .xojo_code file is dead weight -- counting its hits inflates
    the inventory and makes the phase-8 re-scan diff fail to reach zero for
    code that is not in the project at all. Returns [] when no manifest is
    present, since then nothing can be concluded."""
    if not manifests:
        return []
    referenced = set()
    for m in manifests:
        try:
            text = m.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        names = set()
        for line in text.splitlines():
            # Manifest rows are semicolon-separated fields, and a field may
            # be bare ("Name.xojo_code") or Key=Value ("BuildSteps=Build
            # Automation.xojo_code"). A filename can contain spaces, which
            # no token regex can span, so test each whole field's value.
            for field in line.split(";"):
                value = field.split("=", 1)[-1].strip().strip('"')
                if re.fullmatch(r".+\.(?:xojo_\w+|rb\w+)", value):
                    names.add(value)
        # The token pass stays as a supplement: it catches several
        # references packed into one field, which the whole-field test
        # would read as a single garbled name.
        names.update(re.findall(r"[^\s;\"]+\.(?:xojo_\w+|rb\w+)", text))
        for name in names:
            # Manifests saved on Windows use backslash separators, which
            # PurePath does not split on POSIX; normalize first or every such
            # file reads as orphaned (and sweep.py then excludes it).
            referenced.add(pathlib.PurePath(name.replace("\\", "/")).name.lower())
    return [p for p in src if p.name.lower() not in referenced]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("project", type=pathlib.Path)
    ap.add_argument("--format", choices=("text", "json"), default="text")
    args = ap.parse_args()

    root = args.project
    if not root.exists():
        sys.exit(f"path does not exist: {root}")
    if root.is_file():
        # Scanning the parent silently widens a single-file request into a
        # whole-directory one. Say so, rather than reporting hits from files
        # the caller never named.
        print(f"note: {root.name} is a file; scanning its directory {root.parent} instead.",
              file=sys.stderr)
        root = root.parent

    src, binary, xml, manifests = collect_files(root)
    if not src:
        if binary or xml:
            fmt = (binary + xml)[0].name
            sys.exit(f"No text-format source files found, but found '{fmt}'.\n"
                     "This project is saved in binary/XML format, which cannot be scanned.\n"
                     "In the Xojo IDE: File > Save As... and choose 'Xojo Project' (text) "
                     "format, then re-run this scan on the saved copy.")
        sys.exit(f"No Xojo source files (*.xojo_code etc.) found under {root}")
    if binary:
        print(f"note: also found {len(binary)} binary project file(s); scanning "
              f"the {len(src)} text source files only.\n", file=sys.stderr)
    stale = orphaned(src, manifests, root)
    if stale:
        names = ", ".join(p.name for p in stale[:6])
        more = f" (+{len(stale) - 6} more)" if len(stale) > 6 else ""
        print(f"note: {len(stale)} source file(s) are not referenced by the project "
              f"manifest and may be deleted/renamed leftovers: {names}{more}.\n"
              f"      Their hits are included below; exclude them if they are dead.\n",
              file=sys.stderr)

    coverage = json.loads((REFS / "coverage.json").read_text(encoding="utf-8"))
    rules_data = json.loads((REFS / "rules.json").read_text(encoding="utf-8"))
    pats = build_patterns(coverage, rules_data)
    rules = rule_index()

    prefilter = build_prefilter(pats)
    hits = defaultdict(lambda: {"count": 0, "code": 0, "cond": 0, "files": set()})
    for f in src:
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            print(f"warning: cannot read {f}: {e}", file=sys.stderr)
            continue
        for key, (n, n_code, n_cond) in scan_text(text, pats, prefilter).items():
            hits[key]["count"] += n
            hits[key]["code"] += n_code
            hits[key]["cond"] += n_cond
            # Only files with a live-code hit are worth opening. A file that
            # matches purely in layout metadata is not part of the worklist.
            if n_code:
                hits[key]["files"].add(str(f.relative_to(root)))

    # ---- assemble per-symbol report rows
    report = []
    for key, h in hits.items():
        rx, is_member, rows = pats[key]
        bare = key.lstrip(".")
        rids = []
        for row in rows:
            dotted = row["old"].split("(")[0].lower()
            for rid in (rules.get(dotted) or rules.get(dotted.split(".")[-1]) or []):
                if rid not in rids:
                    rids.append(rid)
        buckets = {r["cat"] for r in rows}
        # The default keeps a new/respelled category in coverage.json a "?"
        # instead of a StopIteration crash, matching the candidates sort below.
        bucket = (next((b for b in BUCKET_ORDER if b in buckets), "?")
                  if buckets else "?")
        # One member name can land in several buckets because it is deprecated
        # on several classes. Filing the symbol under the most severe of them
        # and saying nothing else is actively misleading: `.Bold` reports as
        # Removed on the strength of MenuItem.Bold while Graphics.Bold and
        # TextShape.Bold are live API 2.0, so 71 hits present as build errors when
        # zero are. Same for `.Pixel` (System.Pixel is Removed, RGBSurface.Pixel
        # is the replacement) and `.SelStart` (MoviePlayer vs TextEdit). Keep
        # the severity ordering for filing, but say when the receivers disagree.
        live_on = sorted({recv for r in rows for recv in (r.get("live_on") or [])})
        report.append({
            "match": key, "bucket": bucket,
            "mixed_buckets": sorted(buckets) if len(buckets) > 1 else [],
            "live_on": live_on,
            "count": h["count"], "code": h["code"],
            "platform_conditional": h["cond"], "files": sorted(h["files"]),
            # Only the first few candidates are printed, so the order decides
            # what a reader sees. Sorting by BUCKET_ORDER puts the receivers
            # that break a build first and pushes the iOS/Web surface last --
            # `.Value` otherwise led with three WebComboBox rows on a desktop
            # project, which reads as "not my code" and hides the real ones.
            "candidates": sorted(
                ({"old": r["old"], "new": r["new"], "cat": r["cat"]} for r in rows),
                key=lambda c: (BUCKET_ORDER.index(c["cat"]) if c["cat"] in BUCKET_ORDER
                               else len(BUCKET_ORDER), c["old"])),
            "rules": [{"id": i, "conf": c} for i, c in rids],
            "type_blind": is_member,
            "noisy": bare in (NOISY_MEMBERS if is_member else NOISY_GLOBALS),
        })

    if args.format == "json":
        print(json.dumps({"scanned_files": len(src), "symbols": report}, indent=1))
        return

    total_raw = sum(r["count"] for r in report)
    total_code = sum(r["code"] for r in report)
    live = [r for r in report if r["code"]]
    print(f"Scanned {len(src)} source files under {root}")
    print(f"Deprecated-symbol matches: {len(live)} distinct symbols with live-code hits "
          f"({len(report)} matched anywhere)")
    print(f"Hits: {total_code} in code, {total_raw} raw\n")
    print("Report the in-code number. The raw count includes layout metadata")
    print("(`Left = 110`, `Text = \"OK\"`), #tag Note prose, comments and string")
    print("literals -- none of which is a conversion. Even the in-code number is an")
    print("upper bound: member matches are type-blind, so a symbol whose receivers")
    print("all turn out to be user classes or live API 2.0 controls goes to zero.\n")
    for bucket in BUCKET_ORDER:
        group = sorted((r for r in report if r["bucket"] == bucket and r["code"]),
                       key=lambda r: -r["code"])
        if not group:
            continue
        print(f"== {bucket} ({len(group)} symbols) ==")
        for r in group:
            tags = []
            if r["noisy"] and r["type_blind"]:
                tags.append("type-blind, high false-positive rate")
            elif r["noisy"]:
                tags.append("common word, high false-positive rate")
            elif r["type_blind"]:
                tags.append("type-blind")
            # These warnings are properties of the bucket, not of whether a rule
            # happens to attach. Gating them on `not r["rules"]` meant one
            # spurious rule id silenced the very thing phase 2 leads with.
            if bucket == "Removed":
                tags.append("REMOVED: does not compile, rewrite required")
            elif bucket == "No replacement":
                tags.append("no replacement documented: needs redesign")
            elif not r["rules"]:
                tags.append("no rule: use coverage replacement + traps doc")
            if r["platform_conditional"]:
                tags.append(f"{r['platform_conditional']} of {r['code']} inside "
                            f"#if Target* -- the IDE analyzer never compiled them")
            if r["mixed_buckets"]:
                tags.append("MIXED: receivers disagree -- filed under the most severe of "
                            + ", ".join(r["mixed_buckets"]))
            tag = f"   [{'; '.join(tags)}]" if tags else ""
            rids = ", ".join(f"{x['id']}({x['conf']})" for x in r["rules"]) or "-"
            raw = f" ({r['count']} raw)" if r["count"] != r["code"] else ""
            print(f"  {r['match']:<28} {r['code']:>4} in code{raw:<12} "
                  f"in {len(r['files'])} file(s)   rules: {rids}{tag}")
            if r["live_on"]:
                print(f"      LIVE API 2.0 on: {', '.join(r['live_on'])} "
                      f"-- on those receivers this name is correct; do not convert")
            for cand in r["candidates"][:4]:
                print(f"      {cand['old']} -> {cand['new']}")
            if len(r["candidates"]) > 4:
                print(f"      ... {len(r['candidates']) - 4} more possible receivers (lookup.py symbol {r['match'].lstrip('.')})")
        print()
    metadata_only = [r for r in report if not r["code"]]
    if metadata_only:
        print(f"== Matched only outside code ({len(metadata_only)} symbols) ==")
        print("   Layout metadata, notes, comments or string literals. DO NOT CONVERT")
        print("   THESE -- the compiler never reads them, so they are not deprecations.")
        print("   A `#tag Note` in particular often holds slabs of valid archived code;")
        print("   converting it changes a comment and reports as a fix that fixes")
        print("   nothing. Listed so a later re-scan showing them is not read as a")
        print("   missed step, and so a text search turning one up is not read as a")
        print("   symbol this scan missed.")
        names = ", ".join(r["match"] for r in sorted(metadata_only, key=lambda r: -r["count"]))
        print(f"   {names}\n")
    if not live:
        print("No deprecated API 1.0 symbols detected in code; project may already be API 2.0.")


if __name__ == "__main__":
    main()
