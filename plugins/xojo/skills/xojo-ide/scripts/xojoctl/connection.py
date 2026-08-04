"""Connection helper."""

from __future__ import annotations

import argparse
import contextlib
import os
import sys
from typing import List, Optional

from .constants import *  # noqa: F401,F403
from .escaping import *  # noqa: F401,F403
from .framing import *  # noqa: F401,F403
from .journal import *  # noqa: F401,F403
from .transport import *  # noqa: F401,F403
from .discovery import *  # noqa: F401,F403
from .classify import *  # noqa: F401,F403
from .client import *  # noqa: F401,F403
from .scripts import *  # noqa: F401,F403
from .targets import *  # noqa: F401,F403
from .diagnostics import *  # noqa: F401,F403
from .render import *  # noqa: F401,F403


def port_from_env() -> Optional[int]:
    """Resolve XOJOCTL_PORT, failing helpfully rather than with a traceback.

    Deliberately NOT evaluated inside build_parser(): a bad value there
    crashed every invocation before argparse even ran -- including offline
    commands like `targets` and `--help` that never open a connection. Read
    at connect time instead, so only commands that would actually use the
    port can fail on it, and they fail through the normal error rendering.
    """
    raw = os.environ.get("XOJOCTL_PORT")
    if raw is None or raw == "":
        return None
    try:
        port = int(raw)
    except ValueError:
        raise XojoError(
            "XOJOCTL_PORT=%r is not a valid port number. "
            "Unset it, or pass --port <port>." % raw)
    if not 1 <= port <= 65535:
        raise XojoError(
            "XOJOCTL_PORT=%r is outside the valid port range 1-65535." % raw)
    return port


def _connect_remedy() -> List[str]:
    """Only suggest things that can actually work on this platform.

    --ipc-name resolves a socket FILE, which exists only on POSIX. On Windows
    the IDE listens on a loopback port found by discovery, so recommending
    --ipc-name there sends people after a flag that is silently ignored.
    """
    steps = ["Make sure the Xojo IDE is running."]
    if IS_WINDOWS:
        steps.append("Pass --port <port> to skip port discovery.")
    else:
        steps.append("If it was launched with XOJO_IPCPATH set, pass "
                     "--ipc-name <name>.")
    return steps


def _stderr_note(text: str) -> None:
    """Best-effort progress line on stderr.

    Progress is advisory: when the consumer of a combined-output pipe has
    already hung up (`2>&1 | head -1`), the write raises BrokenPipeError --
    a ConnectionError, which from inside a command would be reported as a
    lost IDE connection. Dropping the hint is the right outcome; the
    command itself proceeds.

    A closed fd 2 makes sys.stderr None, and print(file=None) writes to
    STDOUT -- which would put progress text inside the JSON document.
    """
    stream = sys.stderr
    if stream is None:
        return
    try:
        print(text, file=stream, flush=True)
    except (BrokenPipeError, ValueError):
        pass


def open_client(args: argparse.Namespace, res: Result) -> Client:
    hint = (lambda t: None) if args.quiet else (
        lambda t: _stderr_note("  %s" % t))
    res.connection = {
        "attempted": True, "connected": False,
        "transport": None, "endpoint": None,
        "ipc_name": None, "port": None,
        "handshake": "not_attempted", "protocol": 2,
    }
    port = getattr(args, "port", None)
    if port is None:
        port = port_from_env()
    if port is None and not IS_WINDOWS:
        name = getattr(args, "ipc_name", None)
        transport = connect_unix(
            name, timeout=args.connect_timeout,
            trust_foreign_owner=getattr(args, "trust_foreign_socket", False),
            on_retry=hint)
        res.connection["ipc_name"] = name or os.environ.get(
            "XOJO_IPCPATH") or DEFAULT_IPC_NAME
    else:
        if port is None:
            # --timeout caps the patient pass as one shared budget, so
            # discovery obeys the same ceiling flag everything else does.
            port = discover_port(patient=args.timeout, on_slow=lambda c: hint(
                "no quick answer from ports %s; the IDE may be cold. Retrying "
                "patiently..." % c))
        transport = connect_tcp(port, timeout=args.connect_timeout)
        res.connection["port"] = port
    client = Client(transport, first_ceiling=args.timeout,
                    reply_ceiling=args.warm_timeout, on_hint=hint)
    # Recorded only after Client() returns: its constructor performs the
    # handshake write, and recording first meant a handshake that died on
    # the wire was still reported as "connected": true, "handshake": "ok".
    res.connection.update({
        "connected": True, "transport": transport.kind,
        "endpoint": transport.address, "handshake": "ok",
    })
    return client


