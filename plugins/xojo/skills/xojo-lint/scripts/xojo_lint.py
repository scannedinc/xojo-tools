#!/usr/bin/env python3
"""Validate, lint, and conservatively format Xojo text projects.

The implementation intentionally validates containers and relationships rather
than maintaining closed lists of every Xojo property. Unknown keys and tags are
preserved so a newer IDE can extend the formats without making older versions
of this tool destructive.
"""

from __future__ import annotations

import argparse
import difflib
import json
import os
import re
import stat
import struct
import sys
import zipfile
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path, PurePosixPath
from typing import Iterable, Iterator, Sequence

from helptext import HelpConfig, HelpfulParser, help_theme


KNOWN_PROJECT_VERSION = Decimal("2026.021")

LINT_PROG = "python3 scripts/xojo_lint.py"
LINT_COLOR_ENV = "XOJO_LINT_COLOR"
LINT_COMMAND_BLURBS = {
    "check": "Validate and lint Xojo Project files",
    "format": "Conservatively format text-based Xojo Project files",
}
LINT_HELP = HelpConfig(
    prog=LINT_PROG,
    command_blurbs=LINT_COMMAND_BLURBS,
    root_examples=(
        "check .",
        "check --all path/to/project",
        "format --check path/to/project",
    ),
    command_examples={
        "check": (
            "check .",
            "check --all path/to/project",
            "check --all --warnings-as-errors .",
        ),
        "format": (
            "format --check path/to/project",
            "format --diff path/to/project",
            "format path/to/project",
        ),
    },
    learn_more=(
        "Unknown properties and keys are accepted for forward compatibility.",
        "Use check --all for every optional check; warning exit policy is separate.",
    ),
    color_env=LINT_COLOR_ENV,
)


class LintParser(HelpfulParser):
    """The linter CLI using the documentation tools' shared help style."""

    help_config = LINT_HELP


TEXT_EXTENSIONS = {
    ".xojo_code",
    ".xojo_color",
    ".xojo_database_connection",
    ".xojo_filetypeset",
    ".xojo_image",
    ".xojo_menu",
    ".xojo_project",
    ".xojo_report",
    ".xojo_script",
    ".xojo_toolbar",
    ".xojo_window",
}
BINARY_EXTENSIONS = {".xojo_library", ".xojo_resources", ".xojo_uistate"}
SUPPORTED_EXTENSIONS = TEXT_EXTENSIONS | BINARY_EXTENSIONS
KNOWN_OPAQUE_EXTENSIONS = {
    ".xojo_binary_code": "binary-format source item",
    ".xojo_binary_project": "Xojo Binary Project",
    ".xojo_plugin": "compiled plugin archive",
    ".xojo_theme": "IDE theme",
    ".xojo_xml_code": "XML-format source item",
    ".xojo_xml_project": "Xojo XML Project",
}
TAGGED_EXTENSIONS = {
    ".xojo_code",
    ".xojo_color",
    ".xojo_filetypeset",
    ".xojo_image",
    ".xojo_menu",
    ".xojo_report",
    ".xojo_toolbar",
    ".xojo_window",
}

EXPECTED_OUTER_TAGS = {
    ".xojo_code": {
        "BuildAutomation",
        "Class",
        "Interface",
        "IOSContainerControl",
        "IOSLaunchScreen",
        "IOSLayout",
        "IOSScreen",
        "IOSView",
        "MobileContainer",
        "MobileScreen",
        "Module",
        "WebContainerControl",
        "WebPage",
        "WebStyle",
        "iOSLayout",
    },
    ".xojo_color": {"ColorGroup"},
    ".xojo_filetypeset": {"FileTypeSet"},
    ".xojo_image": {"MultiImage"},
    ".xojo_menu": {"Menu"},
    ".xojo_report": {"Report"},
    ".xojo_toolbar": {"DesktopToolbar", "Toolbar"},
    ".xojo_window": {"DesktopWindow", "Window"},
}

KNOWN_TAG_KINDS = {
    "BuildAutomation",
    "Class",
    "Color",
    "ColorGroup",
    "CompatibilityFlags",
    "ComputedProperty",
    "Constant",
    "DelegateDeclaration",
    "DesktopToolbar",
    "DesktopWindow",
    "Enum",
    "EnumValues",
    "Event",
    "Events",
    "ExternalMethod",
    "FileType",
    "FileTypeSet",
    "Getter",
    "Hook",
    "IOSContainerControl",
    "IOSLaunchScreen",
    "IOSLayout",
    "IOSScreen",
    "IOSView",
    "ImageRepresentation",
    "ImageSpecification",
    "Instance",
    "Interface",
    "Menu",
    "MenuHandler",
    "Method",
    "MobileContainer",
    "MobileScreen",
    "Module",
    "MultiImage",
    "Note",
    "Property",
    "Report",
    "ReportCode",
    "ScreenCode",
    "Session",
    "Setter",
    "Structure",
    "Toolbar",
    "Using",
    "ViewBehavior",
    "ViewProperty",
    "WebContainerControl",
    "WebPage",
    "WebStyle",
    "WebStyleStateGroup",
    "Window",
    "WindowCode",
    "Worker",
    "iOSLayout",
}

STANDALONE_TAGS = {"CompatibilityFlags", "Instance"}
# These class metadata regions are serialized flush-left even though they occur
# before the enclosing Class region is closed.
OUTDENTED_METADATA_TAGS = {"Session", "Worker"}
SOURCE_BODY_TAGS = {
    "ComputedProperty",
    "DelegateDeclaration",
    "Enum",
    "Event",
    "ExternalMethod",
    "Getter",
    "Hook",
    "MenuHandler",
    "Method",
    "Note",
    "Property",
    "Setter",
    "Structure",
}
DESIGNER_TAGS = {
    "BuildAutomation",
    "DesktopToolbar",
    "DesktopWindow",
    "IOSContainerControl",
    "IOSLaunchScreen",
    "IOSLayout",
    "IOSScreen",
    "IOSView",
    "Menu",
    "MobileContainer",
    "MobileScreen",
    "MultiImage",
    "Report",
    "Toolbar",
    "WebContainerControl",
    "WebPage",
    "Window",
    "iOSLayout",
}

