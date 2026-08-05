"""Shared help rendering for the command-line scripts in these skills.

argparse parses; this renders: uppercase section headers, two-column content,
dim secondary text, and configurable prompts in examples. The accent
color is Xojo's green:
  #96C84E  used on dark terminals
  #6DB335  used on light terminals

IDENTICAL COPIES -- MAINTAIN TOGETHER. Skills install independently, so they
cannot share one module on disk. The canonical copies live in the xojo-tools
repository at:

    plugins/xojo/skills/xojo/scripts/helptext.py
    plugins/xojo/skills/xojo-lint/scripts/helptext.py
    plugins/xojo/skills/xojo-ide/scripts/xojoctl/helptext.py

Further copies exist in other repositories. Apply every edit to every copy;
xojo-tools' pre-commit hook enforces identity within that repository. Keep
this module generic: anything specific to one CLI belongs in that CLI's own
HelpConfig.
"""

from __future__ import annotations

import argparse
import difflib
import os
import re
import shutil
import sys
import textwrap
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

EX_USAGE = 64

XOJO_GREEN = (150, 200, 78)  # #96C84E
XOJO_GREEN_DEEP = (109, 179, 53)  # #6DB335
DIM_GRAY = (153, 153, 153)  # #999999


class Theme:
    """Color with three levels of graceful degradation.

    truecolor -> 24-bit, the exact Xojo green
    256-color -> the nearest xterm cube entry
    anything else -> plain ANSI green
    no color -> nothing at all
    """

    def __init__(self, enabled: bool) -> None:
        self.on = enabled
        term = os.environ.get("TERM", "")
        self.truecolor = os.environ.get("COLORTERM", "") in ("truecolor", "24bit")
        self.has256 = self.truecolor or "256" in term
        # A light background is announced by COLORFGBG as "fg;bg" with a high bg.
        fgbg = os.environ.get("COLORFGBG", "")
        light = fgbg.endswith(("15", "7"))
        self._green = XOJO_GREEN_DEEP if light else XOJO_GREEN

    def _rgb(
        self,
        rgb: tuple[int, int, int],
        fallback256: int,
        fallback8: str,
        text: str,
        bold: bool = False,
    ) -> str:
        if not self.on:
            return text
        b = "\033[1m" if bold else ""
        if self.truecolor:
            return "%s\033[38;2;%d;%d;%dm%s\033[0m" % (b, rgb[0], rgb[1], rgb[2], text)
        if self.has256:
            return "%s\033[38;5;%dm%s\033[0m" % (b, fallback256, text)
        return "%s%s%s\033[0m" % (b, fallback8, text)

    def accent(self, text: str, bold: bool = True) -> str:
        return self._rgb(self._green, 149, "\033[32m", text, bold)

    def dim(self, text: str) -> str:
        return self._rgb(DIM_GRAY, 245, "\033[2m", text)

    def bold(self, text: str) -> str:
        return "\033[1m%s\033[0m" % text if self.on else text

    def error(self, text: str) -> str:
        return self._rgb((235, 90, 70), 203, "\033[31m", text, bold=True)

    def italic_dim(self, text: str) -> str:
        if not self.on:
            return text
        return "\033[3m%s\033[0m" % self.dim(text)


def help_theme(color_env: str | None = None, stream: Any = None) -> Theme:
    """Help is rendered before flags are parsed, so decide from the environment.

    `color_env` names an optional per-tool variable that forces color on when
    set to "always", e.g. through a pipe. `stream` is the stream the text will
    be written to -- color keys off ITS TTY-ness, so error text bound for
    stderr is not colored just because stdout is a terminal (which put raw
    escape codes in `tool bogus 2>err.log`). Defaults to stdout, where help
    goes.
    """
    if os.environ.get("NO_COLOR"):
        return Theme(False)
    if color_env and os.environ.get(color_env) == "always":
        return Theme(True)
    if stream is None:
        stream = sys.stdout
    return Theme(bool(getattr(stream, "isatty", lambda: False)()))


