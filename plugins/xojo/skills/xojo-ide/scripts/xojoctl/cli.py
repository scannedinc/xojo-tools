"""argparse."""

from __future__ import annotations

import argparse
import json
import os
import sys
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
from .diagnostics import *  # noqa: F401,F403
from .render import *  # noqa: F401,F403
from .connection import *  # noqa: F401,F403
from .commands import *  # noqa: F401,F403


from .helptext import (
    DIM_GRAY,
    HelpConfig,
    HelpfulParser as _SharedHelpfulParser,
    Theme,
    XOJO_GREEN,
    XOJO_GREEN_DEEP,
    _humanize,
    help_theme as _shared_help_theme,
    render_command_help as _shared_render_command_help,
    render_root_help as _shared_render_root_help,
)


COLOR_ENV = "XOJOCTL_COLOR"


def help_theme() -> Theme:
    """Decide color from the environment; XOJOCTL_COLOR=always forces it on."""
    return _shared_help_theme(COLOR_ENV)


# Command grouping. Every subcommand must appear in exactly one group -- the
# test suite asserts it, so a new command cannot silently vanish from help.
COMMAND_GROUPS: Tuple[Tuple[str, Tuple[str, ...]], ...] = (
    ("PROJECT COMMANDS", ("analyze", "build", "run", "stop")),
    ("PROJECT STATE", ("open", "save", "close", "reload")),
    ("INSPECTION", ("status", "projects", "version", "targets")),
    ("ADVANCED", ("script", "capture")),
)

COMMAND_BLURBS = {
    "analyze": "Run Analyze Project; report errors and warnings",
    "build": "Build the open project for one or more targets",
    "run": "Run the open project in the IDE debugger",
    "stop": "Stop the running project",
    "open": "Open a project in the IDE",
    "save": "Save the front project (no prompt)",
    "close": "Close the front project",
    "reload": "Reload the front project from disk (Xojo 2026r3+)",
    "status": "Check that the IDE is reachable and speaking v2",
    "projects": "List open workspaces and which one is frontmost",
    "version": "Report the running IDE's version",
    "targets": "List BuildApp target constants (offline)",
    "script": "Send arbitrary IDE Script",
    "capture": "Log every protocol message (debugging)",
}

# Examples are stored WITHOUT the program name; the renderer prepends
# INVOCATION so a pasted line works however the tool was actually started.
ROOT_EXAMPLES = (
    "analyze",
    "analyze --json | jq '.diagnostics[]'",
    "build --target darwin-arm64 --target darwin-universal",
    "script 'Print Str(XojoVersion)'",
)

COMMAND_EXAMPLES = {
    "analyze": ("analyze",
                "analyze --json | jq '.counts'",
                "analyze --severity errors -W"),
    "build": ("build --target darwin-arm64",
              "build -t 9 -t 24 --stop-on-error"),
    "script": ("script 'Print Str(6*7)'",
               "script --file build.xojo_script"),
    "targets": ("targets --host", "targets darwin"),
    "open": ('open ~/Projects/MyApp.xojo_project',),
    "projects": ("projects", "projects --select 'Desktop App'"),
    "save": ("save",),
    "close": ("close --save", "close --discard"),
    "reload": ("reload --discard", "reload --item Window1 --discard"),
    "capture": ("capture --seconds 60 --json > capture.json",),
}

ROOT_FLAGS = (
    ("--json", "Emit one JSON document on stdout"),
    ("-W", "Treat warnings as errors (analyze, build, run, script)"),
    ("-q, --quiet", "Suppress progress and advisory notes"),
    ("--timeout SEC", "Safety ceiling for the first reply (default %d)"
     % FIRST_REPLY_CEILING),
    ("-h, --help", "Show help for a command"),
    ("--version", "Show xojoctl's own version"),
)


