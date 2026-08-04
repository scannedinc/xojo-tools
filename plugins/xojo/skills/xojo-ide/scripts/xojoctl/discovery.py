"""Windows port discovery.

The IDE listens on an unpublished loopback port. It is found from
Xojo.exe's listening ports and confirmed with a nonce probe.
This path is the least exercised of the three transports.
"""

from __future__ import annotations

import json
import re
import secrets
import subprocess
import time
from typing import Callable, List, Optional

from .constants import *  # noqa: F401,F403
from .escaping import *  # noqa: F401,F403
from .framing import *  # noqa: F401,F403
from .journal import *  # noqa: F401,F403
from .transport import *  # noqa: F401,F403


def _run(cmd: List[str], timeout: float = 15.0) -> str:
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, errors="replace",
                           timeout=timeout, creationflags=flags)
        return p.stdout or ""
    except (OSError, subprocess.SubprocessError):
        return ""


def _parse_tasklist(out: str, prefix: str) -> "set":
    pids = set()
    for line in out.splitlines():
        parts = [p.strip().strip('"') for p in line.split('","')]
        if len(parts) >= 2 and parts[0].lower().startswith(prefix):
            try:
                pids.add(int(parts[1]))
            except ValueError:
                pass
    return pids


def xojo_pids(image: str = "Xojo.exe") -> "set":
    pids = _parse_tasklist(
        _run(["tasklist", "/FI", "IMAGENAME eq %s" % image, "/FO", "CSV", "/NH"]),
        image.split(".")[0].lower())
    if not pids:
        # The /FI filter is brittle across locales and against renamed builds.
        pids = _parse_tasklist(_run(["tasklist", "/FO", "CSV", "/NH"]), "xojo")
    return pids


_LOOPBACK = re.compile(r"^(?:127\.\d+\.\d+\.\d+|\[::1\]):(\d+)$")
_WILDCARD = re.compile(r"^(?:0\.0\.0\.0|\[::\]|\*):(?:0|\*)$")


def listening_ports(pids: "set") -> List[int]:
    """Loopback TCP ports listened on by the given PIDs.

    A listening row is identified STRUCTURALLY -- its foreign address is the
    wildcard -- rather than by the literal string "LISTENING", which netstat
    localizes (de-DE prints ABHOEREN).
    """
    ports = set()
    for line in _run(["netstat", "-ano", "-p", "TCP"]).splitlines():
        parts = line.split()
        if len(parts) < 5 or parts[0].upper() != "TCP":
            continue
        local, foreign, pid = parts[1], parts[2], parts[-1]
        if not _WILDCARD.match(foreign):
            continue
        m = _LOOPBACK.match(local)
        if m and pid.isdigit() and int(pid) in pids:
            ports.add(int(m.group(1)))
    return sorted(ports)


def probe_port(port: int, timeout: float, token: str) -> bool:
    """Connect, handshake, and ask for a per-run nonce back. Read-only."""
    try:
        t = connect_tcp(port, min(timeout, CONNECT_TIMEOUT))
    except TransportUnavailable:
        return False
    try:
        tag = "xojoctl-probe-" + token
        t.send(HANDSHAKE)
        t.send(encode_request(tag, "Print " + xojo_string_literal(token)))
        framer = Framer(cap=1 << 20)
        deadline = time.monotonic() + timeout
        while True:
            # The deadline must bound the recv itself, not just the loop: a
            # listener that accepts and then says nothing otherwise blocks
            # recv() forever, and several Xojo-owned listeners that are not
            # the IDE Communicator (debug targets, web previews) behave
            # exactly like that.
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return False
            t.settimeout(remaining)
            try:
                data = t.recv(4096)
            except OSError:            # includes the timeout at the deadline
                return False
            if not data:
                return False
            for raw in framer.feed(data):
                try:
                    env = json.loads(raw.decode("utf-8"))
                except (ValueError, UnicodeDecodeError):
                    continue
                if (isinstance(env, dict) and env.get("tag") == tag
                        and env.get("response") == token):
                    return True
        return False
    except (XojoError, OSError, ValueError):
        return False
    finally:
        t.close()


def discover_port(quick: float = 6.0, patient: float = FIRST_REPLY_CEILING,
                  on_slow: Optional[Callable[[List[int]], None]] = None) -> int:
    started = time.monotonic()
    pids = xojo_pids()
    if not pids:
        raise TransportUnavailable(
            "no Xojo.exe process is running. The IDE must already be running; "
            "xojoctl cannot start it.")
    candidates = listening_ports(pids)
    if not candidates:
        raise TransportUnavailable(
            "Xojo is running (PIDs %s) but owns no loopback TCP listener.\n"
            "The listener does not require an open project, so this usually "
            "means the IDE is still starting up." % sorted(pids))
    token = secrets.token_hex(8)
    # `patient` is the WHOLE discovery budget, quick pass included. A
    # per-port ceiling multiplies: k silent listeners would cost k x the
    # ceiling serially while the failure message claimed one ceiling had
    # elapsed, and the quick pass could overrun a small --timeout on its own.
    deadline = started + patient
    # Several Xojo-owned loopback listeners is normal (debug targets, web
    # previews), so probing all of them is expected rather than anomalous.
    for n, port in enumerate(candidates):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        # Share what is left with the ports still to try. A flat `quick` per
        # port let the FIRST silent listener spend the whole budget, so the
        # real IDE further down the list was never probed at all.
        share = remaining / (len(candidates) - n)
        if probe_port(port, min(quick, share), token):
            return port
    # Nothing answered quickly: exactly what a COLD IDE looks like while it
    # unpacks plugins. Retry patiently rather than declaring failure.
    if on_slow is not None and time.monotonic() < deadline:
        on_slow(candidates)
    # Round-robin an EQUAL SHARE of what is left, so a silent listener that
    # happens to sort first cannot starve the real IDE of its turn.
    while time.monotonic() < deadline:
        round_started = time.monotonic()
        share = (deadline - round_started) / len(candidates)
        for port in candidates:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            if probe_port(port, min(share, remaining), token):
                return port
        if time.monotonic() - round_started < 0.5:
            # Ports that refuse instantly must not busy-spin the loop.
            time.sleep(min(0.25, max(0.0, deadline - time.monotonic())))
    raise TransportUnavailable(
        "none of Xojo's loopback listeners %s answered IDE Communicator v2 "
        "within %.0fs. Pass --port <port> to skip discovery, or raise "
        "--timeout." % (candidates, time.monotonic() - started))


__all__ = [
    "_LOOPBACK",
    "_WILDCARD",
    "_parse_tasklist",
    "_run",
    "discover_port",
    "listening_ports",
    "probe_port",
    "xojo_pids",
]