@dataclass(frozen=True)
class HelpConfig:
    """Presentation text for one command tree.

    Examples are stored without the program name; the renderer prepends
    `prog`, so a pasted line works however the tool is actually started.
    Every command must appear in `command_blurbs` (and in exactly one group
    when `command_groups` is set), so a new command cannot silently vanish
    from help.

    `root_flags` set to None derives the root FLAGS section from the parser;
    an empty sequence suppresses the section. `usage` holds root usage-line
    suffixes rendered after `prog` (a lone string counts as one line, not as
    characters). `prompt` is the shell prompt drawn before `prog` in usage
    and example lines. A subcommand-less CLI leaves `command_blurbs` empty
    -- that drops the COMMANDS section and the per-command trailer -- and
    should override `usage`, whose default advertises subcommands.
    """

    prog: str
    command_blurbs: Mapping[str, str]
    command_groups: Sequence[tuple[str, Sequence[str]]] | None = None
    root_flags: Sequence[tuple[str, str]] | None = None
    root_examples: Sequence[str] = ()
    command_examples: Mapping[str, Sequence[str]] | None = None
    learn_more: Sequence[str] = ()
    color_env: str | None = None
    usage: Sequence[str] = ("<command> [flags]",)
    prompt: str = "%"

    def __post_init__(self) -> None:
        # A lone string satisfies Sequence[str] and would otherwise render
        # one usage line per character.
        if isinstance(self.usage, str):
            object.__setattr__(self, "usage", (self.usage,))


def nonneg_float(value: str) -> float:
    number = float(value)
    if number < 0:
        raise argparse.ArgumentTypeError("must not be negative")
    return number


def nonneg_int(value: str) -> int:
    number = int(value)
    if number < 0:
        raise argparse.ArgumentTypeError("must not be negative")
    return number


def _prose_columns() -> int:
    """Description text caps at 80 columns; long help reads badly at full width."""
    return max(60, min(shutil.get_terminal_size((80, 24)).columns, 80))


def _blurb(th: Theme, text: str) -> str:
    """The leading description: dimmed, wrapped, paragraphs preserved.

    An unbreakable token -- a URL, say -- stays whole on its own line rather
    than being chopped mid-token.
    """
    cols = _prose_columns() - 2
    out = ["\n"]
    for para in (text or "").split("\n"):
        lines = textwrap.wrap(
            para, cols, break_long_words=False, break_on_hyphens=False
        ) or [""]
        for line in lines:
            out.append("  %s\n" % th.dim(line) if line else "\n")
    out.append("\n")
    return "".join(out)


def _section(th: Theme, title: str) -> str:
    return "  %s\n" % th.accent(title)


def _two_col(th: Theme, rows: Sequence[tuple[str, str]], width: int) -> str:
    cols = _prose_columns()
    out = []
    for name, desc in rows:
        wrapped = textwrap.wrap(desc, max(20, cols - width - 6)) or [""]
        out.append("    %s%s\n" % (th.bold(name.ljust(width)), wrapped[0]))
        for cont in wrapped[1:]:
            out.append("    %s%s\n" % (" " * width, cont))
    return "".join(out)


def _rows_section(th: Theme, title: str, rows: Sequence[tuple[str, str]]) -> str:
    # Width is per-section: flags are longer than command names, and sharing
    # one width makes the longer column collide with its descriptions.
    return (
        _section(th, title)
        + _two_col(th, rows, max(len(name) for name, _ in rows) + 4)
        + "\n"
    )


def _cap(text: str) -> str:
    """Capitalize a description, unless its first word is deliberately cased.

    House style capitalizes the first letter of a help string, which turns
    "iOS or macOS target" into "IOS or macOS target". A first word that
    already carries an interior capital chose its own casing -- iOS, macOS,
    eBay -- so leave it.
    """
    first = text.split(" ", 1)[0]
    if any(ch.isupper() for ch in first[1:]):
        return text
    return text[:1].upper() + text[1:]


def _prompt(th: "Theme", config: "HelpConfig") -> str:
    """The shell prompt drawn before `prog`, carrying its trailing space.

    Empty is the obvious spelling for "draw no prompt", so it must take the
    space with it rather than leaving a stray one -- and, with color on, an
    empty escape wrapper.
    """
    return "%s " % th.dim(config.prompt) if config.prompt else ""


def _metavar_str(action: argparse.Action) -> str:
    """The display name for one argument; argparse allows a tuple for nargs > 1."""
    metavar = action.metavar
    if isinstance(metavar, tuple):
        return " ".join(metavar)
    return metavar or action.dest.upper()


def _positionals(parser: argparse.ArgumentParser) -> list[argparse.Action]:
    return [
        a
        for a in parser._actions
        if not a.option_strings
        and not isinstance(a, argparse._SubParsersAction)
        and a.help != argparse.SUPPRESS
    ]