def help_config() -> HelpConfig:
    """Built per call, not at import: the test suite rebinds INVOCATION."""
    return HelpConfig(
        prog=INVOCATION,
        command_blurbs=COMMAND_BLURBS,
        command_groups=COMMAND_GROUPS,
        root_flags=ROOT_FLAGS,
        root_examples=ROOT_EXAMPLES,
        command_examples=COMMAND_EXAMPLES,
        learn_more=(
            "The Xojo IDE must already be running; %s only connects to it."
            % TOOL_NAME,
        ),
        color_env=COLOR_ENV,
    )


def render_root_help(parser: argparse.ArgumentParser) -> str:
    return _shared_render_root_help(parser, help_config())


def render_command_help(parser: argparse.ArgumentParser, name: str) -> str:
    return _shared_render_command_help(parser, name, help_config())


def _humanize_argparse_error(message: str) -> Tuple[str, Optional[str]]:
    return _humanize(message, COMMAND_BLURBS)


_CLI_ARGV: Optional[List[str]] = None   # what main() is parsing; error() sniffs it


def _wants_json() -> bool:
    """Was --json among the arguments being parsed?

    Asked from parser.error(), where parsing FAILED -- there is no Namespace
    to consult, so the raw argv is the only available signal. argparse accepts
    unambiguous long-option abbreviations, so a consumer that spelled --jso
    gets JSON on a successful parse and must get JSON on a usage error too;
    no other option here starts with --j.
    """
    argv = _CLI_ARGV if _CLI_ARGV is not None else sys.argv[1:]
    return any(a in ("--j", "--js", "--jso", "--json") for a in argv)


def _stdout_to_devnull() -> None:
    """Point the real stdout at devnull after a BrokenPipeError.

    Without this, the JSON that failed to flush is still sitting in the
    buffer at interpreter shutdown; CPython's final flush hits the dead pipe,
    prints "Exception ignored" noise, and overrides the exit status to 120.
    """
    try:
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
    except OSError:
        pass


class HelpfulParser(_SharedHelpfulParser):
    """The shared help style, plus xojoctl's one-JSON-document contract.

    Without this, `xojoctl` with no arguments dumps every subcommand name --
    exactly the wart the custom renderer exists to remove.
    """

    def get_help_config(self) -> HelpConfig:
        return help_config()

    def usage_error_extra(self, text: str, suggestion: Optional[str],
                          hint: str) -> None:
        if not _wants_json():
            return
        # README promises exactly one JSON document on stdout -- always.
        # argparse-level failures used to bypass the Result machinery and
        # emit zero bytes, which a jq consumer reads as empty success.
        res = Result(command=self.command_name or "usage")
        res.ok, res.outcome, res.exit_code = False, "usage_error", EX_USAGE
        res.summary = text
        remedy = ["Run %s for details." % hint]
        if suggestion:
            remedy.insert(0, "Did you mean %r?" % suggestion)
        res.error = {"code": "usage_error", "message": text,
                     "remedy": remedy}
        try:
            json.dump(res.to_json(), sys.stdout, indent=2)
            sys.stdout.write("\n")
            sys.stdout.flush()
        except BrokenPipeError:
            _stdout_to_devnull()


# Any real ceiling is minutes; ~11.6 days is the cap. Merely-finite is not
# enough: settimeout() and Condition.wait() raise the same OverflowError as
# 'inf' once a value passes the platform timestamp range (~4.3e6s on Windows).
_SECONDS_MAX = 10 ** 6


def _seconds_arg(raw: str) -> float:
    """Duration flags: nonnegative, finite, and within the platform's range.

    Bare type=float accepts 'nan' (every nan comparison is False, so the
    wait loop spins at full CPU with no ceiling ever firing) and 'inf'
    (settimeout and Condition.wait raise an uncaught OverflowError) -- and
    a large-enough finite value overflows exactly like 'inf'. Zero stays
    legal: it means expire immediately. ArgumentTypeError routes through
    HelpfulParser.error(), which honors the one-JSON-document contract and
    exits 64.
    """
    try:
        value = float(raw)
    except ValueError:
        raise argparse.ArgumentTypeError("%r is not a number of seconds" % raw)
    if not 0 <= value <= _SECONDS_MAX:     # False for nan, on purpose
        raise argparse.ArgumentTypeError(
            "%r is not a number of seconds between 0 and %d"
            % (raw, _SECONDS_MAX))
    return value


