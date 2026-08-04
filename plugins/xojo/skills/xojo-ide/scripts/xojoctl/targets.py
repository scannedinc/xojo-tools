"""Build targets."""

from __future__ import annotations

import platform
from dataclasses import dataclass, field
from typing import Any, List, Optional, Tuple

from .constants import *  # noqa: F401,F403
from .escaping import *  # noqa: F401,F403
from .framing import *  # noqa: F401,F403
from .journal import *  # noqa: F401,F403
from .transport import *  # noqa: F401,F403
from .discovery import *  # noqa: F401,F403
from .classify import *  # noqa: F401,F403
from .client import *  # noqa: F401,F403
from .scripts import *  # noqa: F401,F403


@dataclass(frozen=True)
class Target:
    value: int
    name: str
    platform: str
    arch: str                # display string
    # Structured facets, so sorting does not have to parse `arch` prose.
    cpu: str = "intel"       # "intel" | "arm" | "multi" (universal / fat)
    bits: Optional[int] = None
    simulator: bool = False  # simulator or emulator rather than real hardware


# Platform display order. Xojo Cloud is where Xojo Web apps deploy, so it takes
# the Web slot; anything unlisted sorts last.
PLATFORM_RANK = {
    "macOS": 0, "Windows": 1, "Linux": 2,
    "iOS": 3, "Android": 4, "Web": 5, "Xojo Cloud": 5,
}

# Architecture precedence WITHIN a platform, applied in this order:
#   1. Intel before ARM, and single-arch before Universal/multi  (this map)
#   2. 32-bit before 64-bit
#   3. real hardware before simulator/emulator
_CPU_RANK = {"intel": 0, "arm": 1, "multi": 2}


def target_sort_key(t: Target) -> Tuple[Any, ...]:
    return (
        PLATFORM_RANK.get(t.platform, 99),
        t.platform,                       # keeps unlisted platforms deterministic
        _CPU_RANK.get(t.cpu, 3),
        t.bits or 0,
        1 if t.simulator else 0,
        t.value,
    )


# BuildApp build targets, transcribed from Xojo's documentation:
# https://documentation.xojo.com/topics/build_automation/ide_scripting/
#   building_commands.html#ide-scripting-building-commands-buildapp
# The `name` column is this tool's own CLI spelling; the value,
# platform, bit-width and architecture come straight from that table.
TARGETS: Tuple[Target, ...] = (
    Target(3,  "windows-386",         "Windows",    "Intel 32-bit",
           "intel", 32),
    Target(4,  "linux-386",           "Linux",      "Intel 32-bit",
           "intel", 32),
    Target(9,  "darwin-universal",    "macOS",      "Universal (Intel & ARM)",
           "multi", 64),
    Target(10, "ios-simulator-arm64", "iOS",        "Simulator ARM 64-bit",
           "arm", 64, True),
    Target(12, "xojo-cloud",          "Xojo Cloud", "Intel 64-bit",
           "intel", 64),
    Target(13, "ios-simulator-x86_64", "iOS",       "Simulator Intel 64-bit",
           "intel", 64, True),
    Target(14, "ios-arm64",           "iOS",        "Device ARM 64-bit",
           "arm", 64),
    Target(16, "darwin-amd64",        "macOS",      "Intel 64-bit",
           "intel", 64),
    Target(17, "linux-amd64",         "Linux",      "Intel 64-bit",
           "intel", 64),
    Target(18, "linux-arm",           "Linux",      "ARM 32-bit",
           "arm", 32),
    Target(19, "windows-amd64",       "Windows",    "Intel 64-bit",
           "intel", 64),
    Target(21, "android-emulator",    "Android",    "Emulator Intel & ARM 64-bit",
           "multi", 64, True),
    Target(23, "android-arm64",       "Android",    "Device ARM 64-bit",
           "arm", 64),
    Target(24, "darwin-arm64",        "macOS",      "ARM 64-bit",
           "arm", 64),
    Target(25, "windows-arm64",       "Windows",    "ARM 64-bit",
           "arm", 64),
    Target(26, "linux-arm64",         "Linux",      "ARM 64-bit",
           "arm", 64),
)


def resolve_target(spec: str) -> Target:
    s = spec.strip().lower()
    if _ascii_digits(s) or (s.startswith("-") and _ascii_digits(s[1:])):
        value = int(s)
        for t in TARGETS:
            if t.value == value:
                return t
        raise ValueError("unknown build target %d" % value)
    for t in TARGETS:
        if s == t.name:
            return t
    raise ValueError(
        "unknown build target %r. Run '%s targets' to list them." % (spec, INVOCATION))


def host_targets() -> List[Target]:
    m = {"Darwin": "macOS", "Linux": "Linux", "Windows": "Windows"}
    want = m.get(platform.system())
    return [t for t in TARGETS if t.platform == want] if want else []


__all__ = [
    "PLATFORM_RANK",
    "TARGETS",
    "Target",
    "_CPU_RANK",
    "host_targets",
    "resolve_target",
    "target_sort_key",
]
