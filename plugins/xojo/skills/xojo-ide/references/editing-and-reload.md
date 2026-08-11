# Editing project files while the IDE is open

An agent has two edit paths: the disk (change the text-format project files, then make the IDE reload them) and IDE Script (change code and properties inside the running IDE). This page gives the rules for both, the failure modes, and which path each kind of change requires. Everything here was verified against Xojo 2026r2.1 on macOS, except the 2026r3 reload command, which is written from that release's notes. The script commands are Xojo's own, documented in the `xojo` skill's mirror under `references/documentation/topics/build_automation/ide_scripting/`; read `project_commands.md` there for the full vocabulary.

## The two silent failure modes

The IDE loads the whole project into memory and never watches the disk. Two mistakes therefore fail without any error:

1. **Edit without reload.** You edit a file on disk and run or analyze. The IDE uses its stale in-memory copy, and your change appears to have no effect. Nothing reports the staleness.
2. **Save over disk edits.** You edit a file on disk, then the IDE saves (a `save` command, a build step that saves, or the user pressing Save). The IDE writes its stale in-memory copy over your edit and destroys it. Nothing reports the overwrite.

The rule that prevents both: **after disk edits, reload before anything else touches the project.**

The stronger rule, when the timing is yours to choose: **close the project before you edit on disk.** A closed project has no in-memory copy to go stale or to save over your work, and since picking up disk edits costs a close and a reopen anyway, closing first is the same number of operations with no window in which the two copies disagree—and no open IDE inviting the user to edit a project you are rewriting underneath. Default to it for any planned batch of disk edits; the recipe below is for edits that have already happened while the project was open.

For an analyze checkpoint there is one command that does the whole bracket: `xojoctl analyze --project PATH --discard` closes a stale open copy of PATH, opens it fresh from disk, analyzes, and closes without saving—the project is never open around your edits, only a copy of PATH itself is ever closed, and an exit of 4 means the bracket broke and the project is still open.

## The reload recipe

`xojoctl reload --discard` reloads the front project from disk on any IDE release. On Xojo 2026r3 or later it runs Reload Project—2026r3's rename of Revert to Saved, written from that release's notes and not yet verified against a shipping 2026r3. On older IDEs it falls back to the atomic close-and-reopen script below, which lands in the same place. `--item NAME` reloads a single project item and does need 2026r3. `--discard` is required for the same reason `close` has it: a reload discards the IDE's unsaved in-memory changes without prompting—typing the flag is the confirmation.

Through Xojo 2026r2.1 the IDE itself has no reload command, and `OpenFile` on an already-open project does nothing (see [IDE behavior](ide-behavior.md)); on those releases `reload --discard` closes and reopens for you. By hand:

```sh
xojoctl close --discard
xojoctl open /path/to/Project.xojo_project
```

`--discard` throws away the IDE's unsaved in-memory changes, which after disk edits is exactly what you want: the in-memory copy is stale. But if the user may have real unsaved work open in the IDE, stop and ask before you discard it.

A single IDE Script does the same atomically, reading the path from the IDE itself:

```
Dim path As String = ProjectShellPath
CloseProject(False)
OpenFile(path)
```

`ProjectShellPath` returns the path shell-escaped (`My\ Desktop\ App.xojo_project`); pass it to `OpenFile` unchanged. `CloseProject(False)` discards unsaved changes without a prompt. This atomic script is what `reload --discard` itself sends on pre-2026r3 IDEs—one script, so no window exists in which the user could bring another project frontmost between the path fetch and the close.

## Editing through IDE Script instead

For code and property changes, `xojoctl script` can edit the in-memory project directly, with no reload cycle:

- **Navigate with `Location`.** `Location = "App.Greet"` selects a method; `Location = "Window1.TestButton.Pressed"` selects a control's event handler. `TypeOfCurrentLocation` reports what is selected. `SelectProjectItem` works only for project items (classes, windows, modules); it returns False for members, so use `Location` for anything inside an item.
- **Read and write source with `Text`.** After setting `Location`, `Text` gets or sets the body of the selected method or event handler (the body only, not the declaration). A write lands in the in-memory project and is saved with the next save.
- **Build multi-line source line by line.** A Xojo string literal cannot span lines: `v = v + "one line" + EndOfLine`, then `Text = v`. Double the quotation marks to embed one: `"Print ""hi"""`.
- **Set framework properties with `PropertyValue`.** `PropertyValue("Window1.Title") = "New Title"` works on framework-defined properties of project items.
- **Create items with `DoCommand`.** `DoCommand("NewClass")` adds Class1 to the project; `ChangeDeclaration` renames and retypes the current method or property. `DoCommand` also drives debugger stepping (`StepOver`, `StepInto`, `StepOut`, `Resume`, `Pause`).
- **List items with `SubLocations`.** `SubLocations("")` returns the top-level project items tab-delimited. It descends only into modules and folders: it returns nothing for a class or a window.

The safety rules of [Security](security.md) apply doubly here: a generated script that writes source code into the project is a generated program.

## What only disk edits can do

Window structure is not script-editable: no command places or removes a control, `SubLocations` does not list a window's controls, and `Text` returns nothing for a window itself. To add or rearrange controls, close the project, edit the `.xojo_window` file on disk following the `xojo` skill's `references/xojo-file-formats/`, then reopen—or reload, if the edits already happened while the project was open. Never invent or renumber the `&h` item IDs in project files; other files reference them. The `xojo-lint` skill validates the result before the IDE sees it.

## Verifying a save

`DoCommand("SaveFile")` reports nothing. To confirm a save happened, compare the modification time of the edited project file before and after, and allow the IDE a moment to write.

## Seeing what a running or built app did

- `System.DebugLog` lands in the macOS unified log, in both debug runs and built apps. A debug run's process is the app name plus `.debug`. Read it back with `/usr/bin/log show --last 2m --predicate 'process == "My Desktop App.debug"'` — spell out `/usr/bin/log`, because zsh has a `log` builtin that shadows it and silently returns nothing. The IDE's own Messages panel shows the same output.
- `App.UnhandledException` fires in debug runs and in built apps. A built app that crashes is invisible unless that handler writes somewhere durable, so install one that logs to a file when the user needs crash evidence from a built app.
- Prefer `System.DebugLog` over `MessageBox` for tracing: a message box blocks the UI and fires once per iteration.
