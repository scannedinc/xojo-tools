#!/usr/bin/env python3
"""Mirror the Xojo documentation site and convert it for agent use.

    sync    download https://documentation.xojo.com into assets/
    build   convert assets/ into Markdown and index files in references/

`sync` downloads the release archive Xojo publishes for each documentation
build, and is a cheap no-op when that archive has not changed. With
--live-site it then verifies every page against the live site: the site is a
Sphinx build served by plain Apache, so every file carries a real per-file
ETag and Last-Modified, which `sync` keeps in requests.tsv and replays as
conditional requests.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from urllib.parse import quote, urlsplit

import archive
from helptext import (
    HelpConfig,
    HelpfulParser,
    nonneg_float,
    nonneg_int,
)
from httpclient import RequestError, Session
from progress import Progress, megabytes
from convert import (
    DESCRIPTION_SECTIONS,
    md_path,
    unquote,
    Counter,
    Page,
    Renderer,
    Resolver,
    parse_inventory_labels,
    parse_page,
    summary_flags,
)

BASE_URL = "https://documentation.xojo.com"
SCRIPT_DIR = Path(__file__).resolve().parent
# Both trees live at the skill root, beside scripts/, following the Agent Skill
# layout: assets/ holds the downloaded mirror, references/ the material an agent
# reads. They resolve from the script, not the working directory, so the data
# always lands with the tool that manages it.
SKILL_DIR = SCRIPT_DIR.parent
# Each command owns one subfolder and writes nowhere else, so anything else kept
# in assets/ or references/ -- starter projects, notes -- is never touched.
DEFAULT_ASSETS = SKILL_DIR / "assets" / "documentation.xojo.com"
DEFAULT_REFERENCES = SKILL_DIR / "references" / "documentation"
DEFAULT_ABORT_AFTER = 5
MANIFEST_NAME = "requests.tsv"
# Hand-maintained deprecations the documentation does not state deterministically:
# language keywords, global functions, symbols the current docs no longer describe,
# and notes about semantics that changed alongside a rename.
OVERRIDES = SCRIPT_DIR / "deprecation-overrides.tsv"
MANIFEST_HEADER = ("path", "date", "etag")
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/27.0 Safari/605.1.15"
)
# Retries for the archive HEAD probes and download. The --retries flag governs
# only the per-page live-site pass.
ARCHIVE_RETRIES = 3
SYNC_STATE_NAME = "sync-state.json"

# What a user types from the skill root, which is where assets/ and
# references/ live and therefore where the defaults make sense.
DOCS_PROG = "python3 scripts/docs.py"
DOCS_COLOR_ENV = "XOJO_DOCS_COLOR"

DOCS_COMMAND_BLURBS = {
    "sync": "Download the documentation into assets/",
    "build": "Convert the mirror into Markdown and indexes in references/",
}

DOCS_HELP = HelpConfig(
    prog=DOCS_PROG,
    command_blurbs=DOCS_COMMAND_BLURBS,
    root_examples=(
        "sync",
        "build",
        "sync --live-site",
    ),
    command_examples={
        "sync": (
            "sync",
            "sync --force-archive",
            "sync --live-site --delay 0.5",
            "sync ~/xojo-mirror",
        ),
        "build": (
            "build",
            "build ~/xojo-markdown --source ~/xojo-mirror",
        ),
    },
    learn_more=(
        "The two commands are ordered: sync downloads, then build converts.",
        "Both default to the skill's own assets/ and references/ folders,",
        "wherever you run the script from.",
    ),
    color_env=DOCS_COLOR_ENV,
)


class DocsParser(HelpfulParser):
    """The documentation CLI using the skills' shared help style."""

    help_config = DOCS_HELP


def release_arg(value: str) -> str:
    """A Xojo release like 2026r2, as used in the archive filename."""
    if not re.fullmatch(r"\d{4}r\d+", value.strip()):
        raise argparse.ArgumentTypeError(f"expected a release like 2026r2, got {value!r}")
    return value.strip()


def pos_float(value: str) -> float:
    """A timeout of 0 would put every socket in non-blocking mode."""
    number = float(value)
    if number <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return number

# Site-level artifacts that are not listed in objects.inv. objects.inv is what
# enumerates the pages, so it is fetched first.
SITE_FILES = [
    "objects.inv",
    "llms.txt",
    "llms-full.txt",
]

# Apache's mod_deflate appends "-gzip" to the ETag when it compresses a
# response, but validates If-None-Match against the *uncompressed* tag, so
# echoing the suffixed value back never matches and every page re-downloads
# (Apache bug 45023). Record what the server sent; strip the suffix on replay.
GZIP_ETAG_SUFFIX = re.compile(r'-gzip("?)$')