def _port_arg(raw: str) -> int:
    # Mirrors port_from_env: socket.connect raises OverflowError, not
    # OSError, for an out-of-range port, which no handler ladder catches.
    try:
        port = int(raw)
    except ValueError:
        raise argparse.ArgumentTypeError("%r is not a valid port number" % raw)
    if not 1 <= port <= 65535:
        raise argparse.ArgumentTypeError(
            "%r is outside the valid port range 1-65535" % raw)
    return port


def build_parser() -> argparse.ArgumentParser:
    conn = HelpfulParser(add_help=False)
    if not IS_WINDOWS:
        # POSIX only: these resolve or guard a socket FILE. Windows has none --
        # the IDE listens on a discovered loopback port -- so registering them
        # there would put flags in --help that cannot do anything.
        conn.add_argument("--ipc-name", "--path", dest="ipc_name",
                          default=os.environ.get("XOJOCTL_IPC_NAME"),
                          help="IPC name the IDE was launched with (default "
                               "XojoIDE), matching XOJO_IPCPATH")
        conn.add_argument("--trust-foreign-socket", action="store_true",
                          help="connect even if the socket is owned by another user")
    conn.add_argument("--port", type=_port_arg, default=None,
                      help="Windows: loopback TCP port; skips discovery "
                           "(defaults to XOJOCTL_PORT if set)")
    conn.add_argument("--connect-timeout", type=_seconds_arg, default=CONNECT_TIMEOUT,
                      metavar="SEC",
                      help="socket connect timeout (default %d)" % CONNECT_TIMEOUT)
    conn.add_argument("--timeout", type=_seconds_arg, default=FIRST_REPLY_CEILING,
                      metavar="SEC",
                      help="safety ceiling for the first reply, and the whole "
                           "budget for Windows port discovery (default %d); "
                           "a cold IDE unpacks plugins before answering"
                           % FIRST_REPLY_CEILING)
    conn.add_argument("--warm-timeout", type=_seconds_arg, default=REPLY_CEILING,
                      metavar="SEC",
                      help="ceiling once the IDE has replied (default %d)"
                           % REPLY_CEILING)

    out = HelpfulParser(add_help=False)
    out.add_argument("--json", action="store_true",
                     help="emit one JSON document on stdout")
    out.add_argument("--no-raw", action="store_true",
                     help="omit the raw protocol log from JSON output")
    out.add_argument("--color", choices=("auto", "always", "never"), default="auto",
                     help="when to colorize output (default auto)")
    out.add_argument("-q", "--quiet", action="store_true",
                     help="suppress progress and advisory notes on stderr")

    pol = HelpfulParser(add_help=False)
    pol.add_argument("-W", "--warnings-as-errors", action="store_true",
                     help="exit 1 when there are warnings but no errors")

    p = HelpfulParser(
        prog=INVOCATION,
        description="Drive a running Xojo IDE: analyze, build, and read back "
                    "errors and warnings.")
    p.add_argument("--version", action="version",
                   version="%s %s" % (TOOL_NAME, TOOL_VERSION))
    sub = p.add_subparsers(dest="command", required=True,
                           parser_class=HelpfulParser)

    s = sub.add_parser("status", parents=[conn, out],
                       help="verify the IDE is reachable and speaking v2")
    s.set_defaults(func=cmd_status)

    s = sub.add_parser("analyze", parents=[conn, out, pol],

                       help="run Analyze Project and report errors and warnings")
    s.add_argument("--item", help="analyze one project item instead of the project")
    s.add_argument("--severity", choices=("all", "errors", "warnings"), default="all",
                   help="display filter only; the exit code always uses the full set")
    s.add_argument("--analyze-timeout", type=_seconds_arg, default=WORK_CEILING,
                   metavar="SEC",
                   help="ceiling for the analysis itself (default %d); a large "
                        "project takes far longer than a small one"
                        % WORK_CEILING)
    s.set_defaults(func=cmd_analyze)

    s = sub.add_parser("build", parents=[conn, out, pol],
                       help="build the open project for one or more targets")
    s.add_argument("-t", "--target", action="append", required=True,
                   help="repeatable; an integer or a name such as darwin-arm64")
    s.add_argument("--reveal", action="store_true",
                   help="open the output folder in the file manager")
    s.add_argument("--stop-on-error", action="store_true",
                   help="stop after the first failing target")
    s.add_argument("--build-timeout", type=_seconds_arg, default=BUILD_CEILING,
                   metavar="SEC",
                   help="ceiling for one build (default %d). Deliberately "
                        "generous: measurements come from empty projects, and a "
                        "real one takes far longer. Too low a value abandons a "
                        "running build and leaves the IDE busy" % BUILD_CEILING)
    s.set_defaults(func=cmd_build)

    s = sub.add_parser(
        "script", parents=[conn, out, pol],
        help="send arbitrary IDE Script",
        description="Runs an IDE Script. To run the PROJECT in the debugger, "
                    "use '%s run'." % INVOCATION)
    g = s.add_mutually_exclusive_group(required=True)
    g.add_argument("source", nargs="?", help="IDE Script text")
    g.add_argument("-f", "--file", help="read the script from a file")
    g.add_argument("--stdin", action="store_true", help="read the script from stdin")
    s.set_defaults(func=cmd_script)

    s = sub.add_parser("targets", parents=[out],
                       help="list BuildApp target constants (offline)",
                       description="List BuildApp target constants (offline). "
                                   "The values are transcribed from Xojo's "
                                   "documented BuildApp table:\n"
                                   "https://documentation.xojo.com/topics/"
                                   "build_automation/ide_scripting/"
                                   "building_commands.html")
    s.add_argument("query", nargs="?", help="filter by number, name, or platform")
    s.add_argument("--host", action="store_true", help="only targets for this host")
    s.add_argument("--sort", choices=("platform", "value", "name"),
                   default="platform",
                   help="sort order (default platform: macOS, Windows, Linux, iOS, Android, Web; then Intel before ARM, single-arch before Universal, 32 before 64, real before simulator)")
    s.set_defaults(func=cmd_targets)

    s = sub.add_parser("version", parents=[conn, out],
                       help="report the running IDE's version")
    s.set_defaults(func=cmd_version)

    s = sub.add_parser(
        "run", parents=[conn, out, pol],
        help="run the open project in the IDE debugger",
        description="Runs the open PROJECT in the IDE debugger. To send an IDE "
                    "Script, use '%s script'." % INVOCATION)
    s.set_defaults(func=cmd_run)

    s = sub.add_parser("stop", parents=[conn, out],
                       help="stop the running project")
    s.set_defaults(func=cmd_stop)

    s = sub.add_parser("capture", parents=[conn, out],
                       help="log every protocol message (debugging)")
    s.add_argument("--seconds", type=_seconds_arg, default=60.0,
                   help="how long to keep capturing (default 60)")
    s.add_argument("--script", help="optional IDE Script to send first")
    s.set_defaults(func=cmd_capture)

    s = sub.add_parser("open", parents=[conn, out],
                       help="open a project in the IDE")
    s.add_argument("project", help="path to the .xojo_project")
    s.set_defaults(func=cmd_open)

    s = sub.add_parser("projects", parents=[conn, out],

                       help="list open workspaces and which one is frontmost",
                       description="Xojo is single-instance and commands act on "
                                   "the frontmost workspace. This shows which "
                                   "that is, and can change it.")
    s.add_argument("--select", metavar="TITLE|INDEX",
                   help="bring a workspace to the front before listing")
    s.set_defaults(func=cmd_projects)

    s = sub.add_parser("save", parents=[conn, out],
                       help="save the front project",
                       description="Saves the front project with no prompt.")
    s.set_defaults(func=cmd_save)

    s = sub.add_parser(
        "close", parents=[conn, out],
        help="close the front project",
        description="Xojo's CloseProject takes a PROMPT flag, not a save flag, "
                    "and prompting would park a modal dialog in front of nobody. "
                    "xojoctl therefore never prompts: --save runs SaveFile first, "
                    "and --discard closes and loses changes -- typing --discard "
                    "IS the confirmation.")
    g = s.add_mutually_exclusive_group(required=True)
    g.add_argument("--save", action="store_true",
                   help="save the project, then close it")
    g.add_argument("--discard", action="store_true",
                   help="discard unsaved changes and close")
    s.set_defaults(func=cmd_close)

    s = sub.add_parser(
        "reload", parents=[conn, out],
        help="reload the front project from disk (Xojo 2026r3+)",
        description="Runs Reload Project, which needs Xojo 2026r3 or later "
                    "(the release that renamed Revert to Saved). It re-reads "
                    "the front project from disk, discarding unsaved IDE "
                    "changes without prompting, so it requires --discard, "
                    "exactly like a discarding close. On an older IDE %s "
                    "refuses and names the close/open pair to use "
                    "instead." % INVOCATION)
    s.add_argument("--item", metavar="NAME",
                   help="reload one project item instead of the whole project")
    s.add_argument("--discard", action="store_true",
                   help="discard unsaved changes and reload")
    s.set_defaults(func=cmd_reload)

    for canonical, sp in _subparsers(sub).items():
        sp.command_name = canonical
    return p


