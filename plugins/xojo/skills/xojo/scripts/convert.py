"""Convert the mirrored Xojo reStructuredText into agent-readable Markdown.

The Xojo docs are generated from a very regular template, which is what makes
this practical. Every API page looks like:

    Class

    ================
    DesktopTextField
    ================

    Description
    -----------
    ...

    Properties          <- summary table, one row per member
    ----------
    .. csv-table::
       :header: "Name", "Type", "Read-Only", "Shared"

       :ref:`Active<desktoptextfield.active>`, :doc:`Boolean</api/...>`, ,

    Property descriptions   <- one block per member, each with an anchor
    ---------------------
    .. _desktoptextfield.active:

    ----

    .. rst-class:: forsearch

    DesktopTextField.Active

    **Active** As :doc:`Boolean</api/data_types/boolean>`

        Indicates whether the control is active.

Each page becomes two Markdown files: a small one with the prose and the summary
tables, and a large one with the per-member detail. An agent reads the small one
to learn what a class offers and only opens the large one for a specific member.
"""

from __future__ import annotations

import csv
import io
import posixpath
import re
import urllib.parse
import zlib
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

# --------------------------------------------------------------------------
# reStructuredText lexing
# --------------------------------------------------------------------------

DIRECTIVE = re.compile(r"^(\s*)\.\.\s+([A-Za-z][A-Za-z0-9_-]*)::\s*(.*)$")
ANCHOR = re.compile(r"^\s*\.\.\s+_([^:]+):\s*$")
COMMENT = re.compile(r"^(\s*)\.\.(\s|$)")
OPTION = re.compile(r"^\s*:([a-zA-Z][a-zA-Z0-9_-]*):\s*(.*)$")
PUNCT_LINE = re.compile(r'^([-=~^"#*+`\'_:.])\1{2,}\s*$')
ROLE = re.compile(r":([a-z][a-z-]*):`([^`]*)`")
TARGETED = re.compile(r"^(.*?)\s*<([^<>]*)>$", re.DOTALL)
LITERAL = re.compile(r"``([^`]+)``")
# reStructuredText hyperlink: `Text <target>`_ (or `_ _` for anonymous).
RST_LINK = re.compile(r"`([^`]+?)\s*<([^<>]+)>`__?")
SUBSTITUTION = re.compile(r"\|(beginnosearch|endnosearch)\|")
# reStructuredText auto-numbered list item: "#." means "next number".
AUTO_ENUM = re.compile(r"^(\s*)#\.(\s+)(.*)$")
LIST_ITEM = re.compile(r"^\s*([*+-]|\d+\.|#\.)\s")
EXPLICIT_ENUM = re.compile(r"^\s*(\d+)\.\s")
# How the docs word a deprecation. Three shapes occur:
#   "This item was deprecated in version 2021r3. Please use X as a replacement."
#   "This item was deprecated in version 2019r2. There is no replacement."
#   "This item was deprecated."
DEPRECATION = re.compile(r"(?:was|is|has been) deprecated", re.I)
DEPRECATED_VERSION = re.compile(
    r"(?:was|is|has been) (?:deprecated|removed)(?: in)?(?: version| Xojo)?\s+([0-9][0-9r.]*?)\.?(?:\s|$)"
)
# The replacement comes from the deprecation notice and only from it: the
# "Please use"/"Use" must follow the notice wording ("was/is/has been
# deprecated") inside the same paragraph, or ordinary "Use this event to
# ..." advice in a member body would be harvested as a replacement. The
# verb is required so the bare word deprecated inside a :doc: role target
# path (</api/deprecated/date>) cannot anchor a harvest. The capture then ends at the notice's
# own wording ("as a replacement", "in place of", "instead") or, when a
# notice omits all three, at the end of the sentence or paragraph. Without
# that stop the lazy match runs on until the next "as a replacement"
# anywhere in the page and swallows whole sentences.
DEPRECATED_REPLACEMENT = re.compile(
    r"(?:was|is|has been) (?:deprecated|removed)\b"
    r"(?:(?!\n[ \t]*\n).){0,120}?(?:Please use|Use)\s+(.+?)"
    r"(?:\s+(?:as a replacement|in place of|instead\b)|(?=\.(?:\s|$))|\s*(?=\n[ \t]*\n))",
    re.S,
)
ROLE_TEXT = re.compile(r":[a-z-]+:`([^`<]*?)\s*(?:<[^`>]*>)?`")
# Half-converted MediaWiki markup that survives in a few upstream notices:
# "]]" link closers, "}}" template closers, "<ShowIf" conditional tags, and
# the literal "(above)"/"(below)" page-position references. Anything from the
# first such token on is junk, never part of the replacement name.
WIKI_LEFTOVER = re.compile(r"\s*(?:\]\]|\}+|<ShowIf|\(above\)|\(below\))")


