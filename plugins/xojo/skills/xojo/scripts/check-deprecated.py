#!/usr/bin/env python3
"""Report deprecated Xojo APIs used in a source file.

Reads the indexes this skill builds and flags API 1 symbols the code still
uses, with what replaced each one. Written to be usable as a Claude Code
PostToolUse hook; see README.md.

Two things it deliberately does NOT do:

- **Flag prose.** Xojo source files carry constants, notes and comments in the
  same file as code. `MsgBox` inside a note is not a call. Constant and note
  blocks are dropped whole, then string literals and comments are stripped from
  what remains.
- **Flag bare words.** `Text` and `Date` are deprecated types and also ordinary
  property names. A symbol is only reported where the syntax makes it an API
  reference: after a dot, or in a type or constructor position.

    usage: check-deprecated.py FILE [FILE...]
           check-deprecated.py --hook        (reads hook JSON on stdin)
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
REFERENCES = SKILL_DIR / "references" / "documentation"
XOJO_SUFFIXES = {
    ".xojo_code", ".xojo_window", ".xojo_menu", ".xojo_toolbar",
    ".xojo_report", ".xojo_script", ".rbbas", ".rbfrm",
}

# Blocks that hold prose or literals rather than executable code.
PROSE_BLOCK = re.compile(
    r"^\s*#tag\s+(Note|Constant|Enum|EndNote|EndConstant|EndEnum)\b", re.I
)
PROSE_OPEN = re.compile(r"^\s*#tag\s+(Note|Constant|Enum)\b", re.I)
PROSE_CLOSE = re.compile(r"^\s*#tag\s+End(Note|Constant|Enum)\b", re.I)

STRING_LITERAL = re.compile(r'"(?:[^"]|"")*"')
COMMENT = re.compile(r"(//|'|\bRem\b).*$", re.I)

# 20260201 -> 2026r2.1. The IDE writes this into the .xojo_project file.
IDE_VERSION = re.compile(r"^OrigIDEVersion=(\d{4})(\d{2})(\d{2})", re.M)
RELEASE = re.compile(r"^(\d{4})r(\d+)")


def release_key(text: str) -> tuple[int, int]:
    m = RELEASE.match(text.strip())
    return (int(m.group(1)), int(m.group(2))) if m else (0, 0)


def project_release(start: Path) -> tuple[str, tuple[int, int]] | None:
    """The Xojo release that last saved the enclosing project, if findable."""
    for folder in [start if start.is_dir() else start.parent, *start.parents]:
        for project in folder.glob("*.xojo_project"):
            match = IDE_VERSION.search(project.read_text(errors="replace"))
            if match:
                year, rel = int(match.group(1)), int(match.group(2))
                return f"{year}r{rel}", (year, rel)
        if (folder / ".git").exists():
            break
    return None


def load_index() -> dict[str, tuple[str, str, str, str]]:
    """Two lookups: bare type names, and member names.

    They cannot share one table. `Text` is a deprecated *type*, but `.Text` is a
    current property on most controls, so a type name may only be matched where
    the syntax demands a type -- `As Text`, `New Text` -- and never after a dot.

    Member names are keyed by the qualified form, plus the bare member name when
    it is unambiguous. Code says `myList.ListCount`, not `ListBox.ListCount`, so
    the bare form is the only way to catch a member on an instance variable, and
    it is only safe when no current API uses the same name.
    """
    types: dict[str, tuple[str, str, str, str]] = {}
    members: dict[str, tuple[str, str, str, str]] = {}
    deprecated_leaves: dict[str, tuple[str, str, str, str]] = {}
    current_leaves: set[str] = set()

    for name, flag_col, ver, rep, note in (
        ("members.tsv", 3, 4, 5, 6),
        ("classes.tsv", 2, 3, 4, 5),
    ):
        path = REFERENCES / name
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines()[1:]:
            c = line.split("\t")
            if len(c) <= note:
                continue
            symbol = re.sub(r"\(.*", "", c[0]).strip().removesuffix(" (deprecated)")
            if not symbol:
                continue
            leaf = symbol.split(".")[-1].lower()
            entry = (symbol, c[ver], c[rep], c[note])
            if "deprecated" in c[flag_col]:
                if "." in symbol:
                    members.setdefault(symbol.lower(), entry)
                    deprecated_leaves.setdefault(leaf, entry)
                else:
                    types.setdefault(symbol.lower(), entry)
            else:
                current_leaves.add(leaf)

    for leaf, entry in deprecated_leaves.items():
        if leaf not in current_leaves:
            members.setdefault(leaf, entry)
    return {"types": types, "members": members}


def code_lines(text: str) -> list[tuple[int, str]]:
    """Line numbers and code, with prose blocks, strings and comments removed."""
    out: list[tuple[int, str]] = []
    in_prose = False
    for number, raw in enumerate(text.splitlines(), 1):
        if PROSE_OPEN.match(raw):
            in_prose = True
            continue
        if PROSE_CLOSE.match(raw):
            in_prose = False
            continue
        if in_prose or raw.lstrip().startswith("#tag"):
            continue
        line = STRING_LITERAL.sub('""', raw)
        line = COMMENT.sub("", line)
        if line.strip():
            out.append((number, line))
    return out


def find_uses(text: str, index: dict) -> list[tuple[int, str, tuple]]:
    """Deprecated symbols used as APIs, not as words."""
    types, members = index["types"], index["members"]
    hits: list[tuple[int, str, tuple]] = []
    for number, line in code_lines(text):
        # Member access: anything after a dot.
        for m in re.finditer(r"([A-Za-z_]\w*)\s*\.\s*([A-Za-z_]\w*)", line):
            receiver, name = m.group(1), m.group(2)
            entry = members.get(f"{receiver}.{name}".lower()) or members.get(name.lower())
            if entry:
                hits.append((number, f"{receiver}.{name}", entry))
        # Type position: As X, New X. Never a bare word on its own.
        for m in re.finditer(r"\b(?:As|New)\s+([A-Za-z_]\w*)", line, re.I):
            entry = types.get(m.group(1).lower())
            if entry:
                hits.append((number, m.group(1), entry))
        # Global function call: X(...), not preceded by a dot.
        for m in re.finditer(r"(?<![.\w])([A-Za-z_]\w*)\s*\(", line):
            entry = types.get(m.group(1).lower())
            if entry:
                hits.append((number, m.group(1), entry))
    return hits


def report(path: Path, index: dict, target: tuple[str, tuple[int, int]] | None) -> int:
    if path.suffix not in XOJO_SUFFIXES:
        return 0
    hits = find_uses(path.read_text(errors="replace"), index)
    if not hits:
        return 0

    seen: set[tuple[int, str]] = set()
    lines: list[str] = []
    for number, used, (canonical, version, replacement, note) in hits:
        if (number, used.lower()) in seen:
            continue
        seen.add((number, used.lower()))
        later = target and version and release_key(version) > target[1]
        mark = "  (deprecated after this project's target)" if later else ""
        arrow = f" -> {replacement}" if replacement else " -- no replacement"
        lines.append(f"  line {number}: {canonical}{arrow}  [{version or '?'}]{mark}")
        if note:
            lines.append(f"      {note}")

    print(f"{path.name}: {len(seen)} deprecated API(s)")
    if target:
        print(f"  project targets {target[0]}")
    print("\n".join(lines))
    return len(seen)


def main(argv: list[str]) -> int:
    if argv[:1] == ["--hook"]:
        try:
            payload = json.load(sys.stdin)
        except json.JSONDecodeError:
            return 0
        edited = (payload.get("tool_input") or {}).get("file_path")
        argv = [edited] if edited else []

    files = [Path(a) for a in argv if a]
    if not files:
        return 0
    index = load_index()
    if not index:
        print(f"no indexes at {REFERENCES}; run: docs.py build", file=sys.stderr)
        return 0

    total = sum(report(f, index, project_release(f)) for f in files if f.is_file())
    if total:
        print("\nLook each one up before replacing it; some renames also changed "
              "their index base. See SKILL.md.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
