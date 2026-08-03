"""A one-line progress bar, redrawn in place on a terminal.

The slow stages of `sync` and `build` are long and quiet -- a large archive
download, thousands of page requests or conversions -- and a bare counter
does not show how fast any of them is moving. This draws a bar instead:

    Pages [ 78%] [███████████████████████████▎       ] 1670/2141

Off a terminal there is nothing to redraw, and an agent running this through
a pipe does not want thousands of lines of bar, so the same update() call
falls back to one terse line every few percent.
"""

from __future__ import annotations

import shutil
import sys

from helptext import help_theme

# The docs.py CLI's variable to force color on through a pipe; the bar keeps
# honoring it because bar and help are styled by the same theme.
COLOR_ENV = "XOJO_DOCS_COLOR"

# Eighth-width blocks, so the bar advances smoothly instead of a whole cell at
# a time. Index n is n eighths of a cell filled; index 8 is a full cell.
BLOCKS = " ▏▎▍▌▋▊▉█"
# Under LC_ALL=C none of those can be encoded, so a cell is all or nothing.
BLOCKS_ASCII = " " * 8 + "#"

# Below MIN_BAR the bar says less than the number does, so it is dropped.
# MAX_BAR keeps the whole line -- label, percent, bar, counts -- under 70
# columns for every stage, so it survives a narrow terminal and pastes into
# documentation without wrapping.
MIN_BAR = 8
MAX_BAR = 35

MB = 1024 * 1024


def megabytes(received: int, total: int) -> str:
    """A "143/183 MB" suffix, or just "143 MB" when the size is unknown."""
    if total > 0:
        return f"{received / MB:.0f}/{total / MB:.0f} MB"
    return f"{received / MB:.0f} MB"


def _encodable(stream, text: str) -> bool:
    try:
        text.encode(getattr(stream, "encoding", None) or "utf-8")
    except (LookupError, UnicodeEncodeError):
        return False
    return True


class Progress:
    """Progress for one stage of work, as a context manager.

    The bar owns the last line of output for as long as it is drawn, so
    anything else that wants to print during that stage has to go through
    log() -- otherwise its line lands on top of the bar and both are lost.
    """

    def __init__(
        self,
        label: str,
        total: int,
        stream=None,
        indent: str = "  ",
        step: int = 5,
    ):
        self.label = label
        self.total = max(0, int(total))
        self.stream = stream or sys.stdout
        self.indent = indent
        # Percent granularity of the non-terminal fallback. Coarse on purpose:
        # an agent reading this through a pipe wants a handful of lines, not a
        # hundred.
        self.step = max(1, step)
        self.theme = help_theme(COLOR_ENV)
        self.tty = bool(getattr(self.stream, "isatty", lambda: False)())
        self.blocks = BLOCKS if _encodable(self.stream, BLOCKS) else BLOCKS_ASCII
        self.current = 0
        self.suffix = ""
        # Width of the bar currently on screen, 0 when the line is clear.
        self._drawn = 0
        self._last: str | None = None
        self._plain_key = None

    def __enter__(self) -> "Progress":
        return self

    def __exit__(self, *exc) -> bool:
        self.clear()
        return False

    # ------------------------------------------------------------------

    def percent(self) -> int | None:
        """0-100, or None when the total is not known.

        Clamped, because a gzipped response reports a compressed
        Content-Length while iter_content yields the decoded bytes.
        """
        if not self.total:
            return None
        return min(100, max(0, self.current * 100 // self.total))

    def update(self, current: int, suffix: str = "", total: int | None = None) -> None:
        """Advance to `current`. `total` may arrive late, e.g. Content-Length."""
        if total is not None:
            self.total = max(0, int(total))
        self.current = max(0, int(current))
        self.suffix = suffix
        if self.tty:
            self._draw()
        else:
            self._print_plain()

    def log(self, message: str, stream=None) -> None:
        """Print a line without leaving the bar smeared across it."""
        self.clear()
        print(message, file=stream or self.stream, flush=True)
        if self.tty and self._last is not None:
            self._draw()

    def clear(self) -> None:
        """Give the line back. Spaces rather than an erase escape, so this is
        also correct on a terminal that understands nothing else."""
        if self._drawn:
            self.stream.write("\r" + " " * self._drawn + "\r")
            self.stream.flush()
            self._drawn = 0

    # ------------------------------------------------------------------

    def _draw(self) -> None:
        plain, styled = self._line()
        if plain == self._last and self._drawn:
            return
        # Pad over whatever the previous, possibly longer, line left behind.
        pad = " " * max(0, self._drawn - len(plain))
        self.stream.write("\r" + styled + pad)
        self.stream.flush()
        self._last = plain
        self._drawn = len(plain)

    def _print_plain(self) -> None:
        percent = self.percent()
        key = self.suffix if percent is None else percent - percent % self.step
        if key == self._plain_key:
            return
        self._plain_key = key
        text = f"{self.indent}{self.label}"
        if percent is not None:
            text += f" {percent}%"
        if self.suffix:
            text += f" {self.suffix}"
        print(text, file=self.stream, flush=True)

    def _line(self) -> tuple[str, str]:
        """The bar as (plain, styled). All width maths uses `plain`, because
        the styled form carries escape bytes that occupy no columns."""
        th = self.theme
        percent = self.percent()
        # Read the width every time, so a mid-run resize is picked up. One
        # column is left spare: a line that reaches the edge wraps, and then
        # the carriage return no longer lands on the bar's own line.
        columns = shutil.get_terminal_size((100, 24)).columns

        if percent is None:
            plain = f"{self.indent}{self.label} {self.suffix}".rstrip()[: columns - 1]
            return plain, th.dim(plain)

        head = f"{self.indent}{self.label} [{percent:3d}%] ["
        tail = "]" + (f" {self.suffix}" if self.suffix else "")
        width = min(MAX_BAR, columns - 1 - len(head) - len(tail))
        if width < MIN_BAR:
            plain = f"{self.indent}{self.label} {percent}% {self.suffix}".rstrip()
            plain = plain[: max(0, columns - 1)]
            return plain, plain

        eighths = min(self.current * width * 8 // self.total, width * 8)
        whole, part = divmod(eighths, 8)
        filled = self.blocks[8] * whole
        if whole < width and part:
            filled += self.blocks[part]
        empty = " " * (width - len(filled))

        plain = head + filled + empty + tail
        styled = "".join(
            [
                f"{self.indent}{self.label} ",
                th.dim(f"[{percent:3d}%]"),
                " ",
                th.dim("["),
                th.accent(filled, bold=False),
                empty,
                th.dim("]"),
                th.dim(f" {self.suffix}") if self.suffix else "",
            ]
        )
        return plain, styled
