"""Messages and the journal."""

from __future__ import annotations

import collections
import json
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, List, Optional, Tuple

from .constants import *  # noqa: F401,F403
from .escaping import *  # noqa: F401,F403
from .framing import *  # noqa: F401,F403


@dataclass
class Message:
    seq: int
    tag: Optional[str]
    envelope: Any
    raw: bytes
    at: float = field(default_factory=time.time)
    # Default "out-of-band": a message is only "tagged" once an exchange has
    # actually CLAIMED it as the reply it was waiting for. Defaulting to
    # "tagged" mislabels unsolicited messages, which is not hypothetical --
    # the IDE reuses a previously-sent tag for them (see below).
    channel: str = "out-of-band"


def decode_message(raw: bytes) -> Message:
    try:
        env: Any = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        env = None
    tag = env.get("tag") if isinstance(env, dict) else None
    if env is None:
        # A reply that is not valid UTF-8 JSON may still carry OUR tag (tags
        # are ASCII hex this client minted). Salvage it with a lenient pass
        # so the waiting exchange can claim the reply and classify it as
        # "not valid UTF-8 JSON" -- instead of never correlating it and
        # sitting out the whole ceiling to blame a cold IDE. The envelope
        # stays None; only the tag is trusted from the lenient decode.
        try:
            lenient: Any = json.loads(raw.decode("utf-8", errors="replace"))
        except ValueError:
            lenient = None
        if isinstance(lenient, dict) and isinstance(lenient.get("tag"), str):
            tag = lenient["tag"]
    return Message(seq=-1, tag=tag if isinstance(tag, str) else None,
                   envelope=env, raw=raw)


class Journal:
    """Ordered, bounded record of every message the connection produced.

    Correlation is a QUERY over this log rather than a routing decision made at
    receipt time. A message that matched nobody stays visible instead of being
    discarded -- which is what preserves unsolicited IDE events (someone
    clicking Analyze in the IDE) for the raw log.

    Evictions are COUNTED so "we saw no diagnostics" can never be confused with
    "we threw some away".
    """

    def __init__(self, max_messages: int = JOURNAL_MAX_MESSAGES,
                 max_bytes: int = JOURNAL_MAX_BYTES) -> None:
        self._cond = threading.Condition()
        self._items: "collections.deque[Message]" = collections.deque()
        self._max_messages = max_messages
        self._max_bytes = max_bytes
        self._bytes = 0
        self._next_seq = 0
        self._first_seq = 0
        self.evicted = 0
        self.closed = False
        self.error: Optional[BaseException] = None

    def append(self, msg: Message) -> None:
        with self._cond:
            msg.seq = self._next_seq
            self._next_seq += 1
            self._items.append(msg)
            self._bytes += len(msg.raw)
            while ((len(self._items) > self._max_messages
                    or self._bytes > self._max_bytes) and len(self._items) > 1):
                old = self._items.popleft()
                self._bytes -= len(old.raw)
                self._first_seq = old.seq + 1
                self.evicted += 1
            self._cond.notify_all()

    def shutdown(self, error: Optional[BaseException] = None) -> None:
        """Mandatory on every reader exit path, including exceptions.

        Without the notify_all here, a dead socket leaves a waiter sitting out
        its entire ceiling.
        """
        with self._cond:
            self.closed = True
            self.error = error
            self._cond.notify_all()

    def cursor(self) -> int:
        with self._cond:
            return self._next_seq

    def snapshot(self) -> List[Message]:
        with self._cond:
            return list(self._items)

    def wait_once(self, cursor: int, predicate: Callable[[Message], bool],
                  timeout: float) -> Tuple[Optional[Message], int, List[Message], int]:
        """One bounded wait. Returns (match, new_cursor, skipped, overrun)."""
        skipped: List[Message] = []
        with self._cond:
            overrun = 0
            deadline = time.monotonic() + timeout
            while True:
                if cursor < self._first_seq:
                    # Checked every pass, not just on entry: eviction can
                    # also happen while this waiter is parked in wait(), and
                    # a reply evicted then must still be COUNTED, or a
                    # flood turns a received reply into a clean-looking
                    # timeout with lost == 0.
                    overrun += self._first_seq - cursor
                    cursor = self._first_seq
                for m in self._items:
                    if m.seq < cursor:
                        continue
                    cursor = m.seq + 1
                    if predicate(m):
                        return m, cursor, skipped, overrun
                    skipped.append(m)
                if self.closed:
                    return None, cursor, skipped, overrun
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return None, cursor, skipped, overrun
                self._cond.wait(remaining)


__all__ = [
    "Journal",
    "Message",
    "decode_message",
]
