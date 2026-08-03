# Protocol reference

`xojoctl` speaks IDE Communicator v2.

## On the wire

| Part | Form |
|---|---|
| Framing | UTF-8 JSON, terminated by a single NUL byte. There is no length prefix |
| Handshake | Send `{"protocol":2}` followed by NUL. The IDE sends **no acknowledgement**. Never wait for one |
| Request | `{"script": "...", "tag": "..."}` followed by NUL |
| Reply | `{"tag": "...", "response": <string or object>}` |
| Errors | Nested **inside** `response`, as `buildError`, `scriptError`, `openErrors`, `loadError`, or `missingFiles` |

One `recv` can carry several complete messages, or part of one. A NUL cannot appear inside a message, because JSON renders an embedded NUL as six characters, so splitting on the byte is exact.

## Transports

| Platform | Endpoint |
|---|---|
| macOS, Linux | `AF_UNIX` at `/tmp/<name>`, default `XojoIDE`, overridden by `XOJO_IPCPATH` |
| Windows | Loopback TCP on a discovered port |

See [Platform support](platforms.md) for how discovery works.

## Diagnostic payloads

`buildError` carries `errors` and `warnings` arrays.

`scriptError` is a **heterogeneous** array. Each entry carries a `type` that is either `scriptCompilerError` or `scriptCompilerWarning`. Treating the whole array as fatal is wrong: a reply that carries only warnings means the script compiled and ran.

`openErrors` is heterogeneous too, and the nested `isFatal` flag matters. A non-fatal `openErrors` leaves a usable project.

`missingFiles` is undocumented but real. See [IDE behavior](ide-behavior.md).

## Verified findings

`xojoctl/protocol_notes.py` documents every finding this client is built on. Read it before changing how replies are judged.

## Xojo's own documentation

- [IDE Communicator](https://documentation.xojo.com/topics/build_automation/ide_communicator.html)
- [IDE Scripting](https://documentation.xojo.com/topics/build_automation/ide_scripting/index.html)
