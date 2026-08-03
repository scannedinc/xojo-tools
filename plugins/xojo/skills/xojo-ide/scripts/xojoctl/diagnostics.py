"""Diagnostic normalization."""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from .constants import *  # noqa: F401,F403
from .escaping import *  # noqa: F401,F403
from .framing import *  # noqa: F401,F403
from .journal import *  # noqa: F401,F403
from .transport import *  # noqa: F401,F403
from .discovery import *  # noqa: F401,F403
from .classify import *  # noqa: F401,F403
from .client import *  # noqa: F401,F403
from .scripts import *  # noqa: F401,F403
from .targets import *  # noqa: F401,F403


_LINE_IN_POSITION = re.compile(r",\s*line\s+(\d+)\s*$", re.IGNORECASE)

# The IDE wraps a submitted script in an enclosing method before compiling it,
# so every line number it reports for a scriptError is ONE GREATER than the line
# the caller actually wrote. Demonstrated on Windows:
#   a ONE-line script whose only line is bad      -> reported "line 2"
#   a five-line script, bad lines 1, 3 and 5      -> reported 2, 4 and 6
# Only scriptError is affected; buildError positions are parsed from prose and
# are already correct. The unadjusted value is preserved as `line_raw`.
SCRIPT_LINE_OFFSET = 1

# Keys already surfaced as their own field, so they are not repeated in the
# synthesized message for a wrapped open error.
_OPEN_ERROR_HANDLED = frozenset((
    "type", "message", "severity", "isfatal", "location", "position", "source"))


def unwrap_open_error(raw: Any) -> Tuple[Optional[str], Any]:
    """Unwrap the single-key envelope an openErrors entry arrives in.

    Entries are not diagnostics themselves -- they are one-key wrappers whose
    value holds the real payload, and that payload has NO "message" at all:

        {"loadError": {"type": "IDE Version Conflict",
                       "projectVersion": "<newer than this IDE>",
                       "ideVersion": "<this IDE>",
                       "severity": "error"}}

    (Established by opening a project saved by a newer IDE in an older one.)
    Reading
    only the top level found no message and rendered "error (no message)",
    discarding the entire explanation. Returns (wrapper_key, payload).
    """
    if isinstance(raw, dict) and "message" not in raw and len(raw) == 1:
        key, value = next(iter(raw.items()))
        if isinstance(value, dict):
            return key, value
    return None, raw


def describe_open_error(wrapper: Optional[str], obj: Any) -> Optional[str]:
    """Build a human message for an open error that carries none of its own."""
    if not isinstance(obj, dict):
        return None
    head = obj.get("type") or wrapper
    if head is None:
        return None
    extra = [
        "%s %s" % (k, obj[k])
        for k in sorted(obj)
        if k.lower() not in _OPEN_ERROR_HANDLED
        and isinstance(obj[k], (str, int, float, bool))
    ]
    text = str(head)
    if extra:
        text += " (%s)" % ", ".join(extra)
    return sanitize(text)


