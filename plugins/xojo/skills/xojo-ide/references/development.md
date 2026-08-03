# Development

## Tests

```sh
python3 test_xojoctl.py
```

No live Xojo IDE is needed. The suite exits 0 when every check passes.

The tests run a mock IDE over the same transport the real client uses on the current platform: `AF_UNIX` on macOS and Linux, loopback TCP on Windows. Each platform therefore exercises its own code path.

The suite covers framing (partial reads, several messages per `recv`, size caps), reply classification, diagnostic normalization, value escaping including an injection payload, argument validation, the timeout path, and the command flows end to end against the mock.

## Source layout

`xojoctl` is a package. Each module is one layer, and every module imports only the layers below it, so the dependency order reads top to bottom:

| Module | Holds |
|---|---|
| `constants.py` | Tunables, exit codes, and the exception types |
| `protocol_notes.py` | The protocol record: every finding this client is built on |
| `escaping.py` | The code-execution boundary. Read this first |
| `framing.py` | The NUL framer |
| `journal.py` | The message record and the bounded log the reader thread fills |
| `transport.py` | Socket setup, the bounded send, and the peer checks |
| `discovery.py` | Windows port discovery and the nonce probe |
| `classify.py` | Turning a reply into a verdict |
| `client.py` | The exchange loop, tag correlation, and reply ceilings |
| `scripts.py` | Every IDE Script this tool sends, and why each is written that way |
| `targets.py` | The transcribed `BuildApp` table |
| `diagnostics.py` | Flattening the IDE's shapes into the documented JSON |
| `render.py` | Terminal output and sanitising |
| `connection.py` | Choosing and opening a transport |
| `commands.py` | One function per subcommand |
| `cli.py` | The argument parser, help rendering, and `main()` |

`__init__.py` re-exports every public name, so `import xojoctl` reaches anything without knowing which module defines it.

### A note on star imports

Each module star-imports the ones below it, and every module declares `__all__` so the underscore-prefixed helpers travel too. That keeps each layer readable without a wall of per-name imports.

It has one consequence worth knowing: a name can exist in several module namespaces at once. Rebinding `xojoctl.some_function` therefore does not change what an already-imported module calls. The test suite has a `set_global` helper that rebinds a name in every module holding a copy, and any new test that patches module state should use it.

## House style

- Comments explain **why**, especially where the code looks wrong until you know what the IDE does. Many record an IDE behavior that was established by experiment. Keep that explanation when you change the code around it.
- `protocol_notes.py` is the protocol record. Update it when you establish a new IDE behavior, and say how you established it.