TAG_RE = re.compile(r"^(?P<indent>[ \t]*)#(?P<word>tag)\s+(?P<body>.*?)[ \t]*$", re.I)
TAG_KIND_RE = re.compile(
    r"^(?P<kind>[A-Za-z][A-Za-z0-9]*)(?P<tail>(?:\s+.*|\s*,.*|\s*=.*)?)$"
)
END_TAG_RE = re.compile(r"^End(?P<kind>[A-Za-z][A-Za-z0-9]*)$")
BEGIN_RE = re.compile(
    r"^[ \t]*(?:Begin[ \t]+(?P<kind>\S+)(?:[ \t]+.*)?|"
    r"Begin(?P<compact_kind>[A-Z][A-Za-z0-9_.]*)[ \t]+.+)$"
)
IMAGE_RE = re.compile(r"^[ \t]*Image(?:\s+.*)?$")
ITEM_ROW_RE = re.compile(
    r"^(?P<name>[^;]*);(?P<path>[^;]*);"
    r"(?P<item>&h[0-9A-Fa-f]+);(?P<parent>&h[0-9A-Fa-f]+);"
    r"(?P<trailing>true|false)(?P<extra>(?:;[^;]*)*)$",
    re.I,
)
KEY_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")
MERGE_MARKER_RE = re.compile(r"^(?:<{7}|={7}|>{7})(?:\s|$)")


@dataclass(frozen=True)
class Diagnostic:
    path: Path
    line: int
    column: int
    severity: str
    code: str
    message: str

    def sort_key(self) -> tuple[str, int, int, str]:
        return (str(self.path), self.line, self.column, self.code)


@dataclass(frozen=True)
class TextDocument:
    text: str
    bom: bool
    raw: bytes


@dataclass(frozen=True)
class TagToken:
    line: int
    indent: str
    body: str
    kind: str
    closing: bool
    standalone: bool
    depth: int
    opener_kind: str | None = None


@dataclass(frozen=True)
class FormatOptions:
    line_ending: str = "preserve"
    final_newline: str = "add"
    source_indent: bool = True


def diagnostic(
    path: Path,
    code: str,
    message: str,
    *,
    line: int = 1,
    column: int = 1,
    severity: str = "error",
) -> Diagnostic:
    return Diagnostic(path, line, column, severity, code, message)


def extension_for(path: Path) -> str:
    return path.suffix.lower()


def is_xojo_extension(path: Path) -> bool:
    return path.suffix.lower().startswith(".xojo_")


def display_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(Path.cwd().resolve()))
    except ValueError:
        return str(path)


def read_text_document(path: Path) -> tuple[TextDocument | None, list[Diagnostic]]:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        return None, [diagnostic(path, "XJC001", f"cannot read file: {exc}")]
    if b"\x00" in raw:
        return None, [diagnostic(path, "XJC002", "NUL byte in text-format file")]
    bom = raw.startswith(b"\xef\xbb\xbf")
    payload = raw[3:] if bom else raw
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        return None, [
            diagnostic(
                path,
                "XJC003",
                f"invalid UTF-8 at byte {exc.start}: {exc.reason}",
            )
        ]
    return TextDocument(text, bom, raw), []


def validate_common_text(path: Path, document: TextDocument) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    if document.bom:
        diagnostics.append(
            diagnostic(
                path,
                "XJC101",
                "UTF-8 BOM is accepted but not emitted by the observed IDE corpus",
                severity="warning",
            )
        )
    for number, line in enumerate(split_logical_lines(document.text), 1):
        if MERGE_MARKER_RE.match(line):
            diagnostics.append(
                diagnostic(
                    path,
                    "XJC004",
                    "unresolved merge-conflict marker",
                    line=number,
                )
            )
    if document.text and not document.text.endswith(("\n", "\r")):
        diagnostics.append(
            diagnostic(
                path,
                "XJC201",
                "no line break at end of file; `format` adds one",
                line=len(split_logical_lines(document.text)),
                severity="notice",
            )
        )
    return diagnostics


def closing_end_kinds(lines: Iterable[str]) -> set[str]:
    """Every kind that appears as a `#tag End<kind>` line, casefolded.

    One definition shared by the validators and the formatter, so their
    models of which tags close can never drift apart.
    """
    return {
        end_match.group("kind").casefold()
        for line in lines
        if (tag_match := TAG_RE.match(line.rstrip("\r")))
        if (end_match := END_TAG_RE.match(tag_match.group("body")))
    }


def is_standalone_tag(kind: str, closing_kinds: set[str]) -> bool:
    """An unknown kind with no matching End tag is an opaque standalone
    record. This lets a newer IDE add metadata records without making an
    older validator claim the rest of the file is malformed.
    """
    return kind in STANDALONE_TAGS or (
        kind not in KNOWN_TAG_KINDS and kind.casefold() not in closing_kinds
    )


