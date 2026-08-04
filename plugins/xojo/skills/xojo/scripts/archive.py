"""Import the Xojo documentation archive from files.xojo.com.

Xojo publishes each release's whole Sphinx build as `Docs<YEAR>r<N>.tgz` -- the
same file the IDE bundles. One request replaces the thousands the live site
needs, and the archive's member timestamps are the values
documentation.xojo.com serves as Last-Modified, so an extracted mirror answers
304 straight away.

The bucket returns 403 for a key that does not exist, never 404, so "not
published" and "cannot reach the host" have to be told apart explicitly.
"""

from __future__ import annotations

import email.utils
import hashlib
import os
import re
import shutil
import tarfile
import time
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from urllib.parse import quote, unquote

from httpclient import RequestError, Response, Session

ARCHIVE_BASE_URL = "https://files.xojo.com/Docs"
# Used only when probing finds nothing at all, e.g. the bucket is reachable but
# empty, or the system clock is years off.
ARCHIVE_FALLBACK = (2026, 2)
# Stop a runaway walk if the bucket ever starts answering 200 to everything:
# caps the releases probed within one year, and the years walked forward.
ARCHIVE_MAX_RELEASE = 12
ARCHIVE_MAX_YEARS = 3
ARCHIVE_URL_RE = re.compile(
    r"^https://files\.xojo\.com/Docs/Docs(\d{4})r(\d+)\.tgz$"
)
# An object store returns "<md5>-<parts>" for a multipart upload, which is a
# hash of hashes and cannot be checked against the file's own MD5.
MULTIPART_ETAG = re.compile(r'-\d+"?$')

# What survives an import. Everything else the archive carries -- rendered HTML,
# _images, _downloads, and the .md files Xojo also ships -- is discarded.
KEEP_PREFIXES = ("_sources/",)
KEEP_FILES = frozenset({"llms-full.txt", "llms.txt", "objects.inv"})

# Room for the archive, the staged extract, and slack.
REQUIRED_FREE_BYTES = 300 * 1024 * 1024


class ArchiveError(RuntimeError):
    """The archive was reached but is unusable."""


class ArchiveUnavailable(RuntimeError):
    """The archive host could not be reached; conclude nothing about releases."""


@dataclass(frozen=True, order=True)
class Release:
    year: int
    number: int

    def __str__(self) -> str:
        return f"{self.year}r{self.number}"

    @property
    def filename(self) -> str:
        return f"Docs{self}.tgz"

    @property
    def url(self) -> str:
        return f"{ARCHIVE_BASE_URL}/{self.filename}"


def parse_release(text: str) -> Release:
    match = re.fullmatch(r"(\d{4})r(\d+)", text.strip())
    if not match:
        raise ValueError(f"expected a release like 2026r2, got {text!r}")
    return Release(int(match.group(1)), int(match.group(2)))


def recorded_release(keys) -> Release | None:
    """The newest release recorded in the manifest, if any."""
    found = [
        Release(int(m.group(1)), int(m.group(2)))
        for m in (ARCHIVE_URL_RE.match(k) for k in keys)
        if m
    ]
    return max(found) if found else None


# --------------------------------------------------------------------------
# Probing
# --------------------------------------------------------------------------


def probe(
    session: Session,
    release: Release,
    timeout: float = 30.0,
    retries: int = 3,
    headers: dict[str, str] | None = None,
) -> Response | None:
    """HEAD one release. None means not published; raises if unreachable."""
    for attempt in range(1, retries + 2):
        try:
            response = session.head(release.url, timeout=timeout, headers=headers)
        except RequestError as exc:
            if attempt > retries:
                raise ArchiveUnavailable(f"{release.url}: {exc}") from exc
            time.sleep(2.0 ** (attempt - 1))
            continue
        response.close()
        if response.status_code in (403, 404):
            return None
        if response.status_code == 200 or response.status_code == 304:
            return response
        if response.status_code == 429 or response.status_code >= 500:
            if attempt > retries:
                raise ArchiveUnavailable(
                    f"{release.url}: HTTP {response.status_code}"
                )
            time.sleep(2.0 ** (attempt - 1))
            continue
        raise ArchiveUnavailable(f"{release.url}: HTTP {response.status_code}")
    raise ArchiveUnavailable(release.url)