def deprecation(text: str) -> tuple[str, str]:
    """(version, replacement) from a deprecation notice; blanks when absent."""
    version = DEPRECATED_VERSION.search(text)
    replacement = DEPRECATED_REPLACEMENT.search(text)
    name = ""
    if replacement:
        # The replacement is usually a :doc:/:ref: role; keep the display text.
        name = " ".join(ROLE_TEXT.sub(r"\1", replacement.group(1)).split())
        name = name.strip("`* ")
        # A malformed role (missing the "<" before its target) leaks the
        # target path into the display text: "System.Version/api/ios/...>".
        name = re.sub(r"/(?:api|doc)/\S*$", "", name.rstrip(">"))
        name = WIKI_LEFTOVER.split(name)[0].strip("`* ")
    return (version.group(1).rstrip(".") if version else "", name)

# Underline character -> heading level, matching the convention the Xojo docs use.
HEADING_LEVEL = {"=": 1, "-": 2, "~": 3, "^": 4, '"': 5, "#": 6, "+": 6, "*": 6}

# Section title -> the member kind its rows describe.
SUMMARY_SECTIONS = {
    "properties": "property",
    "shared properties": "property",
    "class properties": "property",
    "methods": "method",
    "shared methods": "method",
    "class methods": "method",
    "events": "event",
    "event handlers": "event",
    "constants": "constant",
    "enumerations": "enumeration",
}
DESCRIPTION_SECTIONS = {
    "property descriptions": "property",
    "shared property descriptions": "property",
    "method descriptions": "method",
    "shared method descriptions": "method",
    "event descriptions": "event",
    "constant descriptions": "constant",
    "enumeration descriptions": "enumeration",
}

ADMONITIONS = {
    "note": "Note",
    "important": "Important",
    "warning": "Warning",
    "tip": "Tip",
    "caution": "Caution",
    "nota": "Note",  # Spanish; one page in espanol/ uses it
    "seealso": "See also",
    "attention": "Attention",
    "danger": "Danger",
    "error": "Error",
    "hint": "Hint",
}

# Directives that carry no content worth keeping in a text mirror.
DROPPED = {"meta", "toctree", "rst-class", "raw", "index", "highlight", "contents"}

IMAGE_BASE = "https://documentation.xojo.com/_images"


def is_underline(line: str) -> bool:
    # Strict reStructuredText wants the underline at least as long as the title,
    # but Sphinx only warns and builds the heading anyway; 110 headings in these
    # docs are short. A transition rule can never be mistaken for one,
    # because a transition is always preceded by a blank line and the caller
    # only offers non-blank titles.
    return bool(PUNCT_LINE.match(line))


@dataclass
class Section:
    title: str
    level: int
    lines: list[str] = field(default_factory=list)


@dataclass
class Member:
    anchor: str
    qualified: str
    name: str
    signature: str
    kind: str
    body: list[str]
    flags: str = ""
    deprecated: bool = False
    deprecated_in: str = ""
    replacement: str = ""