def parse_tag_tokens(
    path: Path,
    text: str,
    *,
    warn_unknown: bool,
) -> tuple[list[TagToken], list[Diagnostic]]:
    stack: list[tuple[str, int]] = []
    tokens: list[TagToken] = []
    diagnostics: list[Diagnostic] = []
    closing_kinds = closing_end_kinds(split_logical_lines(text))

    for number, line in enumerate(split_logical_lines(text), 1):
        match = TAG_RE.match(line.rstrip("\r"))
        if not match:
            continue
        body = match.group("body")
        end_match = END_TAG_RE.match(body)
        if end_match:
            kind = end_match.group("kind")
            expected_depth = max(0, len(stack) - 1)
            opener_kind: str | None = None
            if not stack:
                diagnostics.append(
                    diagnostic(
                        path,
                        "XJT001",
                        f"unexpected closing tag End{kind}",
                        line=number,
                        column=len(match.group("indent")) + 1,
                    )
                )
            else:
                opener_kind = stack[-1][0]
                if opener_kind.casefold() != kind.casefold():
                    diagnostics.append(
                        diagnostic(
                            path,
                            "XJT002",
                            f"closing tag End{kind} does not match open {opener_kind}",
                            line=number,
                            column=len(match.group("indent")) + 1,
                        )
                    )
                    matching_index = next(
                        (
                            index
                            for index in range(len(stack) - 1, -1, -1)
                            if stack[index][0].casefold() == kind.casefold()
                        ),
                        None,
                    )
                    if matching_index is not None:
                        opener_kind = stack[matching_index][0]
                        del stack[matching_index:]
                    else:
                        stack.pop()
                else:
                    stack.pop()
            tokens.append(
                TagToken(
                    number,
                    match.group("indent"),
                    body,
                    kind,
                    True,
                    False,
                    expected_depth,
                    opener_kind,
                )
            )
            continue

        kind_match = TAG_KIND_RE.match(body)
        if not kind_match:
            diagnostics.append(
                diagnostic(
                    path,
                    "XJT003",
                    "malformed #tag header",
                    line=number,
                    column=len(match.group("indent")) + 1,
                )
            )
            continue
        kind = kind_match.group("kind")
        standalone = is_standalone_tag(kind, closing_kinds)
        depth = len(stack)
        tokens.append(
            TagToken(
                number,
                match.group("indent"),
                body,
                kind,
                False,
                standalone,
                depth,
            )
        )
        if warn_unknown and kind not in KNOWN_TAG_KINDS:
            diagnostics.append(
                diagnostic(
                    path,
                    "XJT101",
                    f"unknown tag kind {kind!r}; preserved as a future extension",
                    line=number,
                    column=len(match.group("indent")) + 1,
                    severity="warning",
                )
            )
        if not standalone:
            stack.append((kind, number))

    for kind, number in stack:
        diagnostics.append(
            diagnostic(
                path,
                "XJT004",
                f"unclosed #tag {kind}",
                line=number,
            )
        )
    return tokens, diagnostics


def validate_begin_blocks(path: Path, text: str) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    blocks: list[tuple[str, int]] = []
    tag_stack: list[str] = []
    closing_kinds = closing_end_kinds(split_logical_lines(text))

    for number, line in enumerate(split_logical_lines(text), 1):
        stripped = line.strip()
        tag_match = TAG_RE.match(line.rstrip("\r"))
        if tag_match:
            body = tag_match.group("body")
            end_match = END_TAG_RE.match(body)
            if end_match:
                if tag_stack:
                    tag_stack.pop()
            else:
                kind_match = TAG_KIND_RE.match(body)
                if kind_match:
                    kind = kind_match.group("kind")
                    if not is_standalone_tag(kind, closing_kinds):
                        tag_stack.append(kind)
            continue

        begin_match = BEGIN_RE.match(line)
        if begin_match and any(kind in DESIGNER_TAGS for kind in tag_stack):
            kind = begin_match.group("kind") or begin_match.group("compact_kind")
            blocks.append((kind, number))
            continue
        if IMAGE_RE.match(line) and any(kind == "MultiImage" for kind in tag_stack):
            blocks.append(("Image", number))
            continue
        if stripped == "End":
            if blocks:
                blocks.pop()
            continue
        if stripped in {"End Image", "End ScreenContent"}:
            expected = stripped[4:]
            if not blocks:
                diagnostics.append(
                    diagnostic(
                        path,
                        "XJB002",
                        f"unexpected {stripped}",
                        line=number,
                    )
                )
            elif blocks[-1][0] != expected:
                diagnostics.append(
                    diagnostic(
                        path,
                        "XJB003",
                        f"{stripped} closes Begin {blocks[-1][0]}",
                        line=number,
                    )
                )
                blocks.pop()
            else:
                blocks.pop()

    for kind, number in blocks:
        diagnostics.append(
            diagnostic(path, "XJB004", f"unclosed Begin {kind}", line=number)
        )
    return diagnostics


def validate_tagged_text(
    path: Path,
    document: TextDocument,
    *,
    warn_unknown: bool,
) -> list[Diagnostic]:
    # Xojo emits empty .xojo_code placeholders for some platform group items.
    if not document.text:
        return []
    tokens, diagnostics = parse_tag_tokens(
        path, document.text, warn_unknown=warn_unknown
    )
    diagnostics.extend(validate_begin_blocks(path, document.text))
    outer = next((token for token in tokens if not token.closing and token.depth == 0), None)
    if outer is None:
        diagnostics.append(diagnostic(path, "XJT005", "missing outer #tag region"))
    else:
        expected = EXPECTED_OUTER_TAGS.get(extension_for(path))
        if expected and outer.kind not in expected:
            choices = ", ".join(sorted(expected))
            diagnostics.append(
                diagnostic(
                    path,
                    "XJT102",
                    f"outer tag {outer.kind!r} is unusual for {path.suffix}; expected one of {choices}",
                    line=outer.line,
                    severity="warning",
                )
            )
    return diagnostics


def parse_hex_id(value: str) -> int:
    return int(value[2:], 16)


