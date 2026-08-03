# Security

## Anything that writes to this socket runs code as you

IDE Script includes `DoShellCommand`. Whatever can write to the IDE Communicator socket can run shell commands as the user running the IDE.

**Never pass untrusted input to `xojoctl script`.** Treat the socket itself as a trust boundary.

## How values are escaped

`xojoctl` escapes every value it puts into a script in two layers:

1. Xojo's own quoting, which doubles `"` into `""`. Xojo does **not** use backslash escapes. A backslash there is an ordinary character.
2. A real JSON encoder for the envelope.

The test suite includes an injection payload that tries to break out of a string literal, and asserts it stays inside one.

## Checks on the socket

On macOS and Linux, `xojoctl` checks who owns the socket before it connects, because `/tmp` is world-writable and a socket you do not own may be an impostor.

After connecting, `xojoctl` also compares the listening process's own credentials against yours, where the platform exposes them: `LOCAL_PEERCRED` on macOS and `SO_PEERCRED` on Linux. This closes the gap between the two checks. The IDE recreates the socket path constantly, so the path check and the connect can otherwise see different listeners.

The credential check fails open. If a platform does not expose the information, `xojoctl` connects as before rather than locking you out of your own IDE.

`--trust-foreign-socket` skips both checks.

## What the IDE prints is not trusted text

Everything in a reply is controlled by the IDE and the project, and it ends up in your terminal. Before printing, `xojoctl` removes escape sequences, control characters, and the bidirectional overrides that can visually rewrite a line. The JSON keeps the original text exactly.
