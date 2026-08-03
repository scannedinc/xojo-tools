"""Human rendering."""

from __future__ import annotations

import os
from typing import Any, Dict, List

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
from .diagnostics import *  # noqa: F401,F403


class Style:
    def __init__(self, enabled: bool) -> None:
        self.on = enabled

    def _w(self, code: str, text: str) -> str:
        return "\033[%sm%s\033[0m" % (code, text) if self.on else text

    def red(self, t: str) -> str: return self._w("31", t)
    def yellow(self, t: str) -> str: return self._w("33", t)
    def green(self, t: str) -> str: return self._w("32", t)
    def dim(self, t: str) -> str: return self._w("2", t)
    def bold(self, t: str) -> str: return self._w("1", t)


def want_color(choice: str, stream: Any) -> bool:
    if choice == "always":
        return True
    if choice == "never":
        return False
    return bool(getattr(stream, "isatty", lambda: False)()) and not os.environ.get("NO_COLOR")


def render_diagnostic(d: Dict[str, Any], st: Style) -> List[str]:
    label = st.red("error") if d["severity"] == "error" else st.yellow("warning")
    where = d.get("position") or d.get("location")
    if not where and d.get("line") is not None:
        where = "line %d" % d["line"]
        if d.get("column") is not None:
            where += ", col %d" % d["column"]
    head = "  %s  %s" % (label, d.get("message") or "(no message)")
    lines = [head]
    if where:
        lines.append("    %s %s" % (st.dim("at"), where))
    src = d.get("source")
    if src:
        lines.append("    %s %s" % (st.dim("|"), src))
    return lines


def render_human(res: Result, st: Style, out: Any) -> None:
    if res.diagnostics:
        warns = [d for d in res.diagnostics if d["severity"] == "warning"]
        errs = [d for d in res.diagnostics if d["severity"] == "error"]
        for group, items in (("warnings", warns), ("errors", errs)):
            if not items:
                continue
            color = st.yellow if group == "warnings" else st.red
            print(color("%d %s" % (len(items), group[:-1] if len(items) == 1 else group)),
                  file=out)
            for d in items:
                for line in render_diagnostic(d, st):
                    print(line, file=out)
            print(file=out)

    if res.result.get("artifacts"):
        for a in res.result["artifacts"]:
            if a.get("path"):
                # The path is IDE-supplied text like everything else in the
                # reply; sanitize at print time so JSON keeps it verbatim.
                print("%s %s" % (st.green("built"), sanitize(a["path"])), file=out)
            else:
                print("%s %s" % (st.red("failed"), a.get("target", "?")), file=out)

    # Only `script` renders raw Print output -- for other commands the Print is
    # an internal completion sentinel and echoing it is noise. Print output is
    # project-controlled text headed for a terminal, so it is sanitized here
    # rather than at classify time, which keeps raw/JSON verbatim. Output and
    # diagnostics are independent channels: a script that printed AND warned
    # shows both, as the README promises.
    if res.command == "script" and res.result.get("output") is not None:
        print(sanitize(res.result["output"]), file=out)

    mark = st.green("ok") if res.ok else st.red("fail")
    print("%s %s" % (mark, res.summary), file=out)


def render_notes(res: Result, st: Style, err: Any, quiet: bool) -> None:
    if quiet:
        return
    for n in res.notes:
        if n["severity"] == "warning":
            print("%s %s" % (st.yellow("note:"), n["message"]), file=err)
        else:
            print("%s %s" % (st.dim("note:"), st.dim(n["message"])), file=err)
        if n.get("hint"):
            print("      %s" % st.dim(n["hint"]), file=err)


def render_error(res: Result, st: Style, out: Any) -> None:
    e = res.error or {}
    print("%s %s" % (st.red("error:"), e.get("message", "unknown failure")), file=out)
    for step in e.get("remedy", []):
        print("  - %s" % step, file=out)


__all__ = [
    "Style",
    "render_diagnostic",
    "render_error",
    "render_human",
    "render_notes",
    "want_color",
]
