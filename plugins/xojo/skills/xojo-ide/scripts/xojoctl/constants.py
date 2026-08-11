"""Constants, exceptions, and protocol tunables."""

from __future__ import annotations

import os
import sys
from typing import Optional

TOOL_NAME = "xojoctl"
TOOL_VERSION = "0.1.0"
SCHEMA_VERSION = 1


def invocation_name(argv0: Optional[str] = None) -> str:
    """Render this program the way the user would have to type it AGAIN.

    Help text is only useful if its examples can be pasted back into the shell,
    and `xojoctl analyze` is a valid command only when something named `xojoctl`
    is on PATH. Run as a plain script -- the normal case on Windows, which has
    no symlink convention to create that name -- every hardcoded example fails
    with "'xojoctl' is not recognized".

    argparse's own default for `prog`, basename(sys.argv[0]), was already right
    about this; passing prog=TOOL_NAME opted out of it. This restores that
    default and adds the interpreter when the basename shows the tool was
    started as a script.

    `python x.py` and `uv run x.py` are INDISTINGUISHABLE here -- both leave the
    script path in argv[0] and nothing marks the launcher -- so `python` is the
    single answer given for both. It runs either way.

    A Windows .cmd shim also forwards to the interpreter, so argv[0] stays the
    .py path and help advertises `python xojoctl.py` to someone who typed
    `xojoctl`. That is accepted: the advertised line is still correct and still
    runs, which is the property that matters.
    """
    raw = argv0 if argv0 is not None else (sys.argv[0] or "")
    base = os.path.basename(raw)
    if not base:
        # Embedded or otherwise argv-less; the canonical name is the best guess.
        return TOOL_NAME
    if base == "-m" or raw.endswith(("/%s/__main__.py" % TOOL_NAME,
                                     "\\%s\\__main__.py" % TOOL_NAME)):
        # Started as `python -m xojoctl`. Python leaves either "-m" or the
        # package's __main__.py in argv[0], and neither is typeable.
        return "python -m " + TOOL_NAME
    if ("/" in raw or os.sep in raw) and os.path.isdir(raw):
        # Started as `python path/to/xojoctl`, the package directory. A bare
        # "xojoctl" is not what the user typed and is not on PATH. The
        # separator requirement keeps an installed `xojoctl` on PATH from
        # matching a same-named directory that happens to sit in the cwd.
        return "python " + base
    if base.lower().endswith(".py"):
        return "python " + base
    if base.lower().endswith(".exe"):
        base = base[:-4]
    return base


# Resolved once, at import: argv[0] does not change during a run.
INVOCATION = invocation_name()

NUL = b"\x00"
HANDSHAKE = b'{"protocol":2}' + NUL
DEFAULT_IPC_NAME = "XojoIDE"

MAX_MESSAGE_BYTES = 16 * 1024 * 1024
RECV_CHUNK = 65536

CONNECT_TIMEOUT = 10.0
CONNECT_RETRY_SECONDS = 20.0   # finding 4: the socket churns; this is normal
CONNECT_RETRY_INTERVAL = 0.5

# Safety ceilings to catch a wedged IDE. They are NOT expected durations, and
# nothing here should be read as "a build takes about this long".
#
# Every timing below was measured on EMPTY projects with few plugins installed.
# Treat them as a FLOOR, not a typical case: a real project with real plugins
# will be substantially slower, and these ceilings are sized for that rather
# than for these numbers.
#   warm, most targets        7-13s   (including Windows and Linux cross-builds)
#   warm, occasional outlier  ~70s    (same targets, same project -- variance
#                                      is real and not explained by the target)
#   first build after a cold IDE      much slower again; an earlier run recorded
#                                     69-123s for targets that later took 8-13s,
#                                     which was cold-cache cost, NOT the target.
# A cold IDE also spends minutes unpacking plugins before answering anything.
#
# The lesson that set these values: a 120s ceiling abandoned builds that were
# still running, and the IDE then returned empty responses to the next few
# commands -- reported as failures that were entirely self-inflicted.
FIRST_REPLY_CEILING = 900.0    # first reply on a connection (cold-start unpack)
REPLY_CEILING = 300.0          # ordinary commands once the IDE is warm
WORK_CEILING = 1800.0          # analyze, build, run: the IDE is doing real work
BUILD_CEILING = WORK_CEILING   # backwards-compatible alias
HINT_AFTER = 20.0

