# Platform support

| Platform | Transport | Test status |
|---|---|---|
| macOS | `AF_UNIX` at `/private/tmp/XojoIDE` | Tested against a live IDE |
| Linux | `AF_UNIX` at `/tmp/XojoIDE` | Runs the same code path as macOS. Not separately tested |
| Windows | Loopback TCP, on a port `xojoctl` discovers | Least tested. Report anything that misbehaves |

## Windows

Windows has no socket file and no named pipe. The IDE listens on a loopback TCP port that Xojo does not publish.

`xojoctl` finds that port for you. It lists the ports `Xojo.exe` is listening on with `tasklist` and `netstat`, then sends each one a probe carrying a random value. The port that echoes the value is the IDE.

Several Xojo-owned listeners is normal. Debug targets and web previews open their own ports, and they either stay silent or answer wrongly. `xojoctl` works through the candidates until one answers correctly.

Pass `--port <port>` to skip discovery.

`--ipc-name` and `--trust-foreign-socket` do not exist on Windows. Both of them resolve or guard a socket *file*, and Windows has none. They are absent from `--help` there, and rejected if you pass them, rather than accepted and ignored.

## The IDE answers with no project open

The endpoint exists and replies even when no project is open, on both transports. `analyze` then fails with `no_project_open` instead of a connection error.

## Running several IDEs

Set `XOJO_IPCPATH` when you launch the IDE, then pass the same name to `xojoctl` with `--ipc-name`. This works on macOS and Linux.
