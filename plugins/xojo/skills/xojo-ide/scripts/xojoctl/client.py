"""Client."""

from __future__ import annotations

import secrets
import socket
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

from .constants import *  # noqa: F401,F403
from .escaping import *  # noqa: F401,F403
from .framing import *  # noqa: F401,F403
from .journal import *  # noqa: F401,F403
from .transport import *  # noqa: F401,F403
from .discovery import *  # noqa: F401,F403
from .classify import *  # noqa: F401,F403


@dataclass
class Exchange:
    tag: str
    script: str
    reply: Optional[Message]
    result: Classification
    strays: List[Message] = field(default_factory=list)
    lost: int = 0
    elapsed: float = 0.0

    @property
    def complete(self) -> bool:
        return self.lost == 0 and self.reply is not None


class Client:
    """A connection to a running Xojo IDE.

    ONE reader thread runs for the connection's lifetime -- started at connect,
    stopped at close, never restarted per command. Stopping the reader at the
    first response is the bug that destroys analysis output in other clients.

    ONE request is in flight at a time, so the journal's Condition IS the
    correlation layer; no pending-tag map is needed.
    """

    def __init__(self, transport: Transport,
                 first_ceiling: float = FIRST_REPLY_CEILING,
                 reply_ceiling: float = REPLY_CEILING,
                 on_hint: Optional[Callable[[str], None]] = None) -> None:
        self._t = transport
        self._journal = Journal()
        self._io = threading.Lock()
        self._nonce = secrets.token_hex(4)
        self._seq = 0
        self._sent_tags: set = set()
        self._claimed_at: Dict[str, float] = {}
        self._warm = False
        self._first_ceiling = first_ceiling
        self._reply_ceiling = reply_ceiling
        self._on_hint = on_hint or (lambda t: None)
        self._reader = threading.Thread(target=self._read_loop,
                                        name="xojoctl-reader", daemon=True)
        self._reader.start()
        # The IDE sends NO acknowledgement to the handshake. Never read here.
        try:
            self._t.send(HANDSHAKE)
        except BaseException:
            # A constructor that raises leaves no object for the caller to
            # close: shut the transport (which also unblocks the reader)
            # and collect the thread before propagating.
            self._t.close()
            self._reader.join(timeout=5.0)
            raise

    @property
    def address(self) -> str:
        return self._t.address

    @property
    def kind(self) -> str:
        return self._t.kind

    def __enter__(self) -> "Client":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def close(self) -> None:
        self._t.close()
        self._reader.join(timeout=5.0)

    def _read_loop(self) -> None:
        framer = Framer()
        err: Optional[BaseException] = None
        try:
            while True:
                try:
                    data = self._t.recv(RECV_CHUNK)
                except (BlockingIOError, InterruptedError):
                    continue
                except socket.timeout as exc:
                    # A deadline-bounded send briefly puts the shared fd in
                    # timed mode; a recv that wakes up empty during that
                    # window is a retry, not a dead socket. But on 3.10+
                    # socket.timeout IS TimeoutError, which a kernel-level
                    # ETIMEDOUT death also maps to -- that one carries an
                    # errno and must still kill the journal.
                    if getattr(exc, "errno", None) is not None:
                        raise
                    continue
                if not data:
                    framer.close()
                    break
                for raw in framer.feed(data):
                    self._journal.append(decode_message(raw))
        except BaseException as exc:            # noqa: BLE001 -- re-raised in waiter
            err = exc
        finally:
            self._journal.shutdown(err)

    def collect_tag(self, tag: str, quiet: float = SPLIT_REPLY_WINDOW
                    ) -> List["Message"]:
        """Every message under `tag`, including any that land moments later.

        The IDE can split one reply across several messages -- a script's Print
        output and a compiler warning arrive separately under the same tag.
        exchange() claims whichever is FIRST, so a caller that reads only that
        one reports the warning as the script's output, or loses the warning,
        depending on a millisecond of ordering.

        Nothing about correlation changes here: the journal already retains
        every message, so this is a read of what was kept, plus a short wait for
        stragglers.
        """
        deadline = time.monotonic() + quiet
        cursor = 0
        found: List["Message"] = []
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return found
            m, cursor, _, _ = self._journal.wait_once(
                cursor, lambda x: x.tag == tag, remaining)
            if m is None:
                # A DEAD connection is not the same as a quiet one. Returning
                # what arrived so far let a sentinel-only analyze reply be
                # judged clean when the IDE had actually dropped the socket
                # before sending its diagnostics.
                self._raise_if_broken()
                return found
            found.append(m)

    def await_sentinel(self, tag: str, value: str,
                       timeout: float = 60.0) -> bool:
        """Block until a trailing Print of `value` arrives under `tag`.

        A build script ends with `Print <sentinel>`, so seeing that sentinel
        proves the script ran to completion -- and, more usefully, that the IDE
        has finished the build and is free again. Merely snapshotting the
        journal after the build reply is a race: the sentinel lands a moment
        later and is sometimes missed, which made completion look intermittent.
        """
        cursor = 0                     # the journal is bounded; scan it all
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return False
            m, cursor, _, _ = self._journal.wait_once(
                cursor,
                lambda x: (x.tag == tag and isinstance(x.envelope, dict)
                           and x.envelope.get("response") == value),
                remaining)
            if m is not None:
                # The sentinel can BE the claimed reply (a build that printed
                # nothing yields one sentinel-only message, which exchange()
                # already labeled "tagged"). Never downgrade that label --
                # raw.messages must keep exactly one tagged entry per
                # exchange, which is the contract consumers use to find the
                # claimed reply.
                if m.channel != "tagged":
                    m.channel = "trailing"
                return True
            if self._journal.closed:
                # A connection that DIED mid-build is a transport failure,
                # not merely an unconfirmed completion: reporting it as
                # "no sentinel" gave exit 4 for a dropped socket.
                self._raise_if_broken()
                return False

    def _raise_if_broken(self) -> None:
        """Turn a journal that closed on an ERROR into a transport failure.

        The reader thread stores whatever killed it. Every waiter has to
        distinguish that from an ordinary quiet period, or a dropped socket
        is reported as a missing reply part instead of a lost connection.
        """
        if self._journal.closed and self._journal.error is not None:
            raise TransportUnavailable(
                "connection failed: %s" % self._journal.error)

    def await_reply_part(self, tag: str, pred: Callable[["Message"], bool],
                         timeout: float) -> Optional["Message"]:
        """Wait up to `timeout` for a same-tag message satisfying `pred`.

        Companion to await_sentinel for the opposite need: a reply part worth
        waiting for (a script's Print output after a compile-time warning)
        rather than one that merely proves completion. Scans the whole
        bounded journal, so a part that already arrived returns immediately.

        The channel label is NOT set here. await_sentinel can label its match
        because it matches one exact sentinel string; an arbitrary predicate
        cannot tell our own trailing output from the IDE reusing a retired
        tag, so record_raw is left to judge it by timing.
        """
        cursor = 0
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return None
            m, cursor, _, _ = self._journal.wait_once(
                cursor, lambda x: x.tag == tag and pred(x), remaining)
            if m is not None:
                return m
            if self._journal.closed:
                # A dead connection is not "no output" -- reporting it as a
                # missing reply part turned a lost IDE into exit 0.
                self._raise_if_broken()
                return None

    def _next_tag(self) -> str:
        self._seq += 1
        tag = "%s-%d" % (self._nonce, self._seq)
        self._sent_tags.add(tag)
        return tag

    def messages(self) -> List[Message]:
        return self._journal.snapshot()

    @property
    def dropped(self) -> int:
        return self._journal.evicted

    @property
    def sent_tags(self) -> set:
        return set(self._sent_tags)

    @property
    def claimed_at(self) -> Dict[str, float]:
        return dict(self._claimed_at)

    def exchange(self, script: str, ceiling: Optional[float] = None) -> Exchange:
        """Send one IDE Script and wait for the reply carrying our tag."""
        with self._io:
            tag = self._next_tag()
            # Cursor taken BEFORE the write so a reply that lands while we are
            # still in sendall() cannot be missed.
            cursor = self._journal.cursor()
            started = time.monotonic()
            if ceiling is None:
                ceiling = self._reply_ceiling if self._warm else self._first_ceiling
            deadline = started + ceiling
            # The deadline bounds the WRITE as well: sendall() to a peer that
            # accepted but stopped reading blocks forever once the kernel
            # buffer fills (~8 KB on macOS AF_UNIX), and no reply ceiling can
            # fire while the send is stuck holding the _io lock.
            self._t.send(encode_request(tag, script), deadline)
            strays: List[Message] = []
            lost = 0
            hinted = False
            while True:
                now = time.monotonic()
                if now >= deadline:
                    raise ReplyTimeout(self._timeout_text(ceiling, script))
                slice_ = deadline - now
                if not hinted:
                    until_hint = HINT_AFTER - (now - started)
                    if until_hint <= 0:
                        hinted = True
                        self._on_hint(self._hint_text(now - started))
                        continue
                    slice_ = min(slice_, until_hint)
                m, cursor, skipped, over = self._journal.wait_once(
                    cursor, lambda x: x.tag == tag, slice_)
                strays.extend(skipped)
                lost += over
                if m is not None:
                    self._warm = True
                    m.channel = "tagged"    # claimed; everything else stays OOB
                    self._claimed_at[tag] = m.at
                    return Exchange(tag, script, m, classify(m), strays, lost,
                                    time.monotonic() - started)
                if self._journal.closed:
                    if self._journal.error is not None:
                        raise TransportUnavailable(
                            "connection failed: %s" % self._journal.error)
                    raise ReplyTimeout(
                        "the IDE closed the connection before replying.\n"
                        "Script was: %r" % script)

    def _hint_text(self, waited: float) -> str:
        if self._warm:
            return ("still waiting (%.0fs). The IDE has answered on this "
                    "connection, so it is warm." % waited)
        return ("still waiting (%.0fs). A cold IDE unpacks its plugins before "
                "servicing anything -- measured at 74s, and it scales with the "
                "machine and plugin set. This is not a hang." % waited)

    def _timeout_text(self, ceiling: float, script: str) -> str:
        head = "no reply after %.0fs.\n" % ceiling
        common = ("The IDE replies ONLY when a script Prints, so a script with no "
                  "output\ncan never reply -- although it did run.")
        if self._warm:
            return head + ("The IDE answered earlier on this connection, so it is "
                           "warm.\n" + common + "\nScript was: %r" % script)
        return head + ("Either the IDE is still cold (plugin unpacking can take "
                       "minutes),\nor " + common + "\nScript was: %r" % script)


__all__ = [
    "Client",
    "Exchange",
]