NEW, UNCHANGED, MISSING, FAILED = "new", "unchanged", "missing", "failed"

# Pages `build` leaves out by default. `sync` still mirrors them, so the local
# copy of the site stays complete; these are simply not worth converting.
DEFAULT_EXCLUDES = (
    "404",           # the site's own not-found page
    "_Unpublished/",  # drafts, linked from nowhere
    "espanol/",      # Spanish translations of pages that exist in English
    "fine_print/",   # license and trademark boilerplate, not reference material
    "fullsearch",    # a raw HTML search widget, no prose
    "whitesands",    # a scratch page of docutils sample markup
)


class SyncAborted(RuntimeError):
    """Raised when the server stops answering and retrying is not helping."""


# ==========================================================================
# sync
# ==========================================================================


def make_session() -> Session:
    session = Session()
    session.headers["User-Agent"] = USER_AGENT
    return session


def local_path(root: Path, url: str) -> Path:
    """Where a fetched URL is stored.

    Keys are full URLs so the manifest can describe more than one host, but the
    on-disk name is the *decoded* path: the archive from files.xojo.com ships
    `+.rst.txt`, and a mirror that also wrote `%2B.rst.txt` would hold the same
    page twice.
    """
    return root / unquote(urlsplit(url).path).lstrip("/")


def safe_docnames(docnames: list[str]) -> list[str]:
    """Drop inventory entries that would escape the mirror root.

    A docname is joined onto a filesystem path and written to; the archive
    import rejects the same shape ("unsafe path in archive"), and the
    live-site path has to as well, or a hostile objects.inv writes outside
    the mirror.
    """
    safe = []
    for name in docnames:
        if (name.startswith("/") or "\\" in name
                or ".." in PurePosixPath(name).parts):
            print(f"  ignoring unsafe path in inventory: {name!r}", file=sys.stderr)
            continue
        safe.append(name)
    return safe


class Manifest:
    """url -> (date, etag), persisted as a tab-separated file."""

    def __init__(self, path: Path):
        self.path = path
        self.entries: dict[str, tuple[str, str]] = {}
        self.dirty = False
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        with self.path.open(encoding="utf-8") as handle:
            for lineno, line in enumerate(handle, 1):
                line = line.rstrip("\n")
                if not line:
                    continue
                fields = line.split("\t")
                if len(fields) != 3:
                    print(f"  warning: {self.path}:{lineno} malformed, ignored", file=sys.stderr)
                    continue
                if lineno == 1 and tuple(fields) == MANIFEST_HEADER:
                    continue
                self.entries[fields[0]] = (fields[1], fields[2])

    def get(self, path: str) -> tuple[str, str] | None:
        return self.entries.get(path)

    def set(self, path: str, date: str, etag: str) -> None:
        self.entries[path] = (date, etag)
        self.dirty = True

    def remove(self, path: str) -> None:
        if self.entries.pop(path, None) is not None:
            self.dirty = True

    def save(self) -> None:
        if not self.dirty:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".part")
        with tmp.open("w", encoding="utf-8") as handle:
            handle.write("\t".join(MANIFEST_HEADER) + "\n")
            for key in sorted(self.entries):
                date, etag = self.entries[key]
                handle.write(f"{key}\t{date}\t{etag}\n")
        os.replace(tmp, self.path)
        self.dirty = False


