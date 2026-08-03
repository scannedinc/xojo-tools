"""IDE Scripts."""

from __future__ import annotations


from .constants import *  # noqa: F401,F403
from .escaping import *  # noqa: F401,F403
from .framing import *  # noqa: F401,F403
from .journal import *  # noqa: F401,F403
from .transport import *  # noqa: F401,F403
from .discovery import *  # noqa: F401,F403
from .classify import *  # noqa: F401,F403
from .client import *  # noqa: F401,F403


def script_version() -> str:
    # XojoVersion is a Double; Print takes a String.
    return "Print Str(XojoVersion)"


def script_window_count() -> str:
    """Probe for the number of open workspace windows.

    `.ToString`, NOT `Str(...)`: WindowCount is an Int64 and Str() takes a
    Double, so `Str(WindowCount)` provokes

        "Converting from Int64 to Double causes a possible loss of precision"

    as a scriptCompilerWarning. It is only a warning and the script still runs,
    but it arrives as an extra scriptError message under this exchange's tag --
    so the tool was manufacturing the very diagnostic noise it then had to
    classify. ToString is exact for an integer and provokes nothing.
    """
    return "Print WindowCount.ToString"


def script_analyze_project() -> str:
    """Analyze the whole project.

    THE TRAILING PRINT IS MANDATORY -- see finding 2. A clean project emits
    nothing at all from CheckProjectErrors, so without a sentinel every clean
    project hangs to the ceiling. Finding 3 confirms the sentinel does not
    clobber diagnostics when there are any.
    """
    return ('DoCommand("CheckProjectErrors")\nPrint %s'
            % xojo_string_literal(ANALYZE_SENTINEL))


def script_analyze_item(item: str) -> str:
    """Analyze ONE project item.

    SelectProjectItem is a FUNCTION: a bare call fails to compile
    with "You must use the value returned by this function" (verified on
    Windows, where dropping the use reproduces it every time). Its
    Boolean result is also the ONLY signal that the item exists: with a
    mistyped name, CheckItemErrors would run against whatever was previously
    selected and report a clean pass for an item that was never analyzed.
    So the result is BRANCHED ON rather than discarded with `Call`: analysis
    runs only after a successful select, and a failed select prints a
    distinct marker that the caller turns into an error.
    """
    return ("If SelectProjectItem(%s) Then\n"
            'DoCommand("CheckItemErrors")\n'
            "Print %s\n"
            "Else\n"
            "Print %s\n"
            "End If"
            % (xojo_string_literal(item),
               xojo_string_literal(ANALYZE_SENTINEL),
               xojo_string_literal(ANALYZE_ITEM_MISSING)))


def script_build(build_type: int, reveal: bool = False) -> str:
    """Build, then Print a sentinel so completion is observable.

    A script that Prints twice yields TWO messages under one tag, so the reply
    tells us which of three things happened:

        path, then sentinel -> the build produced an artifact
        sentinel only       -> the script RAN TO COMPLETION but BuildApp
                               printed nothing
        neither             -> we stopped waiting; the IDE may still be busy

    Without the sentinel the last two are indistinguishable, which is how a
    too-short ceiling once got reported as "the target does not apply".
    """
    # build_type comes from a whitelist and reveal is a bool, so neither is
    # escaped; keep it that way rather than formatting caller input here.
    return ("Print BuildApp(%d,%s)\nPrint %s"
            % (build_type, "True" if reveal else "False",
               xojo_string_literal(BUILD_SENTINEL)))


def script_open_project(path: str) -> str:
    # Bare OpenFile, NEVER DoCommand("OpenFile"): the latter opens a modal
    # dialog and blocks the IDE waiting for a human.
    return ("OpenFile(%s)\nPrint %s"
            % (xojo_string_literal(path), xojo_string_literal("opened")))


def script_list_windows() -> str:
    """Enumerate open workspace titles in ONE script.

    A script's Prints do not reliably arrive as separate messages, so the loop
    builds a single tab-separated string and Prints that once. WindowTitle is
    0-BASED and index 0 is the FRONTMOST workspace; WindowTitle(WindowCount)
    returns an empty response. Declaring the loop variable separately is
    required -- the IDE Script dialect rejects `For i As Integer = ...`.
    """
    return ("Var i As Integer\n"
            "Var s As String\n"
            "For i = 0 To WindowCount - 1\n"
            "s = s + WindowTitle(i) + Chr(9)\n"
            "Next\n"
            "Print s")


def script_front_path() -> str:
    return "Print ProjectShellPath"


def _ascii_digits(text: str) -> bool:
    """True only for plain ASCII digits.

    str.isdigit() is a Unicode predicate: it accepts Arabic-Indic digits
    (which int() converts, silently) and superscripts (which int() rejects,
    with a raw ValueError) -- both routes around the curated errors at every
    call site that means 'this is a plain number'.
    """
    return bool(text) and text.isascii() and text.isdigit()


def script_select_window(which: str) -> str:
    # SelectWindow takes a title or an index; an all-digit argument is passed
    # as a number so `--select 2` means the index, not a project called "2".
    # ASCII digits only: a bare non-ASCII digit is not a valid Xojo numeric
    # literal, so interpolating it unquoted makes the IDE reject the script.
    arg = which if _ascii_digits(which) else xojo_string_literal(which)
    return "SelectWindow(%s)\nPrint WindowTitle(0)" % arg


def script_save_project() -> str:
    # DoCommand("SaveFile") saves the front project with no prompt. A project
    # that has never been saved to disk has no path, so the IDE may still show
    # Save As -- xojoctl cannot detect that case from here.
    return 'DoCommand("SaveFile")\nPrint %s' % xojo_string_literal("saved")


def script_close_project(save: bool) -> str:
    """Close the front project.

    CAREFUL: the parameter is `prompt`, NOT `save`.
        CloseProject(prompt As Boolean = True)
        True  -> show a dialog asking whether to save   <- hangs automation
        False -> close silently, DISCARDING any changes

    So CloseProject alone can never save. To save we must DoCommand("SaveFile")
    first and then close with prompt=False. Passing True from a script would
    park a modal dialog in front of a user who is not there.
    """
    steps = ['DoCommand("SaveFile")'] if save else []
    steps.append("CloseProject(False)")
    steps.append("Print %s" % xojo_string_literal("closed"))
    return "\n".join(steps)


def script_run() -> str:
    return 'DoCommand("RunApp")\nPrint %s' % xojo_string_literal("running")


def script_stop() -> str:
    return 'DoCommand("Kill")\nPrint %s' % xojo_string_literal("stopped")


__all__ = [
    "_ascii_digits",
    "script_analyze_item",
    "script_analyze_project",
    "script_build",
    "script_close_project",
    "script_front_path",
    "script_list_windows",
    "script_open_project",
    "script_run",
    "script_save_project",
    "script_select_window",
    "script_stop",
    "script_version",
    "script_window_count",
]