def normalize_diagnostic(raw: Any, severity: str, kind: str, origin: str,
                         index: int) -> Dict[str, Any]:
    """Flatten one IDE diagnostic into the stable schema.

    Two shapes feed this, and `location` means different things in each:
        buildError  -> location is a plain string, e.g. "Window1.Opening"
        scriptError -> location is an object,       e.g. {"column":6,"line":2}
    Discriminate on `kind`, which is known from the container key, rather than
    sniffing the element.
    """
    out: Dict[str, Any] = {
        "id": "%s%d" % ("s" if kind == "script" else "d", index),
        "severity": severity,
        "kind": kind,
        "type": None, "message": None,
        "location": None, "position": None,
        "line": None, "line_raw": None, "line_source": None,
        "column": None, "number": None,
        "source": None, "source_is_span": kind == "project",
        "origin": origin,
        "raw": raw,
    }
    if not isinstance(raw, dict):
        out["message"] = sanitize(json.dumps(raw))
        return out

    # An openErrors entry hides its payload one level down and has no message
    # of its own, so unwrap before reading any field off it.
    wrapper: Optional[str] = None
    body: Dict[str, Any] = raw
    if kind == "open":
        wrapper, unwrapped = unwrap_open_error(raw)
        if isinstance(unwrapped, dict):
            body = unwrapped

    out["type"] = body.get("type") or wrapper
    msg = body.get("message")
    out["message"] = sanitize(str(msg)) if msg is not None else None
    if kind == "open" and out["message"] is None:
        out["message"] = describe_open_error(wrapper, body)
    if kind == "open":
        # The wrapped payload carries its own severity; honor it so a
        # non-error is not announced as one.
        nested = body.get("severity")
        if isinstance(nested, str) and nested.strip().lower() in ("error", "warning"):
            out["severity"] = nested.strip().lower()

    loc = body.get("location")
    if kind == "script":
        obj = loc if isinstance(loc, dict) else {}
        line = obj.get("line", body.get("line"))
        if isinstance(line, int):
            out["line_raw"] = line
            # Undo the enclosing-method offset; see SCRIPT_LINE_OFFSET. Clamped
            # so an unexpected shape can never produce line 0, which the schema
            # promises never to emit: a 0 or negative line from the IDE is
            # meaningless and becomes null (line_raw keeps what was sent).
            if line > SCRIPT_LINE_OFFSET:
                out["line"] = line - SCRIPT_LINE_OFFSET
                out["line_source"] = "line_field_unwrapped"
            elif line > 0:
                out["line"] = line
                out["line_source"] = "line_field"
        col = obj.get("column")
        if isinstance(col, int):
            # The IDE sends -1 for "unknown"; the schema promises null for
            # that. Non-negative values pass through exactly as sent -- the
            # IDE's column base has not been verified against a live run, so
            # no conversion is applied.
            out["column"] = col if col >= 0 else None
        num = body.get("number")
        if isinstance(num, int):
            out["number"] = num
        out["source_is_span"] = False
    else:
        if isinstance(loc, str):
            out["location"] = sanitize(loc)
        pos = body.get("position")
        if isinstance(pos, str):
            out["position"] = sanitize(pos)
            m = _LINE_IN_POSITION.search(pos)
            if m:
                out["line"] = int(m.group(1))
                out["line_source"] = "position"
        src = body.get("source")
        if src is not None:
            # The exact span the IDE highlights -- may be syntactically
            # incomplete by design. Usable for carets, not parseable.
            out["source"] = sanitize(str(src))
    return out


def normalize(cl: Classification) -> List[Dict[str, Any]]:
    diags: List[Dict[str, Any]] = []
    n = 0
    if cl.key == "scriptError":
        # Warnings first, matching the buildError ordering below.
        for i, w in enumerate(cl.warnings):
            n += 1
            diags.append(normalize_diagnostic(w, "warning", "script",
                                              "scriptError.warnings[%d]" % i, n))
        for i, e in enumerate(cl.errors):
            n += 1
            diags.append(normalize_diagnostic(e, "error", "script",
                                              "scriptError.errors[%d]" % i, n))
        return diags
    if cl.key == "missingFiles":
        return [normalize_diagnostic(
            {"type": "missingFiles", "message": cl.note}, "error", "config",
            "missingFiles", 1)]
    if cl.key == "openErrors":
        for i, e in enumerate(cl.errors):
            n += 1
            diags.append(normalize_diagnostic(e, "error", "open",
                                              "openErrors[%d]" % i, n))
        return diags
    for i, w in enumerate(cl.warnings):
        n += 1
        diags.append(normalize_diagnostic(w, "warning", "project",
                                          "buildError.warnings[%d]" % i, n))
    for i, e in enumerate(cl.errors):
        n += 1
        diags.append(normalize_diagnostic(e, "error", "project",
                                          "buildError.errors[%d]" % i, n))
    return diags


# ===========================================================================
# CLI -- everything below may touch argparse, stdout and exit codes
# ===========================================================================

def _iso_utc(ts: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(ts)) + "Z"