class Downloader:
    def __init__(
        self,
        root: Path,
        manifest: Manifest,
        delay: float,
        retries: int,
        timeout: float,
        abort_after: int = DEFAULT_ABORT_AFTER,
        base_url: str = BASE_URL,
        session: Session | None = None,
    ):
        self.root = root
        self.manifest = manifest
        self.delay = delay
        self.retries = retries
        self.timeout = timeout
        self.abort_after = abort_after
        self.base_url = base_url.rstrip("/")
        self.consecutive_failures = 0
        # A Session pools connections, so all 2000+ requests reuse a single
        # keep-alive socket instead of reconnecting (and re-doing the TLS
        # handshake) per file. It also pools per host, so the archive stage can
        # share it.
        self.session = session or make_session()
        self._last_request = 0.0
        self.counts = {NEW: 0, UNCHANGED: 0, MISSING: 0, FAILED: 0}
        # Set to a Progress while one is drawn, so a missing or failed file is
        # reported without landing on top of the bar. See _log.
        self.progress = None

    def _log(self, text: str, stream=sys.stderr) -> None:
        if self.progress:
            self.progress.log(text, stream)
        else:
            print(text, file=stream)

    def _throttle(self) -> None:
        wait = self.delay - (time.monotonic() - self._last_request)
        if wait > 0:
            time.sleep(wait)
        self._last_request = time.monotonic()

    def _conditional_headers(self, url: str, local: Path) -> dict[str, str]:
        # Only replay validators when the local copy is actually on disk --
        # otherwise a 304 would leave us permanently without the file.
        if not local.exists():
            return {}
        entry = self.manifest.get(url)
        if not entry:
            return {}
        date, etag = entry
        if etag:
            return {"If-None-Match": GZIP_ETAG_SUFFIX.sub(r"\1", etag)}
        if date:
            return {"If-Modified-Since": date}
        return {}

    def fetch(self, path: str) -> str:
        """Fetch one path, tallying the outcome and tripping the abort guard.

        A file that cannot be fetched is reported and skipped; the sync keeps
        going, and because no manifest entry is written the next run retries it.
        But a run of consecutive failures means the server has stopped serving
        us, and grinding through thousands more requests helps nobody, so that
        aborts the sync.
        """
        status = self._fetch(path)
        self.counts[status] += 1

        if status != FAILED:
            self.consecutive_failures = 0
            return status

        self.consecutive_failures += 1
        if self.abort_after and self.consecutive_failures >= self.abort_after:
            raise SyncAborted(
                f"{self.consecutive_failures} files in a row failed after "
                f"{self.retries} retries each with exponential backoff. "
                f"The server has stopped answering. Giving up."
            )
        return status

    def _fetch(self, path: str) -> str:
        # The manifest is keyed by the full URL, so it can describe more than
        # one host. The path is quoted for the request; local_path decodes it
        # again for storage.
        url = f"{self.base_url}/{quote(path)}"
        local = local_path(self.root, url)
        headers = self._conditional_headers(url, local)

        for attempt in range(1, self.retries + 2):
            self._throttle()
            # The body read sits inside the same try as the request: a
            # connection that dies mid-transfer is the same kind of failure
            # as one that dies on connect, and earns the same retry.
            try:
                with self.session.get(
                    url, headers=headers, timeout=self.timeout
                ) as response:
                    if response.status_code == 304:
                        return UNCHANGED
                    if response.status_code == 404:
                        self._log(f"  missing {path}")
                        return MISSING
                    if response.status_code == 429 or response.status_code >= 500:
                        if attempt > self.retries:
                            self._log(f"  failed  {path}: HTTP {response.status_code}")
                            return FAILED
                        self._backoff(attempt, response.headers.get("Retry-After"))
                        continue
                    if response.status_code != 200:
                        self._log(f"  failed  {path}: HTTP {response.status_code}")
                        return FAILED
                    self._write(local, response)
            except RequestError as exc:
                if attempt > self.retries:
                    self._log(f"  failed  {path}: {exc}")
                    return FAILED
                self._backoff(attempt, None)
                continue

            self.manifest.set(
                url,
                response.headers.get("Last-Modified", ""),
                response.headers.get("ETag", ""),
            )
            return NEW

        return FAILED

    def _write(self, local: Path, response) -> None:
        # Write to a sibling .part and rename, so an interrupted transfer never
        # leaves a truncated file that the manifest claims is current.
        local.parent.mkdir(parents=True, exist_ok=True)
        tmp = local.with_name(local.name + ".part")
        try:
            with tmp.open("wb") as handle:
                for chunk in response.iter_content(chunk_size=65536):
                    handle.write(chunk)
            os.replace(tmp, local)
        except BaseException:
            tmp.unlink(missing_ok=True)
            raise

    def _backoff(self, attempt: int, retry_after: str | None) -> None:
        wait = 2.0 ** (attempt - 1)
        if retry_after:
            try:
                wait = max(wait, float(retry_after))
            except ValueError:
                pass
        time.sleep(wait)


def report_inventory_diff(sources: Path, docnames: list[str]) -> None:
    """Say what the inventory gained and lost, without touching either.

    Pages are never deleted: `build` enumerates from objects.inv, so a page
    dropped upstream is already excluded from the output, and leaving the file
    in place means nothing is ever lost to a bad inventory.
    """
    if not sources.is_dir():
        return
    on_disk = {
        p.relative_to(sources).as_posix().removesuffix(".rst.txt")
        for p in sources.rglob("*.rst.txt")
    }
    added = sorted(set(docnames) - on_disk)
    orphans = sorted(on_disk - set(docnames))

    if added:
        print(f"\nNew pages ({len(added)})")
        for docname in added[:20]:
            print(f"  {docname}")
        if len(added) > 20:
            print(f"  ... and {len(added) - 20} more")
    if orphans:
        print(f"\nNo longer in objects.inv ({len(orphans)}), left in place")
        for docname in orphans[:20]:
            print(f"  {docname}")
        if len(orphans) > 20:
            print(f"  ... and {len(orphans) - 20} more")