def uninitialized_submodule_for(project: Path, missing: Path) -> str | None:
    """Return a containing uninitialized submodule path, when declared."""
    real_project = project.resolve()
    real_missing = missing.resolve(strict=False)
    for ancestor in (real_project.parent, *real_project.parents):
        gitmodules = ancestor / ".gitmodules"
        if not gitmodules.is_file():
            continue
        try:
            lines = gitmodules.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for line in lines:
            match = re.match(r"^[ \t]*path[ \t]*=[ \t]*(.+?)[ \t]*$", line)
            if not match:
                continue
            relative = Path(match.group(1))
            submodule = (ancestor / relative).resolve(strict=False)
            try:
                real_missing.relative_to(submodule)
            except ValueError:
                continue
            if not (submodule / ".git").exists():
                return relative.as_posix()
    return None


def validate_project(
    path: Path,
    document: TextDocument,
    *,
    check_paths: bool,
) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    values: dict[str, list[tuple[str, int]]] = {}
    item_rows: list[tuple[str, re.Match[str], int]] = []
    item_ids: dict[int, tuple[str, int]] = {}

    for number, line in enumerate(split_logical_lines(document.text), 1):
        if not line:
            diagnostics.append(
                diagnostic(
                    path,
                    "XJP101",
                    "blank manifest line is accepted but not emitted by the observed IDE",
                    line=number,
                    severity="warning",
                )
            )
            continue
        if "=" not in line:
            diagnostics.append(
                diagnostic(path, "XJP001", "manifest line has no '='", line=number)
            )
            continue
        key, value = line.split("=", 1)
        if not KEY_RE.fullmatch(key):
            diagnostics.append(
                diagnostic(path, "XJP002", f"invalid manifest key {key!r}", line=number)
            )
            continue
        values.setdefault(key, []).append((value, number))
        item_match = ITEM_ROW_RE.fullmatch(value)
        if item_match:
            item_rows.append((key, item_match, number))
            item_id = parse_hex_id(item_match.group("item"))
            if item_id in item_ids:
                previous_key, previous_line = item_ids[item_id]
                diagnostics.append(
                    diagnostic(
                        path,
                        "XJP003",
                        f"duplicate project item ID {item_match.group('item')} "
                        f"(first used by {previous_key} on line {previous_line})",
                        line=number,
                    )
                )
            else:
                item_ids[item_id] = (key, number)
        elif ";&h" in value and value.count(";") >= 3:
            diagnostics.append(
                diagnostic(
                    path,
                    "XJP004",
                    "malformed project item row; expected at least "
                    "Name;Path;&hID;&hParentID;false",
                    line=number,
                )
            )

    for required in ("Type", "RBProjectVersion"):
        if required not in values:
            diagnostics.append(
                diagnostic(path, "XJP005", f"missing required {required}= header")
            )

    if "RBProjectVersion" in values:
        version_text, version_line = values["RBProjectVersion"][0]
        try:
            project_version = Decimal(version_text)
        except InvalidOperation:
            diagnostics.append(
                diagnostic(
                    path,
                    "XJP006",
                    f"invalid RBProjectVersion {version_text!r}",
                    line=version_line,
                )
            )
        else:
            if project_version > KNOWN_PROJECT_VERSION:
                diagnostics.append(
                    diagnostic(
                        path,
                        "XJP102",
                        f"project version {project_version} is newer than validator knowledge "
                        f"{KNOWN_PROJECT_VERSION}; unknown additions are accepted",
                        line=version_line,
                        severity="warning",
                    )
                )

    for key, match, number in item_rows:
        parent_id = parse_hex_id(match.group("parent"))
        if parent_id != 0 and parent_id not in item_ids:
            diagnostics.append(
                diagnostic(
                    path,
                    "XJP007",
                    f"parent ID {match.group('parent')} is not declared in this manifest",
                    line=number,
                )
            )
        item_path = match.group("path")
        if not item_path:
            continue
        # Resolve the manifest before applying relative item paths. Repositories
        # often expose `Project/Foo.xojo_project` through a root-level symlink;
        # Xojo resolves companions beside the real manifest, not beside the
        # symlink.
        resolved = path.resolve().parent / Path(item_path.replace("\\", os.sep))
        companion = Path(item_path).suffix.lower().startswith(".xojo_")
        if (companion or check_paths) and not resolved.exists():
            severity = "error" if companion else "warning"
            message = f"{key} path does not exist: {item_path}"
            submodule = uninitialized_submodule_for(path, resolved)
            if submodule:
                message += (
                    f" (inside uninitialized git submodule {submodule}; "
                    "run git submodule update --init)"
                )
            diagnostics.append(
                diagnostic(
                    path,
                    "XJP008" if companion else "XJP103",
                    message,
                    line=number,
                    severity=severity,
                )
            )
    return diagnostics