def _walk_up(session: Session, year: int, number: int, **kw) -> int:
    while number < ARCHIVE_MAX_RELEASE and probe(
        session, Release(year, number + 1), **kw
    ):
        number += 1
    return number


def find_newest(session: Session, year: int, **kw) -> Release:
    """Newest published release, starting from `year`.

    One year back is enough: it covers January, before that year's r1 has
    shipped. Anything further back means the bucket is broken or the clock is
    wrong, and the fallback covers both.
    """
    for candidate in (year, year - 1):
        if probe(session, Release(candidate, 1), **kw):
            return Release(candidate, _walk_up(session, candidate, 1, **kw))
    return Release(*ARCHIVE_FALLBACK)


def walk_forward(session: Session, current: Release, **kw) -> Release:
    """Newest release at or after `current`, without ever walking backwards."""
    year, number = current.year, _walk_up(session, current.year, current.number, **kw)
    for _ in range(ARCHIVE_MAX_YEARS):
        if not probe(session, Release(year + 1, 1), **kw):
            break
        year += 1
        number = _walk_up(session, year, 1, **kw)
    return Release(year, number)


# --------------------------------------------------------------------------
# Download
# --------------------------------------------------------------------------


def download(
    session: Session,
    release: Release,
    dest: Path,
    timeout: float = 60.0,
    retries: int = 3,
    on_progress=None,
    headers: dict[str, str] | None = None,
) -> tuple[str, str] | None:
    """Fetch one release to `dest`. Returns its (date, etag).

    `headers` may carry If-None-Match or If-Modified-Since validators; a 304
    answer returns None and writes nothing.
    """
    free = shutil.disk_usage(dest.parent).free
    if free < REQUIRED_FREE_BYTES:
        raise ArchiveError(
            f"{free // (1024 * 1024)} MB free at {dest.parent}; "
            f"need about {REQUIRED_FREE_BYTES // (1024 * 1024)} MB"
        )

    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".part")

    for attempt in range(1, retries + 2):
        digest = hashlib.md5()
        received = 0
        try:
            with session.get(release.url, headers=headers, timeout=timeout) as response:
                if response.status_code == 304:
                    return None
                if response.status_code != 200:
                    raise ArchiveUnavailable(
                        f"{release.url}: HTTP {response.status_code}"
                    )
                total = int(response.headers.get("Content-Length", 0))
                with tmp.open("wb") as handle:
                    for chunk in response.iter_content(chunk_size=1 << 16):
                        handle.write(chunk)
                        digest.update(chunk)
                        received += len(chunk)
                        if on_progress:
                            on_progress(received, total)
                date = response.headers.get("Last-Modified", "")
                etag = response.headers.get("ETag", "")
        except ArchiveUnavailable:
            tmp.unlink(missing_ok=True)
            if attempt > retries:
                raise
            time.sleep(2.0 ** (attempt - 1))
            continue
        except RequestError as exc:
            tmp.unlink(missing_ok=True)
            if attempt > retries:
                # Callers are promised ArchiveError/ArchiveUnavailable, so a
                # network-level death mid-download reports as unreachable.
                raise ArchiveUnavailable(f"{release.url}: {exc}") from exc
            time.sleep(2.0 ** (attempt - 1))
            continue

        if etag and not MULTIPART_ETAG.search(etag):
            if digest.hexdigest() != etag.strip('"'):
                tmp.unlink(missing_ok=True)
                if attempt > retries:
                    raise ArchiveError(
                        f"{release.filename}: MD5 does not match the server's ETag"
                    )
                time.sleep(2.0 ** (attempt - 1))
                continue
        os.replace(tmp, dest)
        return date, etag

    raise ArchiveError(f"{release.filename}: download failed")


