"""Transports."""

from __future__ import annotations

import os
import platform
import re
import socket
import stat
import struct
import sys
import tempfile
import time
from typing import Callable, Optional

from .constants import *  # noqa: F401,F403
from .escaping import *  # noqa: F401,F403
from .framing import *  # noqa: F401,F403
from .journal import *  # noqa: F401,F403


class Transport:
    address = ""
    kind = ""

    def send(self, data: bytes, deadline: Optional[float] = None) -> None:
        raise NotImplementedError
    def recv(self, n: int) -> bytes: raise NotImplementedError
    def settimeout(self, value: Optional[float]) -> None: raise NotImplementedError
    def close(self) -> None: raise NotImplementedError


class _SocketTransport(Transport):
    def __init__(self, sock: socket.socket, address: str, kind: str) -> None:
        self._sock, self.address, self.kind = sock, address, kind

    def send(self, data: bytes, deadline: Optional[float] = None) -> None:
        if deadline is None:
            self._sock.sendall(data)
            return
        # Deadline-bounded write. A BLOCKING send of a large buffer loops
        # inside the kernel until every byte is consumed, and neither
        # select() nor MSG_DONTWAIT bounds it (verified on macOS: select
        # keeps reporting writable and the flag is silently ignored for
        # AF_UNIX), so a timed send is the only real bound. settimeout()
        # flips the SHARED fd non-blocking, which the reader thread can
        # observe mid-recv -- Client._read_loop retries those transient
        # wakeups instead of treating them as a dead socket.
        view = memoryview(data)
        total = len(data)
        attempted = False
        try:
            while view:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    if attempted:
                        raise TransportUnavailable(
                            "the IDE accepted the connection but stopped "
                            "reading from it: %d of %d bytes were still "
                            "unsent at the ceiling. It may be busy or "
                            "wedged; retry when it is idle."
                            % (len(view), total))
                    # A zero ceiling (--timeout 0 means expire immediately)
                    # still gets ONE write attempt: a healthy peer drains a
                    # small request instantly, and ReplyTimeout is the
                    # honest failure for it -- not an accusation that the
                    # IDE stopped reading a request that was never written.
                    remaining = 0.01
                self._sock.settimeout(remaining)
                try:
                    view = view[self._sock.send(view):]
                except socket.timeout:
                    pass    # loop; the deadline check above decides
                attempted = True
        finally:
            self._sock.settimeout(None)

    def recv(self, n: int) -> bytes:
        return self._sock.recv(n)

    def settimeout(self, value: Optional[float]) -> None:
        self._sock.settimeout(value)

    def close(self) -> None:
        try:
            self._sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        try:
            self._sock.close()
        except OSError:
            pass


_IPC_NAME = re.compile(r"^[A-Za-z0-9_]+$")


def unix_socket_path(name: Optional[str] = None) -> str:
    """Resolve an IPC *name* to the socket path the IDE creates."""
    name = name or os.environ.get("XOJO_IPCPATH") or DEFAULT_IPC_NAME
    if os.sep in name or (os.altsep and os.altsep in name):
        return os.path.abspath(os.path.expanduser(name))
    if not _IPC_NAME.match(name):
        raise TransportUnavailable(
            "IPC name %r is invalid; XOJO_IPCPATH accepts only A-Z a-z 0-9 _" % name)
    # /tmp is a symlink to /private/tmp on macOS; connect(2) takes either, but
    # resolving it makes stat() and any path we print the real thing.
    base = "/private/tmp" if sys.platform == "darwin" else "/tmp"
    if not os.path.isdir(base):
        base = tempfile.gettempdir()
    return os.path.join(base, name)


def _no_socket_message(path: str) -> str:
    """An absent socket means the IDE is not running.

    It does NOT mean "no project is open". Older notes said the Windows
    listener existed only while a project workspace was open, but that is no
    longer true: on both Windows and macOS, the
    endpoint is present and answers with every project closed -- `analyze` then
    fails with no_project_open rather than a connection error. Both platforms
    now behave the same way, so this message no longer branches on one.
    """
    return ("no Xojo IDE socket at %s.\n"
            "The Xojo IDE does not appear to be running. It creates this socket;\n"
            "xojoctl only dials it.\n"
            "If the IDE was launched with XOJO_IPCPATH set, pass --ipc-name <name>."
            % path)


def check_socket(path: str, trust_foreign_owner: bool = False) -> None:
    st = os.stat(path)          # caller handles FileNotFoundError
    if not stat.S_ISSOCK(st.st_mode):
        raise TransportUnavailable(
            "%s exists but is not a socket (%s)" % (path, stat.filemode(st.st_mode)))
    geteuid = getattr(os, "geteuid", None)
    if geteuid is not None and st.st_uid != geteuid() and not trust_foreign_owner:
        raise TransportUnavailable(
            "%s is owned by uid %d, not you.\n"
            "/tmp is world-writable, so a socket you do not own may be an impostor --\n"
            "and whatever is on the other end of this protocol gets code execution\n"
            "via DoShellCommand. Pass --trust-foreign-socket only if you know why."
            % (path, st.st_uid))