def validate_resources(path: Path) -> list[Diagnostic]:
    try:
        data = path.read_bytes()
    except OSError as exc:
        return [diagnostic(path, "XJC001", f"cannot read file: {exc}")]
    diagnostics: list[Diagnostic] = []
    if not data:
        # Empty placeholders occur in otherwise valid older projects, but the
        # current IDE expands them to a framed 12-byte empty record.
        return [
            diagnostic(
                path,
                "XJR102",
                "legacy zero-byte resource placeholder; Xojo 2026.2.1 rewrites "
                "this as a 12-byte empty ICNS record",
                severity="warning",
            )
        ]

    def validate_chunks(start: int, end: int) -> None:
        chunk = start
        while chunk < end:
            if end - chunk < 8:
                diagnostics.append(
                    diagnostic(
                        path,
                        "XJR005",
                        f"truncated icon chunk header at byte {chunk}",
                    )
                )
                return
            chunk_length = struct.unpack_from(">I", data, chunk + 4)[0]
            next_chunk = chunk + 8 + chunk_length
            if next_chunk > end:
                code = data[chunk : chunk + 4]
                diagnostics.append(
                    diagnostic(
                        path,
                        "XJR006",
                        f"icon chunk {code!r} at byte {chunk} exceeds its ICNS payload",
                    )
                )
                return
            chunk = next_chunk

    offset = 0
    record_number = 0
    while offset < len(data):
        # Some older IDEs pad the sidecar after the last resource record.
        if not any(data[offset:]):
            break
        record_number += 1
        if len(data) - offset < 12:
            diagnostics.append(
                diagnostic(
                    path,
                    "XJR002",
                    f"truncated ICNS record header at byte {offset}",
                )
            )
            break
        magic = data[offset : offset + 4]
        if magic != b"ICNS":
            diagnostics.append(
                diagnostic(
                    path,
                    "XJR003",
                    f"expected ICNS record at byte {offset}, found {magic!r}",
                )
            )
            break
        marker, payload_length = struct.unpack_from(">II", data, offset + 4)
        if marker != 8:
            diagnostics.append(
                diagnostic(
                    path,
                    "XJR101",
                    f"ICNS record {record_number} has unknown marker {marker}; preserved as future format",
                    severity="warning",
                )
            )
        payload_start = offset + 12
        payload_end = payload_start + payload_length
        # A legacy variant uses the same 12-byte prefix with a zero outer
        # length, then stores one icon chunk stream through EOF.
        if (
            payload_length == 0
            and payload_start < len(data)
            and data[payload_start : payload_start + 4] != b"ICNS"
        ):
            diagnostics.append(
                diagnostic(
                    path,
                    "XJR103",
                    "legacy zero-length resource wrapper with trailing icon chunks; "
                    "Xojo 2026.2.1 rewrites this representation",
                    severity="warning",
                )
            )
            validate_chunks(payload_start, len(data))
            break
        if payload_end > len(data):
            diagnostics.append(
                diagnostic(
                    path,
                    "XJR004",
                    f"ICNS payload at byte {offset} extends {payload_end - len(data)} bytes past EOF",
                )
            )
            break
        validate_chunks(payload_start, payload_end)
        offset = payload_end
    return diagnostics


class UIStateParser:
    def __init__(self, path: Path, data: bytes):
        self.path = path
        self.data = data
        self.diagnostics: list[Diagnostic] = []
        self.unsupported = False

    def error(self, code: str, message: str) -> None:
        self.diagnostics.append(diagnostic(self.path, code, message))

    def warning(self, code: str, message: str) -> None:
        self.diagnostics.append(
            diagnostic(self.path, code, message, severity="warning")
        )

    # Grup records nest by recursion; a cap keeps a corrupt (or crafted) file
    # a diagnostic rather than a RecursionError traceback. Real UI state has
    # been observed a handful of levels deep, never near this.
    MAX_GROUP_DEPTH = 100

    def parse_stream(self, start: int, end: int, depth: int = 0) -> int:
        offset = start
        while offset < end:
            if end - offset < 8:
                self.error("XJU001", f"truncated UI-state tag at byte {offset}")
                return end
            tag = self.data[offset : offset + 8]
            value_type = tag[4:8]
            if value_type == b"Int ":
                if end - offset < 12:
                    self.error("XJU002", f"truncated Int record at byte {offset}")
                    return end
                offset += 12
            elif value_type == b"Rect":
                if end - offset < 24:
                    self.error("XJU003", f"truncated Rect record at byte {offset}")
                    return end
                offset += 24
            elif value_type == b"Strn":
                if end - offset < 12:
                    self.error("XJU004", f"truncated Strn header at byte {offset}")
                    return end
                length = struct.unpack_from(">I", self.data, offset + 8)[0]
                padded = (length + 3) & ~3
                next_offset = offset + 12 + padded
                if next_offset > end:
                    self.error("XJU005", f"Strn record at byte {offset} exceeds its container")
                    return end
                offset = next_offset
            elif value_type == b"Grup":
                if end - offset < 16:
                    self.error("XJU006", f"truncated Grup header at byte {offset}")
                    return end
                payload_length = struct.unpack_from(">I", self.data, offset + 8)[0]
                group_id = struct.unpack_from(">I", self.data, offset + 12)[0]
                terminator = offset + 12 + payload_length
                if terminator + 12 > end:
                    self.error("XJU007", f"Grup record at byte {offset} exceeds its container")
                    return end
                if depth >= self.MAX_GROUP_DEPTH:
                    self.error(
                        "XJU010",
                        f"Grup record at byte {offset} nests deeper than "
                        f"{self.MAX_GROUP_DEPTH} levels",
                    )
                    return end
                self.parse_stream(offset + 16, terminator, depth + 1)
                end_tag = self.data[terminator : terminator + 8]
                end_id = struct.unpack_from(">I", self.data, terminator + 8)[0]
                if end_tag != b"EndGInt ":
                    self.error(
                        "XJU008",
                        f"Grup record at byte {offset} has invalid terminator {end_tag!r}",
                    )
                if end_id != group_id:
                    self.error(
                        "XJU009",
                        f"Grup record at byte {offset} ends with ID {end_id}, expected {group_id}",
                    )
                offset = terminator + 12
            else:
                self.warning(
                    "XJU101",
                    f"unknown UI-state value type {value_type!r} at byte {offset}; remaining bytes not parsed",
                )
                self.unsupported = True
                return end
        return offset


def validate_uistate(path: Path) -> list[Diagnostic]:
    try:
        data = path.read_bytes()
    except OSError as exc:
        return [diagnostic(path, "XJC001", f"cannot read file: {exc}")]
    if not data:
        return []
    parser = UIStateParser(path, data)
    parser.parse_stream(0, len(data))
    return parser.diagnostics