JOURNAL_MAX_MESSAGES = 1024
JOURNAL_MAX_BYTES = 64 * 1024 * 1024

# How close to its claimed reply a same-tag message must land to count as
# trailing output from our own script rather than an unsolicited IDE event.
TRAILING_WINDOW = 2.0

# How long to wait for the REST of a reply the IDE split across messages. The
# observed split -- a script's Print output and a compiler warning arriving as
# two messages under one tag -- was about a millisecond apart, so this only has
# to cover jitter, not an unsolicited event.
SPLIT_REPLY_WINDOW = 0.25

ANALYZE_SENTINEL = "__xojoctl_analyze_complete__"
ANALYZE_ITEM_MISSING = "__xojoctl_item_not_found__"
BUILD_SENTINEL = "__xojoctl_build_complete__"
RELOAD_ITEM_MISSING = "__xojoctl_reload_item_not_found__"
RELOAD_NO_PATH = "__xojoctl_reload_no_path__"

# ReloadProject arrived in Xojo 2026r3. XojoVersion is a Double whose numeric
# order matches the release order -- 2026r2.1 prints as "2026.021" -- so the
# minimum is a float compare, not a string one.
RELOAD_MIN_XOJO_VERSION = 2026.03
RELOAD_MIN_XOJO_NAME = "2026r3"

# Exit codes
EX_OK = 0
EX_PROJECT_ERRORS = 1
EX_CONNECT = 2
EX_TIMEOUT = 3
EX_INCOMPLETE = 4
EX_SCRIPT_ERROR = 5
EX_NO_PROJECT = 6      # connected fine, but no project workspace is open
EX_USAGE = 64
EX_INTERRUPTED = 130    # the shell convention for SIGINT, 128 + 2

IS_WINDOWS = sys.platform == "win32"


class XojoError(Exception):
    """Base for every failure this module raises."""


class TransportUnavailable(XojoError):
    pass


class ProtocolError(XojoError):
    pass


class ReplyTimeout(XojoError):
    pass


class NoProjectOpen(XojoError):
    """No project workspace is open, so there is nothing to act on.

    This MUST be an error, never a quiet success. CheckProjectErrors with
    no project emits nothing, so the analyze sentinel comes back exactly as
    it does for a genuinely clean project -- which would report "no errors,
    no warnings" and exit 0 having checked nothing at all.
    """


# ===========================================================================
# CORE -- import-safe, no argparse, no stdout, no sys.exit below this point
# ===========================================================================


__all__ = [
    "ANALYZE_ITEM_MISSING",
    "ANALYZE_SENTINEL",
    "BUILD_CEILING",
    "BUILD_SENTINEL",
    "CONNECT_RETRY_INTERVAL",
    "CONNECT_RETRY_SECONDS",
    "CONNECT_TIMEOUT",
    "DEFAULT_IPC_NAME",
    "EX_CONNECT",
    "EX_INCOMPLETE",
    "EX_INTERRUPTED",
    "EX_NO_PROJECT",
    "EX_OK",
    "EX_PROJECT_ERRORS",
    "EX_SCRIPT_ERROR",
    "EX_TIMEOUT",
    "EX_USAGE",
    "FIRST_REPLY_CEILING",
    "HANDSHAKE",
    "HINT_AFTER",
    "INVOCATION",
    "IS_WINDOWS",
    "JOURNAL_MAX_BYTES",
    "JOURNAL_MAX_MESSAGES",
    "MAX_MESSAGE_BYTES",
    "NUL",
    "NoProjectOpen",
    "ProtocolError",
    "RECV_CHUNK",
    "RELOAD_ITEM_MISSING",
    "RELOAD_MIN_XOJO_NAME",
    "RELOAD_MIN_XOJO_VERSION",
    "RELOAD_NO_PATH",
    "REPLY_CEILING",
    "ReplyTimeout",
    "SCHEMA_VERSION",
    "SPLIT_REPLY_WINDOW",
    "TOOL_NAME",
    "TOOL_VERSION",
    "TRAILING_WINDOW",
    "TransportUnavailable",
    "WORK_CEILING",
    "XojoError",
    "invocation_name",
]
