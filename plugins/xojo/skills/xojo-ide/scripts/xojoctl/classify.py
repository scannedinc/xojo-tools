"""Reply classification."""

from __future__ import annotations

import enum
import json
from dataclasses import dataclass, field
from typing import Any, List, Optional, Sequence, Tuple

from .constants import *  # noqa: F401,F403
from .escaping import *  # noqa: F401,F403
from .framing import *  # noqa: F401,F403
from .journal import *  # noqa: F401,F403
from .transport import *  # noqa: F401,F403
from .discovery import *  # noqa: F401,F403


class Verdict(enum.Enum):
    OK = "ok"
    EMPTY = "empty"
    WARNINGS = "warnings"
    ERRORS = "errors"
    SCRIPT_ERROR = "script-error"
    OPEN_ERRORS = "open-errors"
    MISSING_FILES = "missing-files"   # something must be configured first
    UNKNOWN = "unknown"


# "missingFiles" is undocumented but real: an Android build with no key store
# returns {"missingFiles": "Unable to build. Please specify a Key Store
# properties file in the Android Build Settings."} -- a precise, actionable
# message that was otherwise discarded as an "unrecognized dict".
DIAG_KEYS = ("scriptError", "buildError", "openErrors", "loadError",
             "missingFiles")


def locate_diagnostics(env: Any) -> Tuple[Optional[str], Any, Optional[str]]:
    """Find the diagnostics payload; returns (key, payload, layout).

    Observed builds nest the error INSIDE "response". A documented-but-unseen
    legacy layout puts it beside "tag". "response" is checked first so the
    modern shape wins if both ever appear.
    """
    if not isinstance(env, dict):
        return None, None, None
    for layout, container in (("response", env.get("response")), ("envelope", env)):
        if isinstance(container, dict):
            for key in DIAG_KEYS:
                if key in container:
                    return key, container[key], layout
    return None, None, None


def split_script_diagnostics(items: Sequence[Any]) -> Tuple[List[Any], List[Any]]:
    """Partition a scriptError array into (errors, warnings).

    The array is HETEROGENEOUS: each entry carries a `type` that is either
    scriptCompilerError or scriptCompilerWarning. Treating the whole container
    as fatal reported "the IDE rejected the script" and exited 5 for a script
    that compiled and ran perfectly -- observed in the wild, where the IDE emits

        {"scriptError": [{"type": "scriptCompilerWarning", ...,
          "message": "Converting from Int64 to Double causes a possible loss
                      of precision, ..."}]}

    as the ONLY content of a reply. Anything without a recognizably-warning
    type is treated as an error, so an unknown shape still fails loudly.
    """
    errs: List[Any] = []
    warns: List[Any] = []
    for entry in items:
        kind = entry.get("type") if isinstance(entry, dict) else None
        if isinstance(kind, str) and kind.strip().lower().endswith("warning"):
            warns.append(entry)
        else:
            errs.append(entry)
    return errs, warns


def _has_fatal_open_error(items: Sequence[Any]) -> bool:
    """openErrors is heterogeneous and projectError is polymorphic.

    isFatal matters: a NON-fatal openErrors leaves a usable project, and
    treating it as fatal makes the tool useless on any project with a stale
    asset link.

    isFatal is the ONLY fatality signal. A nested "severity": "error" is
    NOT one: the captured IDE Version Conflict payload carries exactly that
    and the project still loads, so treating severity as fatality failed a
    working open. The conflict is still reported as a diagnostic; it just
    does not change the exit code.
    """
    for entry in items:
        if not isinstance(entry, dict):
            continue
        for value in entry.values():
            cands = (value if isinstance(value, list)
                     else [value] if isinstance(value, dict) else [])
            for c in cands:
                if not isinstance(c, dict):
                    continue
                if c.get("isFatal"):
                    return True
    return False


@dataclass
class Classification:
    verdict: Verdict
    key: Optional[str] = None
    layout: Optional[str] = None
    text: Optional[str] = None
    errors: List[Any] = field(default_factory=list)
    warnings: List[Any] = field(default_factory=list)
    fatal: bool = False
    note: Optional[str] = None
    payload: Any = None


def classify(msg: Message) -> Classification:
    env = msg.envelope
    if env is None:
        return Classification(Verdict.UNKNOWN, note="reply was not valid UTF-8 JSON")
    if not isinstance(env, dict):
        return Classification(
            Verdict.UNKNOWN,
            note="reply was a JSON %s, not an object" % type(env).__name__)

    key, payload, layout = locate_diagnostics(env)

    if key == "scriptError":
        items = payload if isinstance(payload, list) else [payload]
        errs, warns = split_script_diagnostics(items)
        if errs:
            return Classification(
                Verdict.SCRIPT_ERROR, key, layout, errors=errs, warnings=warns,
                payload=payload,
                note="the IDE rejected the script xojoctl sent -- this is a "
                     "client bug, not a project problem")
        # Warnings ONLY. The script compiled and RAN; nothing was rejected.
        # Calling this an error made the tool fail on its own probe script (see
        # script_compiler_warning note), so it must not be SCRIPT_ERROR.
        return Classification(
            Verdict.WARNINGS, key, layout, warnings=warns, payload=payload,
            note="the IDE returned compiler warnings for the script; it still ran")

    if key == "buildError":
        if not isinstance(payload, dict):
            return Classification(Verdict.UNKNOWN, key, layout, payload=payload,
                                  note="buildError was not an object")
        errs = payload.get("errors") or []
        warns = payload.get("warnings") or []
        if not isinstance(errs, list) or not isinstance(warns, list):
            return Classification(
                Verdict.UNKNOWN, key, layout, payload=payload,
                note="buildError.errors/warnings were not arrays")
        if errs:
            return Classification(Verdict.ERRORS, key, layout, errors=list(errs),
                                  warnings=list(warns), payload=payload)
        if warns:
            return Classification(Verdict.WARNINGS, key, layout,
                                  warnings=list(warns), payload=payload)
        return Classification(Verdict.OK, key, layout, payload=payload,
                              note="analysis reported zero errors and zero warnings")

    if key == "openErrors":
        items = payload if isinstance(payload, list) else [payload]
        return Classification(Verdict.OPEN_ERRORS, key, layout, errors=list(items),
                              fatal=_has_fatal_open_error(items), payload=payload)

    if key == "missingFiles":
        text = payload if isinstance(payload, str) else json.dumps(payload)
        return Classification(Verdict.MISSING_FILES, key, layout, payload=payload,
                              note=sanitize(text))

    if key == "loadError":
        return Classification(Verdict.UNKNOWN, key, layout, payload=payload,
                              note="loadError: shape is undocumented and unobserved")

    if "response" not in env:
        return Classification(
            Verdict.UNKNOWN,
            note="reply carried neither 'response' nor a recognized error key")

    resp = env["response"]
    if isinstance(resp, str):
        return Classification(Verdict.OK, text=resp, payload=resp)
    if resp is None or (isinstance(resp, dict) and not resp):
        return Classification(
            Verdict.EMPTY, payload=resp,
            note="the command produced no output and no error")
    return Classification(
        Verdict.UNKNOWN, payload=resp,
        note="response was an unrecognized %s" % type(resp).__name__)


__all__ = [
    "Classification",
    "DIAG_KEYS",
    "Verdict",
    "_has_fatal_open_error",
    "classify",
    "locate_diagnostics",
    "split_script_diagnostics",
]
