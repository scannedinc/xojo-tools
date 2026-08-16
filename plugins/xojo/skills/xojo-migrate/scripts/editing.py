#!/usr/bin/env python3
"""Shared call-site parsing and safe file IO for the source-editing scripts.

Not a command. The editing scripts (targeted_rename.py, apply_rules.py,
global_to_method.py, mid_to_middle.py) import from here so that call
parsing, receiver legality and file IO each have exactly one
implementation.

The editor pattern, stated once: SEARCH THE MASKED LINE, EDIT THE REAL
LINE. `masked_pairs()` returns each real source line beside its
`scan.code_only` mask, which blanks string literals, comments, layout
`Begin` blocks and `#tag` metadata while preserving length and line
count -- so an offset found in the masked line is valid in the real one.
Matching the real text instead converts `Left = 110` in a window's
layout block and `Len(` inside an archived `#tag Note` slab; on a real
project the metadata hits outnumbered the code hits better than ten to
one for some symbols. Find the call span in the MASKED line (parens
inside string literals are blanked there), then slice and split the REAL
line (`split_args` respects the strings that slice contains).

Read with `read_source()` and write with `write_source()`: both use
errors="surrogateescape", so bytes that are not valid UTF-8 survive a
read-edit-write round trip byte for byte. A replace-mode read turns each
such byte into U+FFFD, and a later write bakes that corruption into the
user's source file.

(stdlib only)
"""
import os
import pathlib
import re
import stat
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from scan import code_only, mask_line  # noqa: E402

# A method signature line. Used to find the enclosing method for a call
# site and, in locate.py, to index method bodies. Matches on the
# code_only-masked line so a signature quoted in a #tag Note slab or a
# comment is not a signature.
SIGNATURE = re.compile(
    r"^\s*(?:Protected\s+|Private\s+|Public\s+|Global\s+|Shared\s+|"
    r"Attributes\s*\([^)]*\)\s+)*(?:Sub|Function)\s+([A-Za-z_]\w*)",
    re.I,
)

# Hard rule 3 (conversion-traps.md section 4): a receiver must be an
# identifier, or a chain of member accesses / calls / indexes off one. A
# string literal and a parenthesised expression are syntax errors as
# receivers: `("00" + Hex(r)).Right(2)` does not compile, while
# `f.Child("x").Name` and `s.Trim.Uppercase` do. The call/index segment
# allows one level of nested parens inside itself.
RECEIVER = re.compile(
    r"^[A-Za-z_]\w*(?:\s*\.\s*[A-Za-z_]\w*"
    r"|\s*\([^()]*(?:\([^()]*\)[^()]*)*\))*$"
)


def legal_receiver(expr):
    """True when `expr` can legally receive a method call in Xojo.

    String-literal contents are blanked before the grammar test, so a
    paren or quote INSIDE a quoted argument -- NthField(s, "(", 1) --
    cannot fail a receiver that compiles fine. The blanking keeps the
    delimiters, so a receiver that IS a string literal still starts
    with a quote and is still refused.
    """
    s = expr.strip()
    if not s or s.startswith('"') or s.startswith("("):
        return False
    return bool(RECEIVER.fullmatch(mask_line(s)))


def find_call(line, start):
    """Span of the call parens at/after `start`: (open_idx, close_idx).

    `start` is the index where the callable's name begins (or any point
    before its opening paren). Tracks string literals with Xojo's ""
    escape so a paren inside a string neither opens nor closes anything.
    Returns None when there is no opening paren after `start` or the
    parens do not balance on this line (the call spans lines) -- callers
    must report that site, not guess.
    """
    o = line.find("(", start)
    if o < 0:
        return None
    depth, i, in_string = 0, o, False
    while i < len(line):
        c = line[i]
        if in_string:
            if c == '"':
                if i + 1 < len(line) and line[i + 1] == '"':
                    i += 1
                else:
                    in_string = False
        elif c == '"':
            in_string = True
        elif c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return o, i
        i += 1
    return None


def split_args(text):
    """Split an argument list on its top-level commas.

    Commas inside nested parens and inside string literals (with Xojo's
    "" escape) do not split. Splitting `s, "a,b", f(x, y)` yields three
    arguments. The pieces keep their original spacing; callers strip.
    """
    args, depth, cur, i, in_string = [], 0, "", 0, False
    while i < len(text):
        c = text[i]
        if in_string:
            cur += c
            if c == '"':
                if i + 1 < len(text) and text[i + 1] == '"':
                    cur += text[i + 1]
                    i += 1
                else:
                    in_string = False
        elif c == '"':
            in_string = True
            cur += c
        elif c == "(":
            depth += 1
            cur += c
        elif c == ")":
            depth -= 1
            cur += c
        elif c == "," and depth == 0:
            args.append(cur)
            cur = ""
        else:
            cur += c
        i += 1
    args.append(cur)
    return args


def read_source(path):
    """Read a Xojo source file, preserving bytes that are not UTF-8.

    newline="" keeps \\r\\n endings as they are on disk; the default
    universal-newlines read would rewrite them to \\n on the next save.
    """
    with open(path, encoding="utf-8", errors="surrogateescape",
              newline="") as f:
        return f.read()


def write_source(path, text):
    """Write text read by read_source back, byte-for-byte where unedited.

    Writes a sibling .part and renames, so an interrupted write never
    leaves the user's source file truncated.
    """
    # realpath first: os.replace on the symlink itself would break the
    # link, where open("w") writes through it.
    real = pathlib.Path(os.path.realpath(path))
    # os.replace needs only directory write permission, so without this
    # check a deliberately write-protected file would be replaced where
    # open("w") raised PermissionError.
    if real.exists() and not os.access(real, os.W_OK):
        raise PermissionError(f"{path} is not writable")
    tmp = real.with_name(real.name + ".part")
    try:
        with open(tmp, "w", encoding="utf-8", errors="surrogateescape",
                  newline="") as f:
            f.write(text)
        if real.exists():
            os.chmod(tmp, stat.S_IMODE(os.stat(real).st_mode))
        os.replace(tmp, real)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def masked_pairs(text):
    """The file as [(real_line, masked_line), ...], split on \\n.

    Both sides split at identical offsets: code_only preserves length
    and never blanks a newline. Line endings stay with the real lines
    (a \\r\\n file's real lines end in \\r), so rebuilding the file is
    exactly "\\n".join(real_lines) -- which reproduces the input byte
    for byte when nothing was edited.
    """
    return list(zip(text.split("\n"), code_only(text).split("\n")))