def _peer_uid(sock: socket.socket) -> Optional[int]:
    """Effective uid of the peer on a connected AF_UNIX socket, or None.

    Fail-open by design: this backs a best-effort impostor check, so any
    platform or ABI surprise returns None rather than blocking a connect.
    check_socket() stats the PATH, but the IDE unlinks and recreates that
    path constantly, so the listener can change between the stat and the
    connect; only the connected peer's credentials close that window.
    macOS: LOCAL_PEERCRED fills struct xucred (version, uid, groups...).
    Linux: SO_PEERCRED fills struct ucred (pid, uid, gid).
    """
    try:
        if sys.platform == "darwin":
            raw = sock.getsockopt(0, 0x0001, 128)   # SOL_LOCAL, LOCAL_PEERCRED
            version, uid = struct.unpack_from("II", raw)
            return uid if version == 0 else None    # XUCRED_VERSION is 0
        if sys.platform.startswith("linux"):
            # 'iII', not '3i': pid_t is signed but uid_t/gid_t are unsigned,
            # and a signed unpack turns uid >= 2^31 (large idmap ranges,
            # nobody=4294967294) negative -- which can never equal geteuid()
            # and would fail-close against the user's own IDE.
            raw = sock.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED,
                                  struct.calcsize("iII"))
            return struct.unpack("iII", raw)[1]
    except (AttributeError, OSError, struct.error):
        return None
    return None


def connect_unix(name: Optional[str] = None, timeout: float = CONNECT_TIMEOUT,
                 retry_for: float = CONNECT_RETRY_SECONDS,
                 trust_foreign_owner: bool = False,
                 on_retry: Optional[Callable[[str], None]] = None) -> Transport:
    """Dial the AF_UNIX socket, retrying across socket churn.

    Finding 4: the IDE unlinks and recreates the socket after a client
    disconnects, so a connect immediately following a previous command commonly
    hits ENOENT or ECONNREFUSED. That is normal, not an error; retry.
    """
    if not hasattr(socket, "AF_UNIX"):
        raise TransportUnavailable(
            "this Python build has no AF_UNIX (CPython does not expose it on "
            "Windows); use --port for the TCP transport instead")
    path = unix_socket_path(name)
    deadline = time.monotonic() + max(retry_for, 0.0)
    announced = False
    last: Optional[str] = None
    while True:
        try:
            check_socket(path, trust_foreign_owner)
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            try:
                sock.connect(path)
            except OSError:
                sock.close()
                raise
            sock.settimeout(None)
            geteuid = getattr(os, "geteuid", None)
            if geteuid is not None and not trust_foreign_owner:
                peer = _peer_uid(sock)
                if peer is not None and peer != geteuid():
                    sock.close()
                    raise TransportUnavailable(
                        "the process listening on %s runs as uid %d, not "
                        "you.\nThe path passed the ownership check, but the "
                        "IDE unlinks and recreates it constantly, so an "
                        "impostor can rebind the name between the check and "
                        "the connect. Pass --trust-foreign-socket only if "
                        "you know why." % (path, peer))
            return _SocketTransport(sock, path, "unix")
        except FileNotFoundError:
            last = _no_socket_message(path)
        except ConnectionRefusedError:
            last = ("the socket at %s exists but nothing is listening.\n"
                    "The IDE recreates this socket after each client disconnects; "
                    "if this persists, the IDE may be busy or wedged." % path)
        except TransportUnavailable:
            raise
        except OSError as exc:
            last = "could not connect to %s: %s" % (path, exc)
        if time.monotonic() >= deadline:
            raise TransportUnavailable(last or "could not connect to %s" % path)
        if not announced and on_retry is not None:
            announced = True
            on_retry("waiting for the Xojo IDE socket (it is recreated between "
                     "connections)...")
        time.sleep(CONNECT_RETRY_INTERVAL)


def connect_tcp(port: int, timeout: float = CONNECT_TIMEOUT) -> Transport:
    last: Optional[Exception] = None
    for family, host in ((socket.AF_INET, "127.0.0.1"), (socket.AF_INET6, "::1")):
        try:
            sock = socket.socket(family, socket.SOCK_STREAM)
        except OSError as exc:
            last = exc
            continue
        sock.settimeout(timeout)
        try:
            sock.connect((host, port))
        # OverflowError: connect() raises it (not OSError) for a port
        # outside 0-65535. The flag and env var are both range-checked, so
        # this is a backstop for any future unvalidated caller.
        except (OSError, OverflowError) as exc:
            last = exc
            sock.close()
            continue
        sock.settimeout(None)
        return _SocketTransport(sock, "%s:%d" % (host, port), "tcp")
    raise TransportUnavailable(
        "could not connect to loopback port %d: %s" % (port, last))


__all__ = [
    "Transport",
    "_IPC_NAME",
    "_SocketTransport",
    "_no_socket_message",
    "_peer_uid",
    "check_socket",
    "connect_tcp",
    "connect_unix",
    "unix_socket_path",
]