def mirror_is_usable(root: Path) -> bool:
    """Whether assets/ already holds a complete mirror."""
    inventory, sources = root / "objects.inv", root / "_sources"
    if not inventory.is_file() or not sources.is_dir():
        return False
    try:
        _, docnames = parse_inventory_labels(inventory)
    except Exception:
        return False
    names = {unquote(d) for d in docnames}
    if len(names) < 1000:
        return False
    present = sum(1 for name in names if (sources / f"{name}.rst.txt").is_file())
    return present >= 0.99 * len(names)


def import_archive(
    session: Session, root: Path, manifest: Manifest, args: argparse.Namespace
) -> None:
    """Bring the mirror up to date from the newest release archive.

    The archive is rebuilt upstream from time to time, so its ETag and
    Last-Modified are recorded in the manifest and replayed as a conditional
    request: when the archive has not changed since the last sync, the whole
    step is one request that answers 304 and nothing is written.

    Raises ArchiveError / ArchiveUnavailable; the caller decides whether that
    is fatal. Nothing under `root` is touched until the staged copy validates.
    """
    forced = bool(args.force_archive or args.archive_release)
    current = archive.recorded_release(manifest.entries)
    kw = {"timeout": args.timeout, "retries": ARCHIVE_RETRIES}

    if args.archive_release:
        newest = archive.parse_release(args.archive_release)
        if not archive.probe(session, newest, **kw):
            raise archive.ArchiveError(f"{newest} is not published")
    elif current:
        newest = archive.walk_forward(session, current, **kw)
    else:
        newest = archive.find_newest(session, datetime.now(timezone.utc).year, **kw)

    # Validators are only replayed over a mirror that is really there, so a
    # deleted or gutted mirror can never be "current" by manifest alone.
    conditional: dict[str, str] = {}
    if not forced and mirror_is_usable(root):
        entry = manifest.get(newest.url)
        if entry:
            date, etag = entry
            if etag:
                conditional["If-None-Match"] = GZIP_ETAG_SUFFIX.sub(r"\1", etag)
            elif date:
                conditional["If-Modified-Since"] = date

    print(f"Archive {newest}")

    work = root.with_name(root.name + ".download")
    shutil.rmtree(work, ignore_errors=True)
    staged = work / "staged"
    tgz = work / newest.filename
    work.mkdir(parents=True, exist_ok=True)

    try:
        with Progress("Downloading", 0) as bar:
            seen = [0]

            def progress(received: int, total: int) -> None:
                # download() retries a failed attempt from the beginning, so
                # the count can go backwards; say why rather than let the bar
                # slide back on its own. Content-Length is only known once the
                # response arrives, hence the late total.
                if received < seen[0]:
                    bar.log("  transfer restarted; downloading again from 0%")
                seen[0] = received
                bar.update(received, megabytes(received, total), total=total)

            result = archive.download(
                session, newest, tgz, timeout=args.timeout,
                retries=ARCHIVE_RETRIES, on_progress=progress,
                headers=conditional or None,
            )
        if result is None:
            print(f"  {newest.filename} is unchanged since the last sync\n")
            return
        date, etag = result
        print(f"  downloaded {tgz.stat().st_size // (1024 * 1024)} MB")

        seeded = archive.extract(tgz, staged, BASE_URL)
        archive.validate(staged, parse_inventory_labels)
        copied = archive.merge(staged, root)
        print(f"  imported {copied} files")

        if current and current != newest:
            manifest.remove(current.url)
        for url, value in seeded.items():
            manifest.set(url, *value)
        manifest.set(newest.url, date, etag)
        manifest.save()
    finally:
        shutil.rmtree(work, ignore_errors=True)
    print()


def write_sync_state(root: Path, manifest: Manifest, live_site: bool) -> None:
    """Record when sync last completed, for the skill's periodic refresh check."""
    release = archive.recorded_release(manifest.entries)
    state = {
        "synced": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "release": str(release) if release else None,
        "live_site": live_site,
    }
    path = root / SYNC_STATE_NAME
    path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")