def _arg_rows(parser: argparse.ArgumentParser) -> list[tuple[str, str]]:
    return [
        (_metavar_str(action), _cap((action.help or "").strip()))
        for action in _positionals(parser)
    ]


def _flag_rows(parser: argparse.ArgumentParser) -> list[tuple[str, str]]:
    rows = []
    for action in parser._actions:
        if not action.option_strings or action.help == argparse.SUPPRESS:
            continue
        flag = ", ".join(action.option_strings)
        if action.choices:
            flag += " {%s}" % ",".join(str(c) for c in action.choices)
        elif action.metavar or action.nargs != 0:
            flag += " " + _metavar_str(action)
        rows.append((flag, _cap((action.help or "").strip())))
    return rows


def _usage_lines(th: Theme, config: HelpConfig) -> str:
    return "".join(
        "    %s%s %s\n" % (_prompt(th, config), config.prog, th.dim(usage))
        for usage in config.usage
    )


def render_root_help(
    parser: argparse.ArgumentParser,
    config: HelpConfig,
) -> str:
    th = help_theme(config.color_env)

    buf = [_blurb(th, parser.description or "")]
    if config.usage:
        buf.append(_section(th, "USAGE"))
        buf.append(_usage_lines(th, config))
        buf.append("\n")

    if config.command_groups:
        # One width across all groups, so the columns line up page-wide.
        width = max(len(n) for n in config.command_blurbs) + 4
        for title, group in config.command_groups:
            buf.append(_section(th, title))
            buf.append(
                _two_col(th, [(n, config.command_blurbs[n]) for n in group], width)
            )
            buf.append("\n")
    elif config.command_blurbs:
        buf.append(_rows_section(th, "COMMANDS", list(config.command_blurbs.items())))

    args = _arg_rows(parser)
    if args:
        buf.append(_rows_section(th, "ARGUMENTS", args))

    flags = (
        list(config.root_flags)
        if config.root_flags is not None
        else _flag_rows(parser)
    )
    if flags:
        buf.append(_rows_section(th, "FLAGS", flags))

    if config.root_examples:
        buf.append(_section(th, "EXAMPLES"))
        for example in config.root_examples:
            buf.append(
                "    %s%s %s\n" % (_prompt(th, config), config.prog, example)
            )
        buf.append("\n")

    if config.learn_more:
        for line in config.learn_more:
            buf.append("  %s\n" % th.dim(line))
        buf.append("\n")
    if config.command_blurbs:
        buf.append(
            "  %s\n\n"
            % th.italic_dim(
                "Run '%s <command> --help' for details on a command." % config.prog
            )
        )
    return "".join(buf)


def render_command_help(
    parser: argparse.ArgumentParser,
    name: str,
    config: HelpConfig,
) -> str:
    th = help_theme(config.color_env)
    buf = [_blurb(th, parser.description or config.command_blurbs.get(name, ""))]

    # A readable usage line, rather than argparse's full flag dump.
    shown = []
    for action in _positionals(parser):
        metavar = _metavar_str(action)
        shown.append("[%s]" % metavar if action.nargs in ("?", "*") else metavar)
    buf.append(_section(th, "USAGE"))
    buf.append(
        "    %s%s %s%s %s\n\n"
        % (
            _prompt(th, config),
            config.prog,
            name,
            (" " + " ".join(shown)) if shown else "",
            th.dim("[flags]"),
        )
    )

    args = _arg_rows(parser)
    if args:
        buf.append(_rows_section(th, "ARGUMENTS", args))

    flags = _flag_rows(parser)
    if flags:
        buf.append(_rows_section(th, "FLAGS", flags))

    command_examples = config.command_examples or {}
    if name in command_examples:
        buf.append(_section(th, "EXAMPLES"))
        for example in command_examples[name]:
            buf.append(
                "    %s%s %s\n" % (_prompt(th, config), config.prog, example)
            )
        buf.append("\n")

    return "".join(buf)


# argparse quotes the bad value with %r, which switches to double quotes
# when the value itself contains an apostrophe. The leading group captures
# which argument failed, so a flag's choice error is never mistaken for an
# unknown command.
_INVALID_CHOICE = re.compile(r"argument (\S+): invalid choice: (['\"])(.+?)\2")
_REQUIRED = re.compile(r"the following arguments are required: (.+)")
_UNRECOGNIZED = re.compile(r"unrecognized arguments: (.+)")

