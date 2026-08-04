"""Escaping: the code-execution boundary."""

from __future__ import annotations

import json
import re

from .constants import *  # noqa: F401,F403


_FORBIDDEN = re.compile(r"[\x00-\x1f\x7f-\x9f]")


def xojo_string_literal(value: str) -> str:
    """Render `value` as a Xojo string literal.

    Xojo does NOT use backslash escapes. An embedded double quote is written by
    DOUBLING it (a literal " is written ""). Backslash is an ORDINARY character
    and is passed through untouched; backslash-escaping here would corrupt
    Windows paths while neutralising nothing.

    Control characters are rejected rather than escaped: IDE Script statements
    are newline-separated, so a newline in an interpolated value is a statement
    break, and no legitimate project path contains one.
    """
    m = _FORBIDDEN.search(value)
    if m:
        raise ValueError(
            "value contains control character %r at offset %d; "
            "refusing to build a script" % (m.group(), m.start())
        )
    return '"' + value.replace('"', '""') + '"'


BOM = "﻿"


def strip_bom(text: str) -> str:
    """Drop a leading BOM from an already-decoded script.

    U+FEFF is not a control character, so xojo_string_literal() passes it
    through and it silently becomes part of the first statement.
    """
    return text[1:] if text.startswith(BOM) else text


_SURROGATE = re.compile(r"[\ud800-\udfff]")


def encode_request(tag: str, script: str) -> bytes:
    """Build the JSON envelope with a real encoder. NEVER concatenation.

    This is the actual fix for script injection. A filename containing the six
    literal characters \\u0022 marshals to \\\\u0022 and decodes IDE-side back to
    those same six characters -- an odd substring of a filename, not a quote.
    ensure_ascii (the default) also guarantees no raw NUL reaches the wire
    ahead of the framing NUL.

    Unpaired surrogates are rejected up front: json.dumps would happily emit
    a bare \\udcXX escape, which is not valid JSON interchange -- a strict
    IDE-side parser drops the envelope and the command times out blaming a
    cold IDE. They reach here via surrogateescape-decoded argv (a filename
    that is not valid UTF-8), and an early loud error names the real cause.
    """
    m = _SURROGATE.search(script)
    if m:
        raise ValueError(
            "script contains an unpaired surrogate (U+%04X at offset %d) and "
            "cannot be sent as JSON text; a path argument is probably not "
            "valid UTF-8" % (ord(m.group()), m.start()))
    return json.dumps({"script": script, "tag": tag}).encode("ascii") + NUL


_SHELL_ESCAPE = re.compile(r"\\(.)")


def unescape_shell_path(value: str) -> str:
    """Turn BuildApp's shell-escaped path into a real filesystem path.

    Finding 6: BuildApp returns e.g.  /Users/me/Test\\ Project/...  which is a
    shell path, not a filesystem path. POSIX ONLY: on Windows the backslash is
    the path SEPARATOR, not an escape -- stripping every backslash+character
    pair would turn C:\\Users\\me into C:Usersme -- so Windows paths are passed
    through untouched. (The IDE runs on the same machine as this client, so
    the host platform decides which convention the IDE's paths use.)
    """
    if IS_WINDOWS:
        return value
    return _SHELL_ESCAPE.sub(r"\1", value)


_ANSI = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]|\x1b[@-Z\\-_]")
_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f\u202a-\u202e]")


def sanitize(text: str) -> str:
    """Strip terminal control sequences from IDE-supplied text.

    Everything in a reply is IDE-controlled and lands in a terminal; without
    this, project content can rewrite the display. Carriage return gets
    special handling: a raw CR returns the cursor to column 0 and lets the
    rest of the text overwrite what was already printed -- the exact spoof
    this function exists to prevent -- so CRLF pairs become plain newlines
    and a lone CR is replaced. Raw C1 controls (U+0080-U+009F) are covered by
    the class below; newline and tab pass through on purpose. The deprecated
    bidi embeddings/overrides (U+202A-U+202E) are in the class too: RLO
    visually reverses the rest of a line, the same display-rewrite as CR.
    The isolates (U+2066-U+2069) pass through -- they are how legitimate
    RTL text is wrapped, and they cannot reverse an already-printed prefix.
    """
    text = _ANSI.sub("", text)
    text = text.replace("\r\n", "\n").replace("\r", "�")
    return _CTRL.sub("�", text)


__all__ = [
    "BOM",
    "_ANSI",
    "_CTRL",
    "_FORBIDDEN",
    "_SHELL_ESCAPE",
    "encode_request",
    "sanitize",
    "strip_bom",
    "unescape_shell_path",
    "xojo_string_literal",
]