def run_sync(args: argparse.Namespace) -> int:
    root = Path(args.dest).expanduser()
    root.mkdir(parents=True, exist_ok=True)
    manifest = Manifest(root / MANIFEST_NAME)
    session = make_session()
    downloader = Downloader(
        root, manifest, args.delay, args.retries, args.timeout, args.abort_after,
        session=session,
    )

    print(f"Syncing {BASE_URL} -> {root}")
    if args.live_site:
        print(
            f"  delay {args.delay}s, {args.retries} retries, {args.timeout}s "
            f"timeout, abort after {args.abort_after or 'never'}"
        )
    print()

    live_pass = args.live_site
    try:
        import_archive(session, root, manifest, args)
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        manifest.save()
        return 130
    except (archive.ArchiveUnavailable, archive.ArchiveError) as exc:
        reason = (
            "host unreachable"
            if isinstance(exc, archive.ArchiveUnavailable)
            else "unusable"
        )
        print(f"Archive {reason} ({exc}).", file=sys.stderr)
        if not live_pass:
            if mirror_is_usable(root):
                print(
                    "The mirror was left as it is. Re-run sync later, or run "
                    "sync --live-site to update from the live site instead.",
                    file=sys.stderr,
                )
                manifest.save()
                return 1
            print("Bootstrapping from the live site instead.\n", file=sys.stderr)
            live_pass = True
    finally:
        manifest.save()

    if not live_pass:
        write_sync_state(root, manifest, live_site=False)
        print("Mirror is current. Run `build` to refresh references/.")
        return 0

    aborted = False
    try:
        print(f"Site files ({len(SITE_FILES)})")
        for path in SITE_FILES:
            print(f"  {downloader.fetch(path):9} {path}")

        inventory = root / "objects.inv"
        if not inventory.exists():
            print("\nobjects.inv missing: cannot enumerate pages.", file=sys.stderr)
            return 1

        try:
            _, inventory_names = parse_inventory_labels(inventory)
        except Exception as exc:
            print(f"\n{inventory} is unreadable ({exc}). Delete it and re-run "
                  "sync.", file=sys.stderr)
            return 1
        docnames = safe_docnames(sorted({unquote(d) for d in inventory_names}))
        report_inventory_diff(root / "_sources", docnames)

        print(f"\nPages from objects.inv ({len(docnames)})")
        try:
            with Progress("Pages", len(docnames)) as bar:
                downloader.progress = bar
                for index, docname in enumerate(docnames, 1):
                    status = downloader.fetch(f"_sources/{docname}.rst.txt")
                    bar.update(index, f"{index}/{len(docnames)}")
                    if status == NEW:
                        bar.log(f"  updated  {docname}")
                    if index % 100 == 0:
                        manifest.save()
        finally:
            # The bar is gone; later reports print for themselves again.
            downloader.progress = None
    except SyncAborted as exc:
        print(f"\n\nAborted: {exc}", file=sys.stderr)
        aborted = True
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        return 130
    finally:
        manifest.save()

    counts = downloader.counts
    print(
        f"\n{'Aborted' if aborted else 'Done'}. {counts[NEW]} downloaded, "
        f"{counts[UNCHANGED]} unchanged, {counts[MISSING]} missing, "
        f"{counts[FAILED]} failed."
    )
    print(f"Manifest: {manifest.path}")
    if aborted:
        print("Re-run sync to resume; completed files will answer 304.")
        return 2
    if counts[FAILED]:
        return 1
    write_sync_state(root, manifest, live_site=True)
    return 0


# ==========================================================================
# build
# ==========================================================================


def load_overrides() -> dict[str, tuple[str, str, str]]:
    """name -> (deprecated_in, replacement, note)."""
    if not OVERRIDES.exists():
        return {}
    rows: dict[str, tuple[str, str, str]] = {}
    for lineno, line in enumerate(OVERRIDES.read_text(encoding="utf-8").splitlines(), 1):
        fields = line.rstrip("\n").split("\t")
        if lineno == 1 or not line.strip():
            continue
        if len(fields) < 4:
            print(f"  warning: {OVERRIDES.name}:{lineno} needs 4 columns", file=sys.stderr)
            continue
        rows[fields[0]] = (fields[1], fields[2], fields[3])
    return rows


def is_excluded(docname: str, prefixes: tuple[str, ...]) -> bool:
    return any(docname == p or docname.startswith(p) for p in prefixes)


def write_if_changed(path: Path, text: str) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_text(encoding="utf-8") == text:
        return False
    path.write_text(text, encoding="utf-8")
    return True


def join(lines: list[str]) -> str:
    """Collapse runs of blank lines and end with exactly one newline."""
    out: list[str] = []
    for line in lines:
        if not line.strip():
            if out and not out[-1]:
                continue
            out.append("")
        else:
            out.append(line.rstrip())
    while out and not out[0]:
        out.pop(0)
    while out and not out[-1]:
        out.pop()
    return "\n".join(out) + "\n"


