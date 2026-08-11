---
name: xojo-ide
description: >-
  Drive a running Xojo IDE from the command line with the bundled xojoctl
  tool: open, analyze, build, run, and stop projects, save, close, and
  reload them, list build targets, and send IDE Scripts, with JSON output
  for automation.
  Use when the user asks to build, analyze, or run a Xojo project, to drive
  or automate the Xojo IDE, or to run Xojo IDE scripts. Also use after
  editing Xojo project files on disk while the IDE is open, so the IDE
  reloads them instead of running stale code.
disable-model-invocation: false
---

# Xojo IDE

This skill controls a running Xojo IDE through `xojoctl`, a Python tool that speaks the IDE Communicator protocol. The IDE must already be running; nothing in this skill can start it.

## Run xojoctl

Run the `scripts/xojoctl` folder with Python, from this skill's folder or by its full path:

```sh
python3 scripts/xojoctl status
```

Run `status` first: it confirms the IDE is reachable before you spend a long command on it. Add `--json` to every command you parse; you get exactly one JSON document on stdout even when the command fails. Run a command with `--help` for its flags.

| Command | Does |
| --- | --- |
| `status` | Check that the IDE is reachable |
| `version` | Report the IDE's version |
| `projects` | List open projects; show and change the frontmost |
| `open` | Open a project |
| `save` | Save the front project without a prompt |
| `close` | Close the front project (`--save` or `--discard --yes`) |
| `reload` | Reload the front project from disk (Xojo 2026r3 or later; `--yes` required) |
| `analyze` | Run Analyze Project and report errors and warnings |
| `build` | Build for one or more targets |
| `run` | Run the project in the IDE debugger |
| `stop` | Stop the running project |
| `targets` | List the build targets, without contacting the IDE |
| `script` | Send an IDE Script |
| `capture` | Log every protocol message, for debugging |

## Rules that keep you out of trouble

- **The IDE's in-memory project wins.** The IDE does not watch the disk. After you edit project files on disk, the IDE keeps running its stale in-memory copy, and an IDE-side save overwrites your disk edits without a word. Reload after every batch of disk edits, and never run `save` between your disk edits and the reload; the reload is `reload --yes` on Xojo 2026r3 or later, and a close-and-reopen on every older release. Better, close the project before a planned batch and reopen after it—a closed project has nothing to go stale and nothing to save over you. See [Editing and reload](references/editing-and-reload.md) for the recipe and the failure modes.
- **Analyze, do not guess.** After a reload, run `analyze`. Errors exit 1; warnings alone exit 0; add `-W` to fail on warnings. `build` never reports warnings; only `analyze` does.
- **Do not lower the timeouts.** A cold IDE unpacks plugins for minutes before it answers, and a real build takes far longer than a demo. A ceiling that fires too early abandons work the IDE is still doing. See [IDE behavior](references/ide-behavior.md).
- **`run` runs the project in the debugger. `script` runs an IDE Script.** They are different commands.
- **Never interpolate untrusted text into an IDE Script.** An IDE Script runs with the user's full power: it can build, write files, and run shell commands. Read [Security](references/security.md) before you generate script source from any external input.
- **Xojo is single-instance.** Several projects can share one IDE, and commands act on the frontmost project. Run `projects` to see which one that is, and `projects --select TITLE` to change it.

## References

- [Editing and reload](references/editing-and-reload.md) — editing project files while the IDE is open: the reload recipe, the two silent failure modes, and the IDE Script commands that edit code in place.
- [JSON output](references/json-output.md) — the full schema and the exit codes.
- [IDE behavior](references/ide-behavior.md) — how the IDE really answers, and the surprises xojoctl handles.
- [Build targets](references/build-targets.md) — the target table and its sort order.
- [Platform support](references/platforms.md) — transports, Windows port discovery, several IDEs.
- [Security](references/security.md) — what an IDE Script can do.
- [Protocol reference](references/protocol.md) — IDE Communicator v2 on the wire.