@dataclass
class Page:
    docname: str
    kind: str = ""
    title: str = ""
    preamble: list[str] = field(default_factory=list)
    sections: list[Section] = field(default_factory=list)
    members: list[Member] = field(default_factory=list)
    deprecated: bool = False
    deprecated_in: str = ""
    replacement: str = ""

    @property
    def has_members(self) -> bool:
        return bool(self.members)


def split_sections(lines: list[str]) -> tuple[list[str], list[Section]]:
    """Split a document into its leading preamble and its sections."""
    preamble: list[str] = []
    sections: list[Section] = []
    current: Section | None = None
    i = 0

    while i < len(lines):
        line = lines[i]
        title = level = None

        # Overline form: punctuation, title, matching punctuation.
        if (
            PUNCT_LINE.match(line)
            and i + 2 < len(lines)
            and lines[i + 1].strip()
            and not PUNCT_LINE.match(lines[i + 1])
            and is_underline(lines[i + 2])
            and lines[i + 2].strip()[0] == line.strip()[0]
        ):
            title, level, i = lines[i + 1].strip(), HEADING_LEVEL.get(line.strip()[0], 6), i + 3
        # Underline form: title then punctuation.
        elif (
            line.strip()
            and not PUNCT_LINE.match(line)
            and not COMMENT.match(line)
            and i + 1 < len(lines)
            and is_underline(lines[i + 1])
        ):
            title, level, i = line.strip(), HEADING_LEVEL.get(lines[i + 1].strip()[0], 6), i + 2

        if title is None:
            (current.lines if current else preamble).append(line)
            i += 1
            continue

        current = Section(title=title, level=level)
        sections.append(current)

    return preamble, sections


def collect_indented(lines: list[str], start: int, indent: int) -> tuple[list[str], int]:
    """Collect the blank-or-more-indented lines that form a directive body."""
    body: list[str] = []
    i = start
    while i < len(lines):
        line = lines[i]
        if line.strip() and (len(line) - len(line.lstrip())) <= indent:
            break
        body.append(line)
        i += 1
    while body and not body[-1].strip():
        body.pop()
    return dedent(body), i


def dedent(lines: list[str]) -> list[str]:
    widths = [len(l) - len(l.lstrip()) for l in lines if l.strip()]
    if not widths:
        return [l.strip() for l in lines]
    cut = min(widths)
    return [l[cut:] if l.strip() else "" for l in lines]


# --------------------------------------------------------------------------
# Page parsing
# --------------------------------------------------------------------------


def parse_page(docname: str, text: str) -> Page:
    lines = [l.expandtabs(4).rstrip() for l in text.splitlines()]
    preamble, sections = split_sections(lines)
    page = Page(docname=docname, preamble=preamble, sections=sections)

    if sections:
        page.title = sections[0].title
    else:
        page.title = posixpath.basename(docname)

    # The kind ("Class", "Method", "Keyword", ...) is the last real line of the
    # preamble; directives, comments and substitutions do not count.
    for line in reversed(preamble):
        stripped = line.strip()
        if not stripped or COMMENT.match(line) or stripped.startswith("|"):
            continue
        if PUNCT_LINE.match(line) or OPTION.match(line):
            continue
        page.kind = stripped
        break

    # Page-level deprecation is decided by path, not prose: a release-notes page
    # that merely mentions a deprecation is not itself deprecated. The version
    # and replacement still come from the notice, which sits above Description.
    page.deprecated_in, page.replacement = deprecation(text)

    for section in sections:
        kind = DESCRIPTION_SECTIONS.get(section.title.strip().lower())
        if kind:
            page.members.extend(parse_members(section.lines, kind))

    return page