def render_page(page: Page, renderer: Renderer) -> str:
    """The small file: prose and summary tables, no per-member detail."""
    title = renderer.inline(page.title, page.docname)
    lines = [f"# {title}", ""]
    if page.kind:
        lines += [f"*{page.kind}*", ""]

    if page.sections:
        # The first section is the page title itself; its body is intro content
        # (for a class, the superclass name) and belongs under the H1, not under
        # a heading of its own.
        intro, rest = page.sections[0], page.sections[1:]
        lines += renderer.block(intro.lines, page.docname)
    else:
        rest = []
        lines += renderer.block(page.preamble, page.docname)

    for section in rest:
        if section.title.strip().lower() in DESCRIPTION_SECTIONS:
            continue
        level = min(max(section.level, 2), 6)
        heading = renderer.inline(section.title, page.docname)
        lines += ["", "#" * level + f" {heading}", ""]
        lines += renderer.block(section.lines, page.docname, base_level=level)

    if page.has_members:
        target = md_path(posixpath_basename(page.docname) + ".members.md")
        lines += [
            "",
            "---",
            "",
            f"[Member details for {title}]({target}) "
            f"({len(page.members)} members)",
        ]
    return join(lines)


def render_members(page: Page, renderer: Renderer) -> str:
    """The large file: one section per member, each with an explicit anchor."""
    base = posixpath_basename(page.docname)
    title = renderer.inline(page.title, page.docname)
    lines = [
        f"# {title} members",
        "",
        f"[← back to {title}]({md_path(base + '.md')})",
        "",
    ]

    by_kind: dict[str, list] = {}
    for member in page.members:
        by_kind.setdefault(member.kind, []).append(member)

    for kind in ("property", "method", "event", "constant", "enumeration"):
        members = by_kind.get(kind)
        if not members:
            continue
        lines += ["", f"## {kind.capitalize()} descriptions", ""]
        for member in members:
            signature = renderer.inline(member.signature, page.docname)
            lines += [
                "",
                f'<a id="{member.anchor}"></a>',
                "",
                f"### {renderer.inline(member.qualified, page.docname)}",
                "",
                f"**{member.name}**{joiner(signature)}",
                "",
            ]
            if member.flags:
                lines += [f"*{member.flags}*", ""]
            lines += renderer.block(member.body, page.docname, base_level=4)

    return join(lines)


def joiner(signature: str) -> str:
    """Method signatures start with "(" and want no space; "As Type" wants one."""
    if not signature:
        return ""
    return signature if signature.startswith("(") else " " + signature


def posixpath_basename(docname: str) -> str:
    return docname.rsplit("/", 1)[-1]


def tsv(path: Path, header: tuple[str, ...], rows: list[tuple[str, ...]]) -> None:
    def clean(value: str) -> str:
        return " ".join(str(value).split())

    text = "\t".join(header) + "\n"
    text += "".join("\t".join(clean(c) for c in row) + "\n" for row in rows)
    write_if_changed(path, text)


def first_sentence(page: Page, renderer: Renderer) -> str:
    for section in page.sections:
        if section.title.strip().lower() != "description":
            continue
        for line in section.lines:
            stripped = line.strip()
            if not stripped or stripped.startswith(".."):
                continue
            text = renderer.inline(stripped, page.docname, plain=True)
            parts = text.split(". ")
            return (parts[0] + ".") if len(parts) > 1 else text
    return ""


