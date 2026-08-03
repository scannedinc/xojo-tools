"""A minimal keep-alive HTTP client on the standard library.

Just enough for this skill's needs -- streaming GET, HEAD, per-request
headers, timeouts, and redirects -- without a third-party dependency. One
connection per host is kept open and reused, so a long run of small requests
does not pay a TCP and TLS handshake per file; a stale keep-alive socket is
retried once on a fresh connection.

A connection leaves the pool while its response is open and returns only
once the body is fully read, so two interleaved requests to one host can
never share a socket; the second simply opens its own connection.
"""

from __future__ import annotations

import http.client
import sys
from typing import Iterator, Mapping
from urllib.parse import urljoin, urlsplit

MAX_REDIRECTS = 5
REDIRECT_STATUSES = (301, 302, 303, 307, 308)


class RequestError(OSError):
    """A request failed at the network level."""


class Response:
    """One HTTP response, streamed. Owns its connection until closed."""

    def __init__(self, session: "Session", key: tuple, conn, raw, url: str):
        self._session = session
        self._key = key
        self._conn = conn
        self.raw = raw
        self.url = url
        self.status_code = raw.status
        self.headers = raw.headers

    def __enter__(self) -> "Response":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def iter_content(self, chunk_size: int = 65536) -> Iterator[bytes]:
        try:
            while True:
                chunk = self.raw.read(chunk_size)
                if not chunk:
                    return
                yield chunk
        except (OSError, http.client.HTTPException) as exc:
            self._discard()
            raise RequestError(str(exc) or type(exc).__name__) from exc

    def _discard(self) -> None:
        conn, self._conn = self._conn, None
        if conn is not None:
            conn.close()

    def close(self) -> None:
        """Release the connection: back to the pool when fully read.

        A small unread remainder -- an error page, an empty 304 body -- is
        drained so the connection stays reusable. Abandoning a large body
        costs less as a reconnect than as a read, so that connection is
        closed instead.
        """
        if self._conn is None:
            return
        try:
            if not self.raw.isclosed():
                self.raw.read(65536)
            if self.raw.isclosed():
                conn, self._conn = self._conn, None
                self._session._store(self._key, conn)
            else:
                self.raw.close()
                self._discard()
        except (OSError, http.client.HTTPException):
            self._discard()


class Session:
    """Connections pooled per host, shared default headers, default timeout."""

    def __init__(self, timeout: float = 30.0):
        self.headers: dict[str, str] = {}
        self.timeout = timeout
        self._conns: dict[tuple, http.client.HTTPConnection] = {}

    def __enter__(self) -> "Session":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def get(
        self,
        url: str,
        headers: Mapping[str, str] | None = None,
        timeout: float | None = None,
    ) -> Response:
        return self.request("GET", url, headers, timeout)

    def head(
        self,
        url: str,
        headers: Mapping[str, str] | None = None,
        timeout: float | None = None,
    ) -> Response:
        return self.request("HEAD", url, headers, timeout)

    def request(
        self,
        method: str,
        url: str,
        headers: Mapping[str, str] | None = None,
        timeout: float | None = None,
        _redirects: int = MAX_REDIRECTS,
    ) -> Response:
        split = urlsplit(url)
        if split.scheme not in ("http", "https") or not split.hostname:
            raise RequestError(f"unsupported URL: {url}")
        key = (split.scheme, split.hostname, split.port)
        target = (split.path or "/") + (f"?{split.query}" if split.query else "")
        merged = dict(self.headers)
        merged.update(headers or {})
        timeout = self.timeout if timeout is None else timeout

        # A pooled connection may have been closed by the server since its
        # last use, which surfaces only when the next request is written or
        # read. That one case earns a retry on a fresh connection; a failure
        # on a fresh connection is real and propagates.
        for attempt in (1, 2):
            conn = self._conns.pop(key, None)
            fresh = conn is None
            if fresh:
                cls = (
                    http.client.HTTPSConnection
                    if split.scheme == "https"
                    else http.client.HTTPConnection
                )
                conn = cls(split.hostname, split.port, timeout=timeout)
            elif conn.sock is not None:
                conn.sock.settimeout(timeout)
            try:
                conn.request(method, target, headers=merged)
                raw = conn.getresponse()
            except (OSError, http.client.HTTPException) as exc:
                conn.close()
                if fresh or attempt == 2:
                    raise RequestError(str(exc) or type(exc).__name__) from exc
                continue
            break

        response = Response(self, key, conn, raw, url)
        location = raw.headers.get("Location")
        if raw.status in REDIRECT_STATUSES and location and _redirects > 0:
            response.close()
            return self.request(
                method, urljoin(url, location), headers, timeout, _redirects - 1
            )
        return response

    def _store(self, key: tuple, conn) -> None:
        old = self._conns.pop(key, None)
        if old is not None and old is not conn:
            old.close()
        self._conns[key] = conn

    def close(self) -> None:
        for conn in self._conns.values():
            conn.close()
        self._conns.clear()


if __name__ == "__main__":
    # Not a tool, but exercisable: fetch one URL and report the status line.
    for arg in sys.argv[1:]:
        with Session() as session, session.get(arg) as response:
            size = sum(len(chunk) for chunk in response.iter_content())
            print(response.status_code, arg, f"{size} bytes")