def parse_members(lines: list[str], kind: str) -> list[Member]:
    """Carve a '<X> descriptions' section into one Member per anchor."""
    starts = [i for i, line in enumerate(lines) if ANCHOR.match(line)]
    members: list[Member] = []

    for n, start in enumerate(starts):
        end = starts[n + 1] if n + 1 < len(starts) else len(lines)
        anchor = ANCHOR.match(lines[start]).group(1).strip()
        block = lines[start + 1 : end]

        signature_at = next(
            (i for i, l in enumerate(block) if l.strip().startswith("**")), None
        )
        if signature_at is None:
            continue

        signature_line = block[signature_at].strip()
        qualified = ""
        for line in reversed(block[:signature_at]):
            stripped = line.strip()
            if not stripped or COMMENT.match(line) or PUNCT_LINE.match(line):
                continue
            qualified = stripped
            break

        name_match = re.match(r"\*\*(.+?)\*\*(.*)$", signature_line, re.DOTALL)
        if not name_match:
            continue
        name = name_match.group(1).strip()
        signature = name_match.group(2).lstrip("\\").strip()

        body = dedent(block[signature_at + 1 :])
        joined = "\n".join(body)
        deprecated_in, replacement = deprecation(joined)
        members.append(
            Member(
                anchor=anchor,
                qualified=qualified or name,
                name=name,
                signature=signature,
                kind=kind,
                body=body,
                deprecated=bool(DEPRECATION.search(joined)),
                deprecated_in=deprecated_in,
                replacement=replacement,
            )
        )

    return members


# --------------------------------------------------------------------------
# csv-table parsing
# --------------------------------------------------------------------------


def parse_csv_table(body: list[str]) -> tuple[list[str], list[list[str]]]:
    """Return (header, rows) for a csv-table directive body."""
    options: dict[str, str] = {}
    i = 0
    while i < len(body):
        if not body[i].strip():
            i += 1
            break
        match = OPTION.match(body[i])
        if not match:
            break
        options[match.group(1).lower()] = match.group(2).strip()
        i += 1

    data = "\n".join(body[i:]).strip()
    rows = [
        row
        for row in csv.reader(io.StringIO(data), skipinitialspace=True)
        if any(c.strip() for c in row)
    ]

    header: list[str] = []
    if "header" in options:
        header = next(csv.reader(io.StringIO(options["header"]), skipinitialspace=True), [])
    elif options.get("header-rows", "").strip().isdigit():
        count = int(options["header-rows"])
        if count and rows:
            header = rows[0]
            rows = rows[count:]

    return [h.strip() for h in header], rows


REF_LABEL = re.compile(r":ref:`[^`<]*<([^`>]+)>`")
CHECK = "✓"


def summary_flags(page: Page) -> dict[str, tuple[str, str]]:
    """Read a page's summary tables for each member's kind and flags.

    The summary rows name their member with a :ref: role, so the label in that
    role joins a table row to the description block that carries the same
    anchor, so no fuzzy name matching is required.
    """
    found: dict[str, tuple[str, str]] = {}

    for section in page.sections:
        kind = SUMMARY_SECTIONS.get(section.title.strip().lower())
        if not kind:
            continue
        lines = section.lines
        i = 0
        while i < len(lines):
            match = DIRECTIVE.match(lines[i])
            if not match or match.group(2).lower() != "csv-table":
                i += 1
                continue
            indent = len(match.group(1))
            body, i = collect_indented(lines, i + 1, indent)
            header, rows = parse_csv_table(body)
            columns = [h.strip().lower() for h in header]
            for row in rows:
                if not row:
                    continue
                label_match = REF_LABEL.search(row[0])
                if not label_match:
                    continue
                flags = []
                for index, column in enumerate(columns):
                    if index >= len(row) or CHECK not in row[index]:
                        continue
                    if "read" in column and "only" in column:
                        flags.append("read-only")
                    elif "shared" in column:
                        flags.append("shared")
                found[label_match.group(1).strip()] = (kind, ",".join(flags))
    return found