def run_build(args: argparse.Namespace) -> int:
    source = Path(args.source).expanduser()
    dest = Path(args.dest).expanduser()
    sources = source / "_sources"
    inventory = source / "objects.inv"

    if not inventory.exists() or not sources.is_dir():
        print(
            f"No mirror at {source}. Run `sync` first.",
            file=sys.stderr,
        )
        return 1

    print(f"Building {source} -> {dest}\n")

    # objects.inv is the authority on which pages exist, not the filesystem.
    # `sync` never deletes, so a page dropped upstream can linger in the mirror;
    # enumerating from the inventory keeps it out of the output.
    try:
        labels, docnames = parse_inventory_labels(inventory)
    except Exception as exc:
        print(f"{inventory} is unreadable ({exc}). Re-run sync.", file=sys.stderr)
        return 1
    docnames = safe_docnames(sorted({unquote(d) for d in docnames}))
    print(f"Parsing {len(docnames)} pages")

    excludes = () if args.include_all else DEFAULT_EXCLUDES
    pages: dict[str, Page] = {}
    skipped = 0
    absent: list[str] = []
    for docname in docnames:
        if is_excluded(docname, excludes):
            skipped += 1
            continue
        file = sources / f"{docname}.rst.txt"
        if not file.is_file():
            absent.append(docname)
            continue
        pages[docname] = parse_page(docname, file.read_text(encoding="utf-8", errors="replace"))

    # Attach kind and flags from each page's summary tables. The tables name
    # their rows with the same :ref: label the description block anchors on,
    # so this join is exact rather than name-matched.
    # A deprecated page names its own replacement. Some are whole classes
    # (ListBox -> DesktopListBox), some are single members with their own page
    # (ListBox.ActiveCell -> DesktopListBox.ActiveTextControl). Index both by
    # the symbol they describe so a member can pick the more specific one.
    replacements: dict[str, tuple[str, str]] = {}
    for docname, page in pages.items():
        if not docname.startswith("api/deprecated/"):
            continue
        page.deprecated = True
        symbol = page.title.removesuffix(" (deprecated)").strip()
        if symbol and (page.deprecated_in or page.replacement):
            replacements[symbol] = (page.deprecated_in, page.replacement)

    for docname, page in pages.items():
        flags = summary_flags(page)
        for member in page.members:
            entry = flags.get(member.anchor)
            if entry:
                member.kind, member.flags = entry[0] or member.kind, entry[1]
            if page.deprecated:
                member.deprecated = True
            if member.deprecated:
                member.flags = ",".join(filter(None, ["deprecated", member.flags]))
                # Most precise first: the member's own page, then its own text,
                # then the blanket notice on the class it belongs to.
                specific = replacements.get(member.qualified)
                if specific and specific[1]:
                    member.deprecated_in, member.replacement = specific
                elif not member.replacement:
                    member.deprecated_in = member.deprecated_in or page.deprecated_in
                    member.replacement = page.replacement

    stats: Counter = Counter()
    renderer = Renderer(Resolver(pages, labels), stats)

    overrides = load_overrides()
    used: set[str] = set()

    def apply_override(name: str, version: str, replacement: str) -> tuple[str, str, str]:
        """Hand-maintained rows win: they fix bad parses as well as fill gaps."""
        row = overrides.get(name)
        if not row:
            return version, replacement, ""
        used.add(name)
        return (row[0] or version, row[1] or replacement, row[2])

    class_rows: list[tuple[str, ...]] = []
    member_rows: list[tuple[str, ...]] = []
    written = 0
    bar = Progress("Converting", len(pages))

    for index, (docname, page) in enumerate(sorted(pages.items()), 1):
        if write_if_changed(dest / f"{docname}.md", render_page(page, renderer)):
            written += 1
        if page.has_members:
            if write_if_changed(dest / f"{docname}.members.md", render_members(page, renderer)):
                written += 1

        title = renderer.inline(page.title, docname, plain=True)
        # The prose-harvested version/replacement describe THIS page only when
        # the page itself is deprecated; a guide that merely quotes someone
        # else's deprecation notice must not gain a deprecated_in of its own.
        version, replacement, note = apply_override(
            title.removesuffix(" (deprecated)").strip(),
            page.deprecated_in if page.deprecated else "",
            page.replacement if page.deprecated else "",
        )
        class_rows.append(
            (
                title,
                page.kind,
                "deprecated" if (page.deprecated or note) else "",
                version,
                replacement,
                note,
                str(len(page.members)),
                f"{docname}.md",
                first_sentence(page, renderer),
            )
        )
        for member in page.members:
            member_rows.append(
                (
                    qualified := renderer.inline(member.qualified, docname, plain=True),
                    member.kind,
                    renderer.inline(member.signature, docname, plain=True),
                    member.flags,
                    *apply_override(qualified, member.deprecated_in, member.replacement),
                    f"{docname}.members.md#{member.anchor}",
                )
            )
        bar.update(index, f"{index}/{len(pages)}")
    bar.clear()

    # A symbol the documentation no longer describes at all still has to be
    # findable -- that is the whole reason the override file exists -- so any
    # row that matched nothing is added rather than dropped. This runs BEFORE
    # the files are written; it once ran after, which reported the rows as
    # added while never writing them.
    added = 0
    for name in sorted(set(overrides) - used):
        version, replacement, note = overrides[name]
        if "." in name:
            member_rows.append((name, "", "", "deprecated", version, replacement, note, ""))
        else:
            class_rows.append((name, "", "deprecated", version, replacement, note, "0", "", ""))
        added += 1

    tsv(
        dest / "classes.tsv",
        ("name", "kind", "flags", "deprecated_in", "replacement", "note", "members", "path", "summary"),
        class_rows,
    )
    tsv(dest / "members.tsv", ("name", "kind", "signature", "flags", "deprecated_in", "replacement", "note", "path"), member_rows)

    print(f"\nDone. {len(pages)} pages, {len(member_rows)} members.")
    if skipped:
        print(f"  {skipped} pages excluded (--include-all keeps them)")
    if absent:
        print(f"  {len(absent)} pages in objects.inv are missing from the mirror; run sync")
        for docname in absent[:5]:
            print(f"    {docname}")
    print(f"  {written} files written or updated")
    print(f"  {dest / 'classes.tsv'}")
    print(f"  {dest / 'members.tsv'}")

    unresolved = renderer.resolver.unresolved
    if unresolved:
        total = sum(unresolved.values())
        print(
            f"\n{total} cross-references had no target page and were rendered as "
            f"plain text ({dict(unresolved)})."
        )

    if overrides:
        print(
            f"\n{len(used)}/{len(overrides)} deprecation overrides annotated an "
            f"existing symbol; {added} added a symbol the docs no longer describe."
        )

    if stats:
        print("\nUnhandled markup (passed through as text):")
        for key, count in stats.most_common(10):
            print(f"  {count:6}  {key}")
    return 0