def safe_archive_name(name: str) -> bool:
    pure = PurePosixPath(name)
    return not pure.is_absolute() and ".." not in pure.parts


def validate_library(path: Path, *, warn_unknown: bool) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    if not zipfile.is_zipfile(path):
        return [diagnostic(path, "XJL001", ".xojo_library is not a ZIP archive")]
    try:
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
            for name in names:
                if not safe_archive_name(name):
                    diagnostics.append(
                        diagnostic(path, "XJL002", f"unsafe archive path {name!r}")
                    )
            info_names = [name for name in names if name.endswith("/LibraryInfo.json")]
            if len(info_names) != 1:
                diagnostics.append(
                    diagnostic(
                        path,
                        "XJL003",
                        f"expected one LibraryInfo.json, found {len(info_names)}",
                    )
                )
            else:
                try:
                    metadata = json.loads(archive.read(info_names[0]).decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                    diagnostics.append(
                        diagnostic(path, "XJL004", f"invalid LibraryInfo.json: {exc}")
                    )
                else:
                    if not isinstance(metadata, dict):
                        diagnostics.append(
                            diagnostic(path, "XJL005", "LibraryInfo.json root is not an object")
                        )
            api_names = [name for name in names if "/API/" in name and name.endswith(".xojo_code")]
            if not api_names:
                diagnostics.append(
                    diagnostic(
                        path,
                        "XJL101",
                        "library has no API .xojo_code files in the observed layout",
                        severity="warning",
                    )
                )
            for name in api_names:
                try:
                    text = archive.read(name).decode("utf-8")
                except UnicodeDecodeError as exc:
                    diagnostics.append(
                        diagnostic(path, "XJL006", f"{name}: invalid UTF-8: {exc}")
                    )
                    continue
                virtual = Path(f"{path}!/{name}")
                _, nested = parse_tag_tokens(virtual, text, warn_unknown=warn_unknown)
                diagnostics.extend(nested)
    except (OSError, zipfile.BadZipFile) as exc:
        diagnostics.append(diagnostic(path, "XJL007", f"cannot read library archive: {exc}"))
    return diagnostics


def validate_file(
    path: Path,
    *,
    warn_unknown: bool,
    check_paths: bool,
) -> list[Diagnostic]:
    extension = extension_for(path)
    if extension not in SUPPORTED_EXTENSIONS:
        if is_xojo_extension(path) and warn_unknown:
            description = KNOWN_OPAQUE_EXTENSIONS.get(extension)
            if description:
                code = "XJC102"
                message = (
                    f"recognized {description} format {path.suffix}; "
                    "not covered by this validator and skipped as opaque"
                )
            else:
                code = "XJC103"
                message = (
                    f"unknown {path.suffix} format; skipped as a future/opaque format"
                )
            return [
                diagnostic(
                    path,
                    code,
                    message,
                    severity="warning",
                )
            ]
        return []
    if extension == ".xojo_resources":
        return validate_resources(path)
    if extension == ".xojo_uistate":
        return validate_uistate(path)
    if extension == ".xojo_library":
        return validate_library(path, warn_unknown=warn_unknown)

    document, diagnostics = read_text_document(path)
    if document is None:
        return diagnostics
    diagnostics.extend(validate_common_text(path, document))
    if extension == ".xojo_project":
        diagnostics.extend(validate_project(path, document, check_paths=check_paths))
    elif extension in TAGGED_EXTENSIONS:
        diagnostics.extend(
            validate_tagged_text(path, document, warn_unknown=warn_unknown)
        )
    elif extension == ".xojo_database_connection":
        diagnostics.extend(validate_begin_blocks(path, document.text))
    return diagnostics


def split_line_ending(line: str) -> tuple[str, str]:
    if line.endswith("\r\n"):
        return line[:-2], "\r\n"
    if line.endswith("\n") or line.endswith("\r"):
        return line[:-1], line[-1]
    return line, ""


# The formatter must split only on real line endings. str.splitlines also
# splits on form feeds and the Unicode separators, which the IDE treats as
# ordinary characters inside a line; splitting there would rewrite content.
LINE_BOUNDARY_RE = re.compile(r"\r\n|\n|\r")


def split_lines_keepends(text: str) -> list[str]:
    lines: list[str] = []
    start = 0
    for match in LINE_BOUNDARY_RE.finditer(text):
        lines.append(text[start : match.end()])
        start = match.end()
    if start < len(text):
        lines.append(text[start:])
    return lines


def split_logical_lines(text: str) -> list[str]:
    parts = LINE_BOUNDARY_RE.split(text)
    if parts and parts[-1] == "":
        parts.pop()
    return parts


def source_minimum_indent(tag_stack: Sequence[str]) -> int | None:
    if tag_stack and tag_stack[-1] in SOURCE_BODY_TAGS:
        return len(tag_stack)
    return None


def format_manifest(text: str) -> str:
    formatted: list[str] = []
    for line in split_lines_keepends(text):
        body, ending = split_line_ending(line)
        if "=" in body:
            key, value = body.lstrip().split("=", 1)
            if KEY_RE.fullmatch(key.strip()):
                body = f"{key.strip()}={value.rstrip()}"
        formatted.append(body + ending)
    return "".join(formatted)


def format_tagged_text(text: str, *, source_indent: bool) -> str:
    formatted: list[str] = []
    stack: list[str] = []
    closing_kinds = closing_end_kinds(split_logical_lines(text))
    for line in split_lines_keepends(text):
        body, ending = split_line_ending(line)
        match = TAG_RE.match(body)
        if match:
            tag_body = match.group("body")
            end_match = END_TAG_RE.match(tag_body)
            if end_match:
                opener = stack[-1] if stack else end_match.group("kind")
                depth = (
                    0
                    if opener in OUTDENTED_METADATA_TAGS
                    else max(0, len(stack) - 1)
                )
                body = "\t" * depth + f"#tag End{opener}"
                if stack:
                    stack.pop()
            else:
                kind_match = TAG_KIND_RE.match(tag_body)
                if kind_match:
                    kind = kind_match.group("kind")
                    # Xojo's serializer uniquely capitalizes the localized
                    # constant records as `#Tag Instance`.
                    marker = "#Tag" if kind == "Instance" else "#tag"
                    depth = 0 if kind in OUTDENTED_METADATA_TAGS else len(stack)
                    body = "\t" * depth + marker + " " + tag_body.rstrip()
                    if not is_standalone_tag(kind, closing_kinds):
                        stack.append(kind)
            formatted.append(body + ending)
            continue

        minimum = source_minimum_indent(stack) if source_indent else None
        if minimum is not None and body.strip():
            prefix = re.match(r"^[ \t]*", body).group(0)
            tab_count = len(prefix) - len(prefix.lstrip("\t"))
            if tab_count < minimum:
                body = "\t" * minimum + body.lstrip(" \t")
        formatted.append(body + ending)
    return "".join(formatted)


def apply_line_policy(text: str, options: FormatOptions) -> str:
    if options.line_ending != "preserve":
        ending = "\n" if options.line_ending == "lf" else "\r\n"
        had_final = text.endswith(("\n", "\r"))
        logical = split_logical_lines(text)
        text = ending.join(logical)
        if had_final:
            text += ending
    if options.final_newline != "preserve":
        if options.line_ending == "crlf":
            ending = "\r\n"
        elif options.line_ending == "lf":
            ending = "\n"
        elif "\r\n" in text:
            ending = "\r\n"
        else:
            ending = "\r" if "\r" in text else "\n"
        if options.final_newline == "add":
            # Only append a missing line break; an empty file stays empty and
            # existing trailing blank lines are left alone.
            if text and not text.endswith(("\n", "\r")):
                text += ending
        else:
            text = text.rstrip("\r\n")
    return text


def format_document(path: Path, document: TextDocument, options: FormatOptions) -> bytes:
    extension = extension_for(path)
    text = document.text
    if extension == ".xojo_project":
        text = format_manifest(text)
    elif extension in TAGGED_EXTENSIONS:
        text = format_tagged_text(text, source_indent=options.source_indent)
    text = apply_line_policy(text, options)
    payload = text.encode("utf-8")
    return (b"\xef\xbb\xbf" if document.bom else b"") + payload


def iter_files(paths: Sequence[Path], *, include_unknown: bool) -> Iterator[Path]:
    seen: set[Path] = set()
    for supplied in paths:
        path = supplied.expanduser()
        if path.is_file():
            resolved = path.resolve()
            if resolved not in seen:
                seen.add(resolved)
                yield resolved
            continue
        if not path.exists():
            yield path
            continue
        for root, directories, filenames in os.walk(path):
            directories[:] = sorted(name for name in directories if name != ".git")
            for filename in sorted(filenames):
                candidate = Path(root) / filename
                if extension_for(candidate) in SUPPORTED_EXTENSIONS or (
                    include_unknown and is_xojo_extension(candidate)
                ):
                    resolved = candidate.resolve()
                    if resolved not in seen:
                        seen.add(resolved)
                        yield resolved


def render_diagnostic(item: Diagnostic) -> str:
    theme = help_theme(LINT_COLOR_ENV)
    if item.severity == "error":
        severity = theme.error(item.severity)
    elif item.severity == "notice":
        severity = theme.dim(item.severity)
    else:
        severity = theme.accent(item.severity)
    return (
        f"{display_path(item.path)}:{item.line}:{item.column}: "
        f"{severity} {item.code} {item.message}"
    )


def check_command(args: argparse.Namespace) -> int:
    paths = [Path(value) for value in (args.paths or ["."])]
    warn_unknown = args.warn_unknown or args.all_checks
    check_paths = args.check_paths or args.all_checks
    diagnostics: list[Diagnostic] = []
    for path in iter_files(paths, include_unknown=warn_unknown):
        if not path.exists():
            diagnostics.append(diagnostic(path, "XJC005", "path does not exist"))
            continue
        diagnostics.extend(
            validate_file(
                path,
                warn_unknown=warn_unknown,
                check_paths=check_paths,
            )
        )
    if args.no_notices:
        diagnostics = [item for item in diagnostics if item.severity != "notice"]
    diagnostics.sort(key=Diagnostic.sort_key)
    for item in diagnostics:
        print(render_diagnostic(item))
    errors = sum(item.severity == "error" for item in diagnostics)
    warnings = sum(item.severity == "warning" for item in diagnostics)
    notices = sum(item.severity == "notice" for item in diagnostics)
    if diagnostics and not args.quiet_summary:
        summary = f"Found {errors} error(s), {warnings} warning(s)"
        if notices:
            summary += f", {notices} notice(s)"
        print(summary + ".", file=sys.stderr)
    return 1 if errors or (args.warnings_as_errors and warnings) else 0


def unified_diff(path: Path, before: bytes, after: bytes) -> str:
    before_text = before.decode("utf-8", errors="replace").splitlines(keepends=True)
    after_text = after.decode("utf-8", errors="replace").splitlines(keepends=True)
    return "".join(
        difflib.unified_diff(
            before_text,
            after_text,
            fromfile=str(path),
            tofile=str(path),
        )
    )


def format_command(args: argparse.Namespace) -> int:
    paths = [Path(value) for value in (args.paths or ["."])]
    options = FormatOptions(args.line_ending, args.final_newline, not args.no_source_indent)
    changed = 0
    errors = 0
    for path in iter_files(paths, include_unknown=False):
        if not path.exists():
            print(render_diagnostic(diagnostic(path, "XJC005", "path does not exist")))
            errors += 1
            continue
        if extension_for(path) not in TEXT_EXTENSIONS:
            continue
        document, diagnostics = read_text_document(path)
        if document is None:
            for item in diagnostics:
                print(render_diagnostic(item))
            errors += 1
            continue
        structural = validate_file(path, warn_unknown=False, check_paths=False)
        structural_errors = [item for item in structural if item.severity == "error"]
        if structural_errors:
            for item in structural_errors:
                print(render_diagnostic(item))
            errors += len(structural_errors)
            continue
        output = format_document(path, document, options)
        if output == document.raw:
            continue
        changed += 1
        if args.diff:
            sys.stdout.write(unified_diff(path, document.raw, output))
        elif args.check:
            print(
                render_diagnostic(
                    diagnostic(
                        path,
                        "XJF001",
                        "file would be reformatted",
                        severity="warning",
                    )
                )
            )
        else:
            # Write-then-replace so a failed write never truncates the file.
            real = os.path.realpath(path)
            tmp = real + ".part"
            try:
                # A read-only target must fail closed (XJF002), not be
                # silently replaced by a writable copy.
                if not os.access(real, os.W_OK):
                    raise PermissionError(f"'{real}' is not writable")
                with open(tmp, "wb") as handle:
                    handle.write(output)
                os.chmod(tmp, stat.S_IMODE(os.stat(real).st_mode))
                os.replace(tmp, real)
            except OSError as exc:
                print(
                    render_diagnostic(
                        diagnostic(path, "XJF002", f"cannot write formatted file: {exc}")
                    )
                )
                errors += 1
            finally:
                # After a successful replace the temp is gone; anything else
                # -- including an interrupt -- must not leave a .part behind.
                try:
                    os.remove(tmp)
                except OSError:
                    pass
    if not args.check and not args.diff and changed and not args.quiet_summary:
        print(f"Reformatted {changed} file(s).")
    if (args.check or args.diff) and changed and not args.quiet_summary:
        print(f"Would reformat {changed} file(s).", file=sys.stderr)
    return 1 if errors or ((args.check or args.diff) and changed) else 0


def build_parser() -> LintParser:
    parser = LintParser(
        prog=LINT_PROG,
        description="Validate, lint, and conservatively format Xojo Project files.",
        add_help=False,
    )
    parser.add_argument("-h", "--help", action="help", help="show help for a command")
    subparsers = parser.add_subparsers(
        dest="command",
        metavar="<command>",
        parser_class=LintParser,
    )

    check = subparsers.add_parser(
        "check",
        help=LINT_COMMAND_BLURBS["check"],
        description=(
            "Validate Xojo Project containers and relationships without rejecting "
            "unknown properties introduced by newer IDE versions."
        ),
        add_help=False,
    )
    check.command_name = "check"
    check.add_argument(
        "paths",
        nargs="*",
        metavar="PATH",
        help="file or directory to check; defaults to the current directory",
    )
    check.add_argument(
        "--all",
        dest="all_checks",
        action="store_true",
        help="enable all optional checks (equivalent to --warn-unknown --check-paths)",
    )
    check.add_argument(
        "--warn-unknown",
        action="store_true",
        help="warn about unknown tag kinds and unsupported .xojo_* extensions",
    )
    check.add_argument(
        "--check-paths",
        action="store_true",
        help="also warn when external asset paths in manifests do not exist",
    )
    check.add_argument(
        "--warnings-as-errors",
        action="store_true",
        help="return a failing exit status when warnings are emitted",
    )
    check.add_argument(
        "--no-notices",
        action="store_true",
        help="suppress notice-level diagnostics; notices never affect the exit status",
    )
    check.add_argument(
        "--quiet-summary",
        action="store_true",
        help="suppress the final error and warning count",
    )
    check.add_argument("-h", "--help", action="help", help="show help for this command")
    check.set_defaults(func=check_command)

    formatter = subparsers.add_parser(
        "format",
        help=LINT_COMMAND_BLURBS["format"],
        description=(
            "Conservatively repair serialization indentation and whitespace in "
            "text-based Xojo Project files."
        ),
        add_help=False,
    )
    formatter.command_name = "format"
    formatter.add_argument(
        "paths",
        nargs="*",
        metavar="PATH",
        help="file or directory to format; defaults to the current directory",
    )
    output_mode = formatter.add_mutually_exclusive_group()
    output_mode.add_argument(
        "--check", action="store_true", help="report files that would change"
    )
    output_mode.add_argument(
        "--diff", action="store_true", help="print a unified diff without writing"
    )
    formatter.add_argument(
        "--line-ending",
        choices=("preserve", "lf", "crlf"),
        default="preserve",
        help="line-ending policy (default: preserve)",
    )
    formatter.add_argument(
        "--final-newline",
        choices=("preserve", "add", "remove"),
        default="add",
        help="final-newline policy (default: add a missing final line break; "
        "preserve to skip)",
    )
    formatter.add_argument(
        "--no-source-indent",
        action="store_true",
        help="do not repair missing minimum indentation inside source tags",
    )
    formatter.add_argument(
        "--quiet-summary",
        action="store_true",
        help="suppress the final reformatted-file count",
    )
    formatter.add_argument(
        "-h", "--help", action="help", help="show help for this command"
    )
    formatter.set_defaults(func=format_command)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    values = list(sys.argv[1:] if argv is None else argv)
    parser = build_parser()
    if not values:
        parser.print_help()
        return 0
    if values[0] in LINT_COMMAND_BLURBS:
        parser.command_name = values[0]
    args = parser.parse_args(values)
    if not hasattr(args, "func"):
        parser.error("no command given")
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