# --------------------------------------------------------------------------
# Extract, validate, merge
# --------------------------------------------------------------------------


def _wanted(name: str) -> bool:
    return name in KEEP_FILES or name.startswith(KEEP_PREFIXES)


def extract(tgz: Path, staged: Path, base_url: str) -> dict[str, tuple[str, str]]:
    """Unpack the files worth keeping and return manifest rows for them.

    The dates come from `member.mtime`, never from the extracted file's own
    stat(). If the timestamps failed to survive extraction, seeding from disk
    would quietly record "now" for every page, every conditional request would
    answer 200, and the whole mirror would re-download with nothing logged.
    """
    staged.mkdir(parents=True, exist_ok=True)
    seeded: dict[str, tuple[str, str]] = {}

    with tarfile.open(tgz, "r|gz") as tar:
        for member in tar:
            name = member.name.removeprefix("./")
            if not name or not member.isfile() or not _wanted(name):
                continue
            parts = PurePosixPath(name).parts
            # Backslashes are rejected outright: PurePosixPath does not split
            # on them, so `_sources/..\..\evil` would pass the ".." check here
            # and then escape `staged` on a Windows host, where the joined
            # path DOES treat them as separators. No legitimate Sphinx output
            # contains one.
            if name.startswith("/") or "\\" in name or ".." in parts:
                raise ArchiveError(f"unsafe path in archive: {member.name}")

            target = staged / name
            target.parent.mkdir(parents=True, exist_ok=True)
            tmp = target.with_name(target.name + ".part")
            source = tar.extractfile(member)
            if source is None:
                continue
            with source, tmp.open("wb") as handle:
                shutil.copyfileobj(source, handle, 1 << 16)
            os.replace(tmp, target)
            os.utime(target, (member.mtime, member.mtime))
            # Verify the timestamp took, at the moment it can fail: the seeded
            # manifest promises these mtimes, and a filesystem that silently
            # drops them would make every conditional request answer 200.
            if abs(target.stat().st_mtime - member.mtime) > 2:
                raise ArchiveError(f"timestamp did not survive extraction: {name}")

            url = f"{base_url}/{quote(name)}"
            seeded[url] = (email.utils.formatdate(member.mtime, usegmt=True), "")

    return seeded


def validate(staged: Path, parse_inventory) -> None:
    """Refuse to import a partial archive. Runs before assets/ is touched."""
    inventory = staged / "objects.inv"
    if not inventory.is_file():
        raise ArchiveError("archive has no objects.inv")
    if not (staged / "llms.txt").is_file():
        raise ArchiveError("archive has no llms.txt")

    try:
        _, docnames = parse_inventory(inventory)
    except Exception as exc:
        raise ArchiveError(f"objects.inv is unreadable: {exc}") from exc

    names = set(docnames)
    if len(names) < 1000:
        raise ArchiveError(f"objects.inv lists only {len(names)} pages")

    sources = staged / "_sources"
    on_disk = {
        p.relative_to(sources).as_posix().removesuffix(".rst.txt")
        for p in sources.rglob("*.rst.txt")
    }
    if len(on_disk) < 1000:
        raise ArchiveError(f"archive holds only {len(on_disk)} pages")

    decoded = {unquote(n) for n in names}
    difference = len(decoded ^ on_disk)
    if difference > 0.02 * len(decoded):
        raise ArchiveError(
            f"{difference} pages differ between objects.inv and _sources/"
        )

    # Timestamp survival is checked in extract(), against each member's own
    # mtime. A wall-clock check here rejected any archive published within
    # the last hour -- fresh member mtimes are indistinguishable from "the
    # timestamps did not survive" without the archive in hand.


def merge(staged: Path, root: Path) -> int:
    """Copy the staged tree over the mirror. Never deletes anything."""
    copied = 0
    for source in staged.rglob("*"):
        if not source.is_file():
            continue
        target = root / source.relative_to(staged)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        copied += 1
    return copied
