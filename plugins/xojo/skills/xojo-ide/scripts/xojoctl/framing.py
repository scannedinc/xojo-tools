"""Framing."""

from __future__ import annotations

from typing import List

from .constants import *  # noqa: F401,F403
from .escaping import *  # noqa: F401,F403


class Framer:
    """Incremental NUL framer with a hard size cap.

    Handles both directions: several complete messages in one recv, and one
    message spanning several recvs. NUL cannot occur inside a message (JSON
    renders any embedded NUL as six characters), so a byte split is exact.
    """

    __slots__ = ("_buf", "_cap")

    def __init__(self, cap: int = MAX_MESSAGE_BYTES) -> None:
        self._buf = bytearray()
        self._cap = cap

    def feed(self, data: bytes) -> List[bytes]:
        out: List[bytes] = []
        pos, n = 0, len(data)
        while pos < n:
            i = data.find(NUL, pos)
            if i < 0:
                if len(self._buf) + (n - pos) > self._cap:
                    raise ProtocolError(
                        "unterminated message exceeded the %d byte cap; "
                        "the connection is desynchronised" % self._cap)
                self._buf += data[pos:]
                return out
            if len(self._buf) + (i - pos) > self._cap:
                raise ProtocolError("message exceeded the %d byte cap" % self._cap)
            self._buf += data[pos:i]
            if self._buf:
                out.append(bytes(self._buf))
            self._buf.clear()
            pos = i + 1
        return out

    def close(self) -> None:
        if self._buf:
            raise ProtocolError(
                "connection closed with %d bytes of unterminated data" % len(self._buf))


__all__ = [
    "Framer",
]