def record_raw(res: Result, client: Client, started: float) -> None:
    """Classify every message into three channels, not two.

    "tagged"   -- the reply an exchange claimed
    "trailing" -- more output from a request WE sent. Expected: a script can
                  emit several messages under one tag, e.g. analyze returns the
                  buildError AND the Print sentinel, same tag, same millisecond.
    "out-of-band" -- a tag we never sent, i.e. genuinely IDE-initiated.

    Only the last is worth telling the user about.
    """
    sent = client.sent_tags
    claimed = client.claimed_at
    msgs = []
    for m in client.messages():
        if m.channel == "out-of-band" and m.tag in sent:
            # Only messages nothing has positively identified are judged by
            # timing here: exchange() labels its claimed reply "tagged" and
            # await_sentinel labels a matched sentinel "trailing", and
            # neither label is second-guessed -- a sentinel await_sentinel
            # accepted minutes later is still OUR sentinel, not an
            # unsolicited event.
            #
            # For the rest, a stale tag alone does NOT mean "ours": the IDE
            # reuses a previously-sent tag for unsolicited messages
            # (verified -- a hand-clicked Analyze came back under an
            # already-retired tag). Timing separates them: real trailing
            # output from one script lands in the same millisecond as the
            # claimed reply, whereas the observed unsolicited message
            # arrived 5.9s later.
            owner = claimed.get(m.tag)
            m.channel = ("trailing" if owner is not None
                         and abs(m.at - owner) <= TRAILING_WINDOW
                         else "out-of-band")
        msgs.append({
            "seq": m.seq,
            "at": _iso_utc(m.at),
            "elapsed_ms": int((m.at - started) * 1000),
            "channel": m.channel,
            "tag": m.tag,
            "reply": m.envelope,
        })
    res.raw = {"messages": msgs, "dropped": client.dropped,
               "truncated": client.dropped > 0}
    if client.dropped:
        res.notes.append(note(Note.RESULT_INCOMPLETE))
    if any(m["channel"] == "out-of-band" for m in msgs):
        res.notes.append(note(Note.UNSOLICITED))


@contextlib.contextmanager
def connected(args: argparse.Namespace, res: Result, started: float):
    """Open a client and ALWAYS record the protocol log on the way out.

    record_raw used to be the last statement inside each command's `with`
    block, so any failure skipped it -- leaving raw.messages empty on
    exactly the outcomes where the journal is the only evidence, and making
    the documented `dropped`/`truncated` reporting unreachable on a failing
    command.
    """
    client = open_client(args, res)
    try:
        yield client
    finally:
        try:
            record_raw(res, client, started)
        except Exception:               # noqa: BLE001 -- never mask the real error
            pass
        client.close()


def project_window_count(client: Client) -> Optional[int]:
    """Number of open workspace windows, or None if it cannot be determined.

    Judged over EVERY message the reply arrived as, not just the claimed one:
    the probe script itself once provoked a compiler warning, which
    the IDE sent as a separate same-tag message. If that warning wins the race,
    the count is in the OTHER message -- reading only the first turned a
    working probe into None.
    """
    ex = client.exchange(script_window_count())
    parts = [classify(m) for m in client.collect_tag(ex.tag)] or [ex.result]
    for cl in parts:
        if cl.verdict is Verdict.OK and cl.text:
            try:
                return int(cl.text.strip())
            except ValueError:
                continue
    return None


def require_project(client: Client, res: Result, action: str) -> None:
    """Refuse to act when no project is open, and say so when several are.

    FAIL CLOSED on an unreadable probe: a None count means the guard could not
    do its job, and proceeding anyway is how "no errors, no warnings" gets
    reported for a project that was never checked (the false-clean class the
    NoProjectOpen docstring forbids).
    """
    count = project_window_count(client)
    res.project["window_count"] = count
    if count == 0:
        raise NoProjectOpen(
            "no project is open in the Xojo IDE, so there is nothing to %s.\n"
            "Open one first:  %s open <path>.xojo_project"
            % (action, INVOCATION))
    if count is None:
        raise ProtocolError(
            "could not determine whether a project is open (the WindowCount "
            "probe returned no usable reply); refusing to %s blind" % action)
    if count > 1:
        res.notes.append(note(Note.AMBIGUOUS_WORKSPACE, window_count=count))


def health_check(client: Client, res: Result) -> None:
    """Prove the peer really is Xojo speaking v2, and warm the connection."""
    ex = client.exchange(script_version())
    if ex.result.verdict is Verdict.OK and ex.result.text:
        # Peer-supplied text that lands in summaries and terminals -- and this
        # is the one exchange that may be talking to something that is NOT a
        # Xojo IDE, which is exactly who would put ANSI or CR here.
        res.ide["version"] = sanitize(ex.result.text).strip()
    elif ex.result.verdict is Verdict.SCRIPT_ERROR:
        raise ProtocolError(
            "the peer rejected a trivial script; it may not be a Xojo IDE")
    if ex.elapsed > HINT_AFTER:
        res.notes.append(note(Note.COLD_START_SLOW))


__all__ = [
    "_connect_remedy",
    "_stderr_note",
    "connected",
    "health_check",
    "open_client",
    "port_from_env",
    "project_window_count",
    "record_raw",
    "require_project",
]