# How the subcommand argument is conventionally named; HelpfulParser.error()
# extends these with the parser's actual subparsers dest and metavar.
_COMMAND_LABELS = ("<command>", "command")


def _humanize(
    message: str,
    command_blurbs: Mapping[str, str],
    command_labels: Sequence[str] = _COMMAND_LABELS,
) -> tuple[str, str | None]:
    """Turn argparse's phrasing into something a person wants to read.

    argparse's own invalid-choice text lists every valid name inline; strip
    that and offer a single close match instead. Only errors on an argument
    named in `command_labels` are treated as command errors; a flag with
    choices keeps argparse's own message.
    """
    match = _INVALID_CHOICE.search(message)
    if match and command_blurbs and match.group(1) in command_labels:
        bad = match.group(3)
        close = difflib.get_close_matches(bad, sorted(command_blurbs), n=1, cutoff=0.5)
        return 'unknown command "%s"' % bad, close[0] if close else None
    match = _REQUIRED.search(message)
    if match:
        if command_blurbs and match.group(1).strip() in command_labels:
            return "no command given", None
        return "missing required argument: %s" % match.group(1), None
    match = _UNRECOGNIZED.search(message)
    if match:
        extra = match.group(1)
        plural = "s" if " " in extra.strip() else ""
        return "unrecognized argument%s: %s" % (plural, extra), None
    return message, None


class HelpfulParser(argparse.ArgumentParser):
    """An ArgumentParser whose *errors* look like its help.

    argparse routes errors through format_usage() and a bare `prog: error: ...`
    line, neither of which goes anywhere near a custom format_help().

    Set `help_config` on a subclass before rendering, or override
    `get_help_config()` when the configuration has to be built per call, e.g.
    around a program name that tests rebind. Override `usage_error_extra()`
    to add output -- a JSON document, say -- after the human-readable error
    and before the exit.
    """

    command_name: str | None = None
    help_config: HelpConfig | None = None

    def get_help_config(self) -> HelpConfig:
        if self.help_config is None:
            raise RuntimeError("HelpfulParser.help_config is not set")
        return self.help_config

    def format_help(self) -> str:
        if self.command_name:
            return render_command_help(self, self.command_name, self.get_help_config())
        return render_root_help(self, self.get_help_config())

    def format_usage(self) -> str:
        # Only the error path renders usage, and errors go to stderr.
        config = self.get_help_config()
        th = help_theme(config.color_env, sys.stderr)
        if self.command_name:
            return "    %s%s %s %s\n" % (
                _prompt(th, config),
                config.prog,
                self.command_name,
                th.dim("[flags]"),
            )
        return _usage_lines(th, config)

    def _command_labels(self) -> list[str]:
        """Labels naming this parser's subcommand argument, if it owns one.

        A parser with no subparsers gets NO labels: its errors are about
        ordinary arguments -- even one whose dest happens to be "command" --
        and rewriting those as "unknown command" would discard argparse's
        own choose-from list and offer suggestions drawn from a command
        table the argument has nothing to do with.
        """
        labels: list[str] = []
        for action in self._actions:
            if isinstance(action, argparse._SubParsersAction):
                labels.extend(_COMMAND_LABELS)
                labels.extend(
                    label
                    for label in (action.dest, action.metavar)
                    if label and label != argparse.SUPPRESS
                )
        return labels

    def usage_error_extra(self, text: str, suggestion: str | None, hint: str) -> None:
        """Hook for subclasses; called just before a usage error exits."""

    def error(self, message: str) -> Any:
        config = self.get_help_config()
        err = sys.stderr
        th = help_theme(config.color_env, err)
        text, suggestion = _humanize(
            message, config.command_blurbs, self._command_labels()
        )
        print("\n  %s %s\n" % (th.error("error:"), text), file=err)
        if suggestion:
            print("  Did you mean %s?\n" % th.bold(suggestion), file=err)
        usage = self.format_usage()
        if usage:
            print(_section(th, "USAGE"), file=err, end="")
            print(usage, file=err, end="")
        hint = (
            "%s %s --help" % (config.prog, self.command_name)
            if self.command_name
            else "%s --help" % config.prog
        )
        print("\n  Run %s for details.\n" % th.bold(hint), file=err)
        self.usage_error_extra(text, suggestion, hint)
        sys.exit(EX_USAGE)