def parse_inventory_labels(path: Path) -> tuple[dict[str, str], list[str]]:
    """Return (label -> docname, [docname]) from a Sphinx objects.inv."""
    raw = path.read_bytes()
    offset = 0
    for _ in range(4):
        offset = raw.index(b"\n", offset) + 1
    record = re.compile(r"(?x)(.+?)\s+(\S+)\s+(-?\d+)\s+?(\S*)\s+(.*)")

    labels: dict[str, tuple[str, str]] = {}
    docnames: list[str] = []
    for line in zlib.decompress(raw[offset:]).decode("utf-8").splitlines():
        match = record.match(line.rstrip())
        if not match:
            continue
        name, role, _priority, uri, display = match.groups()
        if uri.endswith("$"):
            uri = uri[:-1] + name
        docname = uri.split("#", 1)[0].removesuffix(".html")
        if role == "std:doc":
            docnames.append(docname)
        elif role == "std:label":
            # "-" means the inventory has no title for this label.
            labels[name] = (docname, "" if display.strip() == "-" else display.strip())
    return labels, docnames


# --------------------------------------------------------------------------
# Rendering
# --------------------------------------------------------------------------


class Resolver:
    """Turns :doc:/:ref: targets into relative links between generated files."""

    def __init__(self, pages: dict[str, Page], labels: dict[str, str]):
        self.pages = pages
        # Some docnames are percent-encoded in objects.inv because the URL is
        # (the "+" operator page is served as %2B), while :doc: roles spell the
        # decoded name. Index both so either form resolves.
        self.labels = {unquote(k): (unquote(v[0]), v[1]) for k, v in labels.items()}
        # A few upstream links get the capitalization wrong, e.g. /api/language/New
        # for a page whose docname is "new". Fall back to a case-insensitive match.
        self.folded = {d.lower(): d for d in pages}
        # label -> docname for every member we actually emitted
        self.members: dict[str, str] = {}
        for docname, page in pages.items():
            for member in page.members:
                self.members[member.anchor] = docname
        self.unresolved: Counter = Counter()

    def _page(self, target: str) -> str | None:
        if target in self.pages:
            return target
        return self.folded.get(target.lower())

    def doc_link(self, current: str, target: str) -> str | None:
        target = unquote(target.strip().lstrip("/"))
        if not target:
            return None
        docname = self._page(target)
        if docname is None:
            self.unresolved["doc"] += 1
            return None
        # A page that links to itself sends the reader nowhere. Upstream does
        # this a handful of times; render the text without the link.
        if docname == current:
            return None
        return md_path(relative(current, docname + ".md"))

    def ref_link(self, current: str, label: str) -> str | None:
        label = unquote(label.strip().lstrip("/"))
        docname = self.members.get(label)
        if docname:
            # The fragment needs the same escaping as the path: a few labels
            # contain parentheses, which would end the link destination early.
            return md_path(relative(current, docname + ".members.md")) + "#" + md_path(label)
        entry = self.labels.get(label)
        if entry and (docname := self._page(entry[0])):
            # A section label carries no anchor in the generated Markdown, so a
            # label living on the current page would only link to itself. Say
            # nothing rather than point the reader back where they already are.
            if docname == current:
                return None
            return md_path(relative(current, docname + ".md"))
        self.unresolved["ref"] += 1
        return None

    def label_display(self, label: str) -> str:
        """The inventory's title for a label, for refs written without text."""
        entry = self.labels.get(unquote(label.strip().lstrip("/")))
        return entry[1] if entry else ""


def unquote(text: str) -> str:
    return urllib.parse.unquote(text)


def md_path(path: str) -> str:
    """Escape the characters that would end a Markdown link destination early."""
    return path.replace("(", "%28").replace(")", "%29").replace(" ", "%20")


def relative(from_docname: str, to_path: str) -> str:
    base = posixpath.dirname(from_docname)
    return posixpath.relpath(to_path, base) if base else to_path