class Note:
    """Stable, machine-readable advisories carried in JSON and shown to humans."""

    AMBIGUOUS_WORKSPACE = (
        "ambiguous_workspace", "info",
        "Xojo is single-instance. With more than one project open, commands act "
        "on the frontmost workspace and the protocol gives no way to tell which.",
        "Keep exactly one project open for unattended use.")
    WARNINGS_NOT_REPORTED = (
        "warnings_not_reported", "info",
        "BuildApp does not report warnings; only analyze does. A clean build "
        "does not mean the project has no warnings.",
        "%s analyze" % INVOCATION)
    WARNINGS_ONLY_EXIT_ZERO = (
        "warnings_only_exit_zero", "info",
        "Warnings with no errors are not a failure; this run exits 0.",
        "Pass --warnings-as-errors to exit 1 instead.")
    WARNINGS_PROMOTED = (
        "warnings_promoted_to_errors", "info",
        "--warnings-as-errors is set, so warnings with no errors exit 1.", None)
    COLD_START_SLOW = (
        "cold_start_slow", "info",
        "The first reply took over 20s. A cold IDE unpacks its plugins before "
        "servicing anything; this is expected, not a fault.", None)
    EMPTY_RESPONSE = (
        "empty_response_no_op", "warning",
        "The command produced no output. Why is not knowable from the protocol: "
        "a build can return nothing because the IDE is still busy with an "
        "earlier build, or because the target is unavailable for this project. "
        "Retrying once the IDE is idle distinguishes the two.",
        None)
    RESULT_INCOMPLETE = (
        "result_incomplete", "warning",
        "Some messages were dropped, so this result may be incomplete. Do not "
        "read it as a clean project.", None)
    SCRIPT_COMPILER_WARNING = (
        "script_compiler_warning", "info",
        "The IDE returned compiler warnings for the script, but no errors: it "
        "compiled and ran. A scriptError array can carry warnings as well as "
        "errors, distinguished only by each entry's 'type'.", None)
    UNSOLICITED = (
        "unsolicited_messages", "info",
        "The IDE sent messages this command did not request -- usually someone "
        "using the IDE while xojoctl was connected. They are in raw.messages.",
        None)
    SENTINEL_NOT_SEEN = (
        "build_sentinel_not_seen", "warning",
        "The build script's completion sentinel never arrived, so the IDE may "
        "still be busy with this build. Remaining targets were skipped: a busy "
        "IDE answers the next few commands with empty responses, which read as "
        "failures that never happened.", None)
    SPLIT_REPLY = (
        "split_reply_extra_messages", "warning",
        "The IDE sent additional messages under this command's tag beyond the "
        "reply it first claimed. All parts were judged together; the extras "
        "are preserved in raw.messages.", None)
    SCRIPT_NOT_COMPLETED = (
        "script_completion_unconfirmed", "warning",
        "The script's completion sentinel never arrived, so it may still be "
        "running, may have returned early, or may have failed at runtime. "
        "Any output it produced after that point was not captured.", None)


def note(spec: Tuple[str, str, str, Optional[str]], **extra: Any) -> Dict[str, Any]:
    d = {"code": spec[0], "severity": spec[1], "message": spec[2]}
    if spec[3]:
        d["hint"] = spec[3]
    d.update(extra)
    return d


@dataclass
class Result:
    command: str
    ok: bool = True
    outcome: str = "success"
    exit_code: int = EX_OK
    summary: str = ""
    connection: Dict[str, Any] = field(default_factory=dict)
    ide: Dict[str, Any] = field(default_factory=lambda: {"version": None})
    project: Dict[str, Any] = field(default_factory=lambda: {
        "identified": False, "path": None,
        "reason": "the IPC protocol does not report which workspace is frontmost"})
    timing: Dict[str, Any] = field(default_factory=dict)
    result: Dict[str, Any] = field(default_factory=dict)
    diagnostics: List[Dict[str, Any]] = field(default_factory=list)
    counts: Dict[str, int] = field(default_factory=lambda: {
        "errors": 0, "warnings": 0, "script_errors": 0, "open_errors": 0})
    notes: List[Dict[str, Any]] = field(default_factory=list)
    error: Optional[Dict[str, Any]] = None
    raw: Dict[str, Any] = field(default_factory=lambda: {
        "messages": [], "dropped": 0, "truncated": False})

    def recount(self) -> None:
        c = {"errors": 0, "warnings": 0, "script_errors": 0, "open_errors": 0}
        for d in self.diagnostics:
            # Severity is decided FIRST: script and open payloads carry warnings
            # too, and counting those under script_errors/open_errors reported a
            # failure count for something that never failed.
            if d["severity"] == "warning":
                c["warnings"] += 1
            elif d["kind"] == "script":
                c["script_errors"] += 1
            elif d["kind"] == "open":
                c["open_errors"] += 1
            else:
                c["errors"] += 1
        self.counts = c

    def to_json(self, include_raw: bool = True) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "tool": TOOL_NAME,
            "tool_version": TOOL_VERSION,
            "command": self.command,
            "ok": self.ok,
            "outcome": self.outcome,
            "exit_code": self.exit_code,
            "summary": self.summary,
            "connection": self.connection,
            "ide": self.ide,
            "project": self.project,
            "timing": self.timing,
            "result": self.result,
            "diagnostics": self.diagnostics,
            "counts": self.counts,
            "notes": self.notes,
            "error": self.error,
        }
        if include_raw:
            d["raw"] = self.raw
        return d


__all__ = [
    "Note",
    "Result",
    "SCRIPT_LINE_OFFSET",
    "_LINE_IN_POSITION",
    "_OPEN_ERROR_HANDLED",
    "_iso_utc",
    "describe_open_error",
    "normalize",
    "normalize_diagnostic",
    "note",
    "unwrap_open_error",
]
