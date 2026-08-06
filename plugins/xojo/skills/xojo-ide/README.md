# Agent Skill: xojo-ide

Control a running [Xojo](https://www.xojo.com/) IDE from the command line.

`xojoctl` tells the IDE to analyze or build your project, then reports the errors and warnings it found. It prints readable text for you and JSON for your scripts. Use it to run Xojo builds from continuous integration, to automate a release, or to let an AI agent drive the IDE.

The Xojo IDE must already be running. The IDE creates the socket and `xojoctl` dials it. Nothing in this protocol can start the IDE for you.

```console
$ xojoctl analyze
2 warnings
  warning  Left is deprecated.  You should use String.Left instead
    at Window1.Opening, line 1
    | left("asdfsa", 1
  warning  i is an unused local variable
    at Window1.Opening, line 3

1 error
  error  This item does not exist
    at Window1.Opening, line 5
    | foo

fail 1 error, 2 warnings
```

## Requirements

- Python 3.9 or later.
- A running Xojo IDE on the same machine.
- An IDE that speaks IDE Communicator protocol v2. `xojoctl` does not speak the older protocol v1, so IDEs that predate v2 cannot be driven. See [Protocol reference](references/protocol.md).
- macOS or Linux. Windows works but is less tested. See [Platform support](references/platforms.md).

`xojoctl` uses only the Python standard library. There is nothing to install.

## Run it

Run the `scripts/xojoctl` folder with Python, from anywhere:

```sh
python3 /path/to/skills/xojo-ide/scripts/xojoctl status
```

For a plain `xojoctl` command, add an alias to your shell profile:

```sh
alias xojoctl="python3 /path/to/skills/xojo-ide/scripts/xojoctl"
```

The examples below say `xojoctl`. Without the alias, read that as the full `python3` command.

## Use it

### Check that you can reach the IDE

Start here. This confirms the IDE is running and talking to you.

```console
$ xojoctl status
ok connected to Xojo 2026.021 at /private/tmp/XojoIDE
```

### See which projects are open

Xojo runs as a single instance, so several projects can share one IDE. Commands act on the frontmost project. This shows you which one that is.

```console
$ xojoctl projects
#   PROJECT      PATH
0  * My iOS App  /Users/me/Projects/My iOS App.xojo_project
1    Desktop App
2    Console App

  * frontmost -- commands act on this workspace
```

### Switch to a different project

```console
$ xojoctl projects --select "Desktop App"
```

A title that matches nothing is an error, not a silent no-op. `xojoctl` exits 64 and tells you what is still in front.

### Open and close a project

```sh
xojoctl open ~/Projects/MyApp.xojo_project
xojoctl close --save
```

`close --discard` throws away unsaved changes, so it also needs `--yes`.

### Analyze the project

```console
$ xojoctl analyze
ok no errors, no warnings
```

Errors exit 1. Warnings alone exit 0. Add `-W` to make warnings exit 1 too.

Analyze one item instead of the whole project with `--item MyClass`.

### List the build targets

```console
$ xojoctl targets --host
PLATFORM  ARCH                     NAME              VALUE
macOS     Intel 64-bit             darwin-amd64      16
macOS     ARM 64-bit               darwin-arm64      24
macOS     Universal (Intel & ARM)  darwin-universal  9
```

Drop `--host` to list every target Xojo supports.

### Build the project

```sh
xojoctl build --target darwin-arm64
xojoctl build --target darwin-arm64 --target windows-amd64
```

Each target reports the path of the artifact it produced.

Note that `build` never reports warnings. Only `analyze` does. Run `analyze` if you need them.

## Use it in a script

`--json` writes exactly one JSON document to stdout for every command you run. You get JSON even when the connection fails, the command times out, or you mistype a flag. Progress text goes to stderr, so your parser never sees it. (`--help` and `--version` still print text: they are requests for text, not commands.)

```sh
xojoctl analyze --json | jq '.diagnostics[] | select(.severity=="error")'
```

Branch on `ok` and `exit_code`:

| Code | Meaning |
|---|---|
| 0 | Success, including warnings with no errors |
| 1 | The project failed: errors, a configuration problem, or an empty result |
| 2 | Could not connect, or the connection failed part way |
| 3 | Timed out waiting for the IDE |
| 4 | The result is incomplete and you should not trust it |
| 5 | `xojoctl` sent a script the IDE rejected. This is a bug here |
| 6 | No project is open |
| 64 | You used a flag or value the tool does not accept |

The full JSON schema is in [JSON output](references/json-output.md).

## Commands

| Command | Does |
|---|---|
| `status` | Check that the IDE is reachable |
| `version` | Report the IDE's version |
| `projects` | List open projects; show and change the frontmost |
| `open` | Open a project |
| `save` | Save the front project without a prompt |
| `close` | Close the front project |
| `analyze` | Run Analyze Project and report errors and warnings |
| `build` | Build for one or more targets |
| `run` | Run the project in the IDE debugger |
| `stop` | Stop the running project |
| `targets` | List the build targets, without contacting the IDE |
| `script` | Send your own IDE Script |
| `capture` | Log every protocol message, for debugging |

`run` starts your **project** in the debugger. `script` runs an **IDE Script**. They are different commands.

Run `xojoctl <command> --help` for the flags of any command.

## Documentation

- [JSON output](references/json-output.md) — the full schema, field by field, and how it changes between versions.

- [IDE behavior](references/ide-behavior.md) — how the IDE really answers, and the surprises `xojoctl` handles for you. Read this when a result confuses you.

- [Build targets](references/build-targets.md) — the target table, where its numbers come from, and the sort order.

- [Platform support](references/platforms.md) — transports, Windows port discovery, and running several IDEs.

- [Security](references/security.md) — what an IDE Script can do, and why you must not pass it untrusted input.

- [Protocol reference](references/protocol.md) — IDE Communicator v2 on the wire.

- [Development](references/development.md) — running the tests and how the source is laid out.