class Renderer:
    def __init__(self, resolver: Resolver, stats: Counter):
        self.resolver = resolver
        self.stats = stats

    # ---- inline --------------------------------------------------------

    def inline(self, text: str, current: str, plain: bool = False) -> str:
        literals: list[str] = []

        def stash(match: re.Match) -> str:
            literals.append(match.group(1))
            return f"\x00{len(literals) - 1}\x00"

        text = LITERAL.sub(stash, text)
        text = SUBSTITUTION.sub("", text)

        def role(match: re.Match) -> str:
            name, content = match.group(1), match.group(2)
            target_match = TARGETED.match(content)
            label = target_match.group(1).strip() if target_match else content.strip()
            target = target_match.group(2).strip() if target_match else content.strip()

            if name in ("doc", "ref"):
                display = label
                if not target_match and name == "ref":
                    display = self.resolver.label_display(target) or label
                display = display or posixpath.basename(target.rstrip("/"))
                if plain:
                    return display
                href = (
                    self.resolver.doc_link(current, target)
                    if name == "doc"
                    else self.resolver.ref_link(current, target)
                )
                return f"[{display}]({href})" if href else display
            if name == "kbd":
                return content if plain else f"`{content}`"
            if name == "sup":
                return content if plain else f"<sup>{content}</sup>"
            if name in ("subscript", "sub"):
                return content if plain else f"<sub>{content}</sub>"
            if name == "download":
                display = label or target
                return display if plain else f"[{display}](https://documentation.xojo.com/{target.lstrip('/')})"
            self.stats[f"role:{name}"] += 1
            return label or content

        text = ROLE.sub(role, text)

        def hyperlink(match: re.Match) -> str:
            label, target = match.group(1).strip(), match.group(2).strip()
            if plain:
                return label
            if target.startswith(("http://", "https://", "mailto:", "ftp://")):
                return f"[{label}]({target})"
            # A handful are written as hyperlinks but point at a doc page.
            href = self.resolver.doc_link(current, target)
            return f"[{label}]({href})" if href else label

        text = RST_LINK.sub(hyperlink, text)
        text = re.sub(r"\\(.)", r"\1", text)
        for n, literal in enumerate(literals):
            text = text.replace(f"\x00{n}\x00", literal if plain else f"`{literal}`")
        return text

    # ---- block ---------------------------------------------------------

    def block(self, lines: list[str], current: str, base_level: int = 2) -> list[str]:
        out: list[str] = []
        enum = 0
        i = 0
        while i < len(lines):
            line = lines[i]

            if not line.strip():
                out.append("")
                i += 1
                continue

            indent = len(line) - len(line.lstrip())

            # An indented run is a block quote, or a literal block when the
            # paragraph above ended with "::". Either way it cannot be left
            # indented: Markdown would silently render the prose as code. The
            # source uses tabs in places, which expandtabs turns into exactly
            # the four spaces that trigger it.
            if indent >= 3 and not LIST_ITEM.match(line):
                body, i = collect_indented(lines, i, indent - 1)
                # The paragraph owning the "::" is the last NON-BLANK entry:
                # standard reStructuredText puts a blank line before the
                # indented block, so out[-1] is "" by the time it is reached.
                last = next((k for k in range(len(out) - 1, -1, -1)
                             if out[k].strip()), None)
                literal = last is not None and out[last].rstrip().endswith("::")
                if literal:
                    remainder = out[last].rstrip()[:-2].rstrip()
                    if remainder:
                        out[last] = remainder
                    else:
                        # A paragraph that was only "::" disappears, as in RST.
                        del out[last]
                    out += ["", "```", *body, "```", ""]
                else:
                    out += ["", *self.block(body, current, base_level), ""]
                continue

            auto = AUTO_ENUM.match(line)
            explicit = EXPLICIT_ENUM.match(line)
            if auto:
                # "#." continues whatever number the list is up to, including a
                # list that began with an explicit "1.".
                enum += 1
                line = f"{auto.group(1)}{enum}.{auto.group(2)}{auto.group(3)}"
            elif explicit:
                enum = int(explicit.group(1))
            elif indent == 0 and not LIST_ITEM.match(line):
                enum = 0

            # Nested headings inside a section body.
            if (
                not PUNCT_LINE.match(line)
                and not COMMENT.match(line)
                and i + 1 < len(lines)
                and is_underline(lines[i + 1])
            ):
                level = min(HEADING_LEVEL.get(lines[i + 1].strip()[0], 6) + base_level - 1, 6)
                out += ["", "#" * level + " " + self.inline(line.strip(), current), ""]
                i += 2
                continue

            if PUNCT_LINE.match(line):  # transition rule
                i += 1
                continue

            directive = DIRECTIVE.match(line)
            if directive:
                indent = len(directive.group(1).expandtabs(4))
                name, arg = directive.group(2).lower(), directive.group(3).strip()
                body, i = collect_indented(lines, i + 1, indent)
                out += self.directive(name, arg, body, current, base_level)
                continue

            if COMMENT.match(line):  # comment or anchor: skip with its body
                indent = len(COMMENT.match(line).group(1).expandtabs(4))
                _, i = collect_indented(lines, i + 1, indent)
                continue

            out.append(self.inline(line, current))
            i += 1

        return out

    def directive(
        self, name: str, arg: str, body: list[str], current: str, base_level: int
    ) -> list[str]:
        if name in DROPPED:
            return []

        if name in ("code", "code-block", "sourcecode"):
            language = arg.split()[0] if arg else ""
            code = list(body)
            while code and not code[0].strip():
                code.pop(0)
            return ["", f"```{language}", *code, "```", ""]

        if name == "csv-table":
            return self.table(arg, body, current)

        if name in ADMONITIONS:
            # An admonition's argument is its first paragraph, not its title --
            # and it carries inline markup like any other prose.
            rendered = self.block(body, current, base_level)
            quoted = [f"> {l}".rstrip() for l in rendered]
            lead = [f"> {self.inline(arg, current)}"] if arg else []
            return ["", f"> **{ADMONITIONS[name]}**", ">", *lead, *quoted, ""]

        if name == "image" or name == "figure":
            alt = next((l.split(":", 2)[2].strip() for l in body if l.strip().startswith(":alt:")), "")
            return ["", f"![{alt}]({IMAGE_BASE}/{posixpath.basename(arg)})", ""]

        if name == "youtube":
            return ["", f"[Video](https://www.youtube.com/watch?v={arg})", ""]

        if name == "collapse":
            rendered = self.block(body, current, base_level)
            return ["", f"**{self.inline(arg, current)}**", "", *rendered, ""]

        if name == "rubric":
            return ["", f"**{self.inline(arg, current)}**", ""]

        # An unrecognized directive still has content worth keeping. Its
        # argument is not decoration: for a one-line directive it is the entire
        # text, and dropping it loses the content outright.
        self.stats[f"directive:{name}"] += 1
        lead = ["", self.inline(arg, current), ""] if arg else []
        return lead + self.block(body, current, base_level)

    def table(self, arg: str, body: list[str], current: str) -> list[str]:
        header, rows = parse_csv_table(body)
        if not rows and not header:
            return []

        width = max([len(header)] + [len(r) for r in rows]) if (header or rows) else 0
        if not width:
            return []

        def cell(value: str) -> str:
            return self.inline(value.strip(), current).replace("|", "\\|").replace("\n", " ")

        def row(values: list[str]) -> str:
            padded = list(values) + [""] * (width - len(values))
            return "| " + " | ".join(cell(v) for v in padded[:width]) + " |"

        head = header if header else [""] * width
        out = ["", row(head), "|" + "|".join([" --- "] * width) + "|"]
        out += [row(r) for r in rows]
        out.append("")
        return out