def _subparsers(sub: Any) -> Dict[str, argparse.ArgumentParser]:
    """Map canonical command name -> its parser, skipping alias duplicates."""
    seen: Dict[int, str] = {}
    out: Dict[str, argparse.ArgumentParser] = {}
    for name, sp in sub.choices.items():
        if id(sp) in seen:
            continue          # an alias pointing at a parser we already have
        if name in COMMAND_BLURBS:
            seen[id(sp)] = name
            out[name] = sp
    return out


def main(argv: Optional[List[str]] = None) -> int:
    global _CLI_ARGV
    _CLI_ARGV = list(argv) if argv is not None else list(sys.argv[1:])
    parser = build_parser()
    # A bare invocation is a request to see what the tool does, not an error.
    if not _CLI_ARGV:
        sys.stdout.write(parser.format_help())
        return EX_OK
    args = parser.parse_args(argv)

    # Every subcommand is registered under exactly one name, so the parsed
    # command IS the canonical one.
    res = Result(command=args.command)
    stdout, stderr = sys.stdout, sys.stderr
    st = Style(want_color(args.color, stderr if args.json else stdout))

    try:
        args.func(args, res)
    except TransportUnavailable as exc:
        res.ok, res.outcome, res.exit_code = False, "connection_failed", EX_CONNECT
        res.summary = "could not connect to the Xojo IDE"
        res.error = {"code": "connection_failed", "message": str(exc),
                     "remedy": _connect_remedy()}
    except NoProjectOpen as exc:
        res.ok, res.outcome, res.exit_code = False, "no_project_open", EX_NO_PROJECT
        res.summary = "no project is open in the Xojo IDE"
        res.error = {"code": "no_project_open", "message": str(exc),
                     "remedy": ["Open a project: %s open <path>.xojo_project"
                                % INVOCATION,
                                "Or open it in the IDE by hand, then retry."]}
    except ReplyTimeout as exc:
        res.ok, res.outcome, res.exit_code = False, "timeout", EX_TIMEOUT
        res.summary = "timed out waiting for the IDE"
        res.error = {"code": "timeout", "message": str(exc),
                     "remedy": ["End the script with a Print -- the IDE replies "
                                "only when a script produces output.",
                                "Raise --timeout if the IDE was cold.",
                                "For analyze/build raise --analyze-timeout/"
                                "--build-timeout; cross-compiling to Windows or "
                                "Linux is slow. (run compiles under a fixed "
                                "%.0fs ceiling.)" % WORK_CEILING]}
    except ProtocolError as exc:
        # The peer answered, but not in a way this protocol allows -- treat it
        # like a connection problem, NOT a usage error: nothing about the
        # command line caused it, and a retry wrapper keyed on 2 should fire.
        res.ok, res.outcome, res.exit_code = False, "protocol_error", EX_CONNECT
        res.summary = "the connection to the Xojo IDE failed"
        res.error = {"code": "protocol_error", "message": str(exc),
                     "remedy": ["Check that the endpoint really is a Xojo IDE, "
                                "then retry."]}
    except ConnectionError as exc:
        # The IDE went away mid-exchange (quit, crashed, dropped the socket).
        # Same story: a transient transport death is exit 2, not 64.
        res.ok, res.outcome, res.exit_code = False, "connection_lost", EX_CONNECT
        res.summary = "lost the connection to the Xojo IDE"
        res.error = {"code": "connection_lost", "message": str(exc),
                     "remedy": ["Check whether the IDE is still running, "
                                "then retry."]}
    except KeyboardInterrupt:
        # Ctrl-C is an EXPECTED escape here: the first-reply ceiling is 900s
        # and a hint is printed at 20s inviting the wait. Letting it through
        # would print a traceback and zero bytes of stdout, which a --json
        # consumer reads as empty success.
        res.ok, res.outcome, res.exit_code = False, "interrupted", EX_INTERRUPTED
        res.summary = "interrupted"
        res.error = {"code": "interrupted",
                     "message": "interrupted before the command finished; "
                                "the IDE may still be working on it",
                     "remedy": ["Check the IDE before retrying: a build or "
                                "analysis it already started keeps running."]}
    except (XojoError, ValueError, OSError) as exc:
        res.ok, res.outcome, res.exit_code = False, "failed", EX_USAGE
        res.summary = "command failed"
        res.error = {"code": "failed", "message": str(exc), "remedy": []}

    try:
        if args.json:
            json.dump(res.to_json(include_raw=not args.no_raw), stdout, indent=2)
            stdout.write("\n")
            stdout.flush()      # keep notes after output when both are a tty
            render_notes(res, st, stderr, args.quiet)
        else:
            if res.error:
                render_error(res, st, stdout)
            elif res.command == "targets":
                render_targets(res, st, stdout)
            elif res.command == "projects":
                render_projects(res, st, stdout)
            else:
                render_human(res, st, stdout)
            stdout.flush()      # keep notes after output when both are a tty
            render_notes(res, st, stderr, args.quiet)
    except BrokenPipeError:
        # Downstream closed the pipe early (`... --json | head`, jq bailing).
        # That is the CONSUMER's choice, not a failure of this command, so
        # the computed exit code stands.
        _stdout_to_devnull()
    return res.exit_code


if __name__ == "__main__":
    sys.exit(main())


__all__ = [
    "COLOR_ENV",
    "COMMAND_BLURBS",
    "COMMAND_EXAMPLES",
    "COMMAND_GROUPS",
    "DIM_GRAY",
    "HelpConfig",
    "HelpfulParser",
    "ROOT_EXAMPLES",
    "ROOT_FLAGS",
    "Theme",
    "XOJO_GREEN",
    "XOJO_GREEN_DEEP",
    "_CLI_ARGV",
    "_SECONDS_MAX",
    "_humanize_argparse_error",
    "_port_arg",
    "_seconds_arg",
    "_stdout_to_devnull",
    "_subparsers",
    "_wants_json",
    "build_parser",
    "help_config",
    "help_theme",
    "main",
    "render_command_help",
    "render_root_help",
]
