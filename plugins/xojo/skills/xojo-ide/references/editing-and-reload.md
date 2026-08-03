# Editing project files while the IDE is open

An agent's normal edit path is the disk: change the text-format project files, then make the IDE reload them. This page gives the rules for that path, the failure modes when a rule is skipped, and the IDE Script alternatives.

Some items below are marked **unverified**. They are reported by another IDE Communicator client, the MIT-licensed [xojo-mcp](https://github.com/brechanbech/xojo-mcp) project, but have not been confirmed against a live IDE by this skill's own tests. Verify before you rely on one.

## The two silent failure modes

The IDE loads the whole project into memory and never watches the disk. Two mistakes therefore fail without any error:

1. **Edit without reload.** You edit a file on disk and run or analyze. The IDE uses its stale in-memory copy, and your change appears to have no effect. Nothing reports the staleness.
2. **Save over disk edits.** You edit a file on disk, then the IDE saves (a `save` command, a build step that saves, or the user pressing Save). The IDE writes its stale in-memory copy over your edit and destroys it. Nothing reports the overwrite.

The rule that prevents both: **after disk edits, reload before anything else touches the project.**

## The reload recipe

There is no reload command, and `OpenFile` on an already-open project does nothing (verified; see [IDE behavior](ide-behavior.md)). Close, then reopen:

```sh
xojoctl close --discard --yes
xojoctl open /path/to/Project.xojo_project
```

`--discard` throws away the IDE's unsaved in-memory changes, which after disk edits is exactly what you want: the in-memory copy is stale. But if the user may have real unsaved work open in the IDE, stop and ask before you discard it.

A single IDE Script can do the same atomically, reading the path from the IDE itself (unverified):

```
Dim path As String = ProjectShellPath
CloseProject(False)
OpenFile(path)
```

## Window and layout internals

- Event handlers, controls, and layout inside a `.xojo_window` are not reachable through IDE scripting at all (unverified). The disk-edit-and-reload path is the only way to change them.
- Never invent or renumber the `&h` item IDs in project files. Other files reference them, and a fabricated ID can crash the IDE (unverified). The `xojo` skill's `references/xojo-file-formats/` documents the formats; the `xojo-lint` skill validates the result.

## Editing through the IDE instead (unverified)

The IDE Script language exposes an in-IDE editing vocabulary that `xojoctl script` can use. None of it is wrapped as a xojoctl command yet, and none of it is verified here:

- `SubLocations("dot.path")` returns the tab-delimited children of a navigator item; an empty string lists the top level. Events are not listed.
- `SelectProjectItem("Module.Method")` then the `Text` property reads or replaces the selected item's source.
- A multi-line value cannot be written as one Xojo string literal. Build it line by line: `v = v + "escaped line" + EndOfLine`.
- `DoCommand` accepts item-creation names (`NewClass`, `NewModule`, `NewMethod`, and more) and debugger stepping names (`StepOver`, `StepInto`, `StepOut`, `Resume`, `Pause`).

The safety rules of [Security](security.md) apply doubly here: a generated script that writes source code into the project is a generated program.

## Verifying a save

`DoCommand("SaveFile")` reports nothing. To confirm a save happened, compare the modification time of the project file before and after, and allow the IDE a moment to write (unverified as a recipe; the missing signal itself is documented in the protocol notes).

## Seeing what a running or built app did

- In debug runs, `System.DebugLog` output lands in the macOS unified log. Read it back with `log show --last 2m --predicate 'process == "MyApp.debug"'` (unverified).
- A built app that crashes is invisible unless the code installs an `UnhandledException` handler that writes to a log file. The handler does not fire in debug runs; the debugger intercepts the exception first (unverified).
- Prefer `System.DebugLog` over `MessageBox` for tracing: a message box blocks the UI and fires once per iteration.
