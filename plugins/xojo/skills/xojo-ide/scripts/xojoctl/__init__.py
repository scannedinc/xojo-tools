"""xojoctl -- drive a running Xojo IDE over its IDE Communicator socket.

See docs/ for usage; the protocol record lives in protocol_notes.py.
"""

from __future__ import annotations

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
from .connection import *  # noqa: F401,F403
from .commands import *  # noqa: F401,F403
from .cli import *  # noqa: F401,F403

from . import (  # noqa: F401  -- module handles for targeted patching
    constants, escaping, framing, journal, transport, discovery, classify, client, scripts, targets, diagnostics, render, connection, commands, cli,
)

_MODULES = (constants, escaping, framing, journal, transport, discovery, classify, client, scripts, targets, diagnostics, render, connection, commands, cli)