# ==========================================================================
# CLI
# ==========================================================================


def build_parser() -> argparse.ArgumentParser:
    parser = DocsParser(
        prog="docs.py",
        description="Mirror the Xojo documentation site and convert it for agent use.",
        add_help=False,
    )
    parser.add_argument(
        "-h", "--help", action="help", help="show help for a command"
    )
    sub = parser.add_subparsers(
        dest="command", metavar="<command>", parser_class=DocsParser
    )

    sync = sub.add_parser(
        "sync",
        add_help=False,
        help="download the documentation into assets/",
        description=(
            "Download the latest documentation from Xojo.\n"
            "\n"
            "The documentation lands in assets/ as one archive download, and "
            "a repeat run downloads nothing until the documentation changes "
            "upstream. With --live-site, sync then also checks every page of "
            "the live site, which finds changes newer than the archive; that "
            "pass takes several minutes."
        ),
    )
    sync.add_argument(
        "dest",
        nargs="?",
        default=DEFAULT_ASSETS,
        metavar="PATH",
        help="where to download (default: assets/documentation.xojo.com/)",
    )
    sync.add_argument(
        "--live-site", action="store_true",
        help=(
            "after the archive, also fetch every page from the live site "
            "with conditional requests (slow; several minutes)"
        ),
    )
    sync.add_argument(
        "--force-archive", action="store_true",
        help="download and import the archive even when it is unchanged",
    )
    sync.add_argument(
        "--archive-release", type=release_arg, metavar="YEARrN",
        help="import a specific release, e.g. 2026r1, instead of the newest",
    )
    sync.add_argument(
        "--timeout", type=pos_float, default=30.0, metavar="SECONDS",
        help="per-request timeout (default: 30)",
    )
    sync.add_argument(
        "--delay", type=nonneg_float, default=0.25, metavar="SECONDS",
        help="with --live-site: minimum seconds between page requests (default: 0.25)",
    )
    sync.add_argument(
        "--retries", type=nonneg_int, default=3, metavar="N",
        help=(
            "with --live-site: retries per page on network errors, 429 and "
            "5xx (default: 3)"
        ),
    )
    sync.add_argument(
        "--abort-after", type=nonneg_int, default=DEFAULT_ABORT_AFTER, metavar="N",
        help=(
            "with --live-site: give up once N pages in a row fail every "
            f"retry, e.g. when the server starts refusing requests (default: "
            f"{DEFAULT_ABORT_AFTER}; 0 to never abort)"
        ),
    )
    sync.add_argument("-h", "--help", action="help", help="show this help")
    sync.command_name = "sync"
    sync.set_defaults(func=run_sync)

    build = sub.add_parser(
        "build",
        add_help=False,
        help="convert the mirror into Markdown and index files in references/",
        description=(
            "Build agent-friendly copies of the Xojo documentation.\n"
            "\n"
            "Each synced page becomes two Markdown files: a small one with "
            "the prose and summary tables, and a large one with the "
            "per-member detail. The build also writes the classes.tsv and "
            "members.tsv indexes."
        ),
    )
    build.add_argument(
        "dest",
        nargs="?",
        default=DEFAULT_REFERENCES,
        metavar="PATH",
        help="where to write the output (default: references/documentation/)",
    )
    build.add_argument(
        "--include-all",
        action="store_true",
        help="also convert the pages excluded by default (%s)"
        % ", ".join(DEFAULT_EXCLUDES),
    )
    build.add_argument(
        "--source", default=DEFAULT_ASSETS, metavar="PATH",
        help="the mirror to read (default: assets/documentation.xojo.com/)",
    )
    build.add_argument("-h", "--help", action="help", help="show this help")
    build.command_name = "build"
    build.set_defaults(func=run_build)

    return parser


def main(argv: list[str]) -> int:
    parser = build_parser()
    if not argv:
        parser.print_help()
        return 0
    # An unrecognized flag after a known command is reported by the *root*
    # parser, so point its usage line at that command before parsing.
    if argv[0] in DOCS_COMMAND_BLURBS:
        parser.command_name = argv[0]
    args = parser.parse_args(argv)
    if not getattr(args, "command", None):
        parser.print_help()
        return 0
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
