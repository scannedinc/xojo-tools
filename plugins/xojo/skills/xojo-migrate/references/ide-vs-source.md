# What the Xojo IDE converts for you, and what it leaves behind

The migration splits cleanly in two: the IDE's built-in converter handles control/class **type** renames; everything else—the deprecated method, property, and function calls inside your code—is source work (this skill).

## What the IDE handles

**Project ▸ Update Controls to API 2.0** (or right-click a control -> **Update to <New Class Name>**) performs:

- Control / class **type** renames: `Window -> DesktopWindow`, `PushButton -> DesktopButton`, `ListBox -> DesktopListBox`, plus `Canvas`, `Label`, `PopupMenu`, `ComboBox`, `TextField`, `TextArea`, `Application -> DesktopApplication`, `MenuBar`/`MenuItem`, and the rest of the desktop control set (the coverage matrix tags these `IDE handles`, 53 entries).
- Standard **event-name** changes on those controls: `PushButton.Action -> DesktopButton.Pressed`, `Open -> Opening`, `Close -> Closing`, etc. The new name depends on the control—a button's `Action` became `Pressed`, a checkbox's `ValueChanged`, a menu item's `MenuItemSelected`.

**This is a prerequisite of the skill, not one of two options.** Requires Xojo 2021r3 or later (when the `Desktop*` classes were introduced). Ask the user to run it **before** starting source conversion, then commit it on its own as the migration branch's first commit. This diff is large and entirely IDE-generated; isolating it is what keeps every later commit readable as hand-reviewed conversion work.

There is no hand-rename fallback here, deliberately. A control's type appears in both code and layout metadata, so a by-hand pass has to keep two representations in step; the event names it would have to change with them differ per control; and the skill already requires the Xojo IDE for the compile checkpoints, so anyone able to use it at all can run the converter. A project that cannot run it cannot reach the `Desktop*` classes either, which makes the migration impossible rather than manual.

## Still on you afterward

- Every deprecated method/property/function **call** in the code: the 264 rules and the coverage matrix's `Source` buckets.
- **Event definitions added by hand to subclasses**: the converter renames standard events on IDE-placed controls, but custom subclass event definitions that shadow old names must be renamed manually.
- **The `Source — type` bucket (52 entries)**: type names that are not placed controls, so the converter never sees them: `Date → DateTime`, `HTTPSocket → URLConnection`, `OpenDialog → OpenFileDialog`, the database types. These are yours in every case, converter or not. `SegmentedControl → SegmentedButton` and `Serial → SerialConnection` live here too, and are the two that cannot be converted by changing the `Super` alone; they need per-class attention. (They are *not* in the `IDE handles` bucket; note that the separate `SegmentedButton → DesktopSegmentedButton` rename is.)
- Anything in the `Removed` bucket (86 symbols, e.g. `FolderItem.AbsolutePath`, `FolderItem.MacType`, `RectControl.BalloonHelp`, the `MoviePlayer` QuickTime surface): gone from the framework. These do not compile, so they surface as build errors whether or not you plan for them.

  Read the *row*, not the bucket, when a member name is shared. `MenuItem.Bold` is Removed, but `.Bold` is live API 2 on `Graphics` and `TextShape`—so a scan filing `.Bold` under Removed is reporting the worst of its receivers, not a verdict on your code. The matrix marks those receivers (`live_on`) and the scanner flags the symbol `MIXED`.
- Anything in the `No replacement` bucket (40 symbols, e.g. `AddressBook`, `Placard`, `Line`): still compiles, but Xojo documents no API 2 replacement. The feature needs a redesign, not a rename.

## Reading the converter's output as evidence

On a project where the converter has already run, its output is a useful oracle—but only inside its jurisdiction. It rewrites control **types** and **event names**; it never touches code-level type annotations or your call sites. So:

| Observation | What it means |
|---|---|
| The converter renamed the types and event names but **left an `Action` binding alone** | **Informative.** Events are its job. That binding is still valid API 2—do not "finish" it by renaming. |
| `As Window` or `As REALbasic.Rect` still in the code | **Not informative.** Code-level type annotations are outside its jurisdiction; it was never going to touch them. Their survival says nothing about whether they are current. |

Stated as a heuristic: **the converter's silence is evidence only where the converter has jurisdiction.** Both readings come up in a real migration and they are not in conflict—the first is a signal, the second is an absence of one. Getting this backwards in either direction costs you: treat its silence on types as approval and you leave real deprecations behind; treat its silence on events as an oversight and you break working code.

The most common instance is the menu handler: a `Handles Foo.Action` menu handler **keeps** `.Action`, and the converter deliberately leaves all of them alone. Only an `Action` event on a `DesktopMenuItem` subclass becomes `MenuItemSelected`. Renaming the handlers unbinds every menu command, and it compiles.

## If the converter cannot be run

Stop and resolve that; do not convert types by hand. See "What the IDE handles" above for why there is no fallback path here. The one case that *is* yours either way is the `Source — type` bucket below, which the converter never touches because those are not placed controls.

## Deprecated vs removed

Deprecated API 1 calls still compile and run; Analyze Project flags them once "Item1 is deprecated" warnings are enabled (Project ▸ Analysis Warnings, off by default). This means conversion can proceed category by category with a working project at every checkpoint.

The two buckets that are *not* ordinary deprecations are easy to confuse, and only one of them blocks a build:

| Bucket | Compiles? | What it means |
|---|---|---|
| `Removed` | **No** | Xojo lists the symbol as Removed; it is gone. Any project still using one fails to build before conversion even starts. |
| `No replacement` | Yes | Deprecated, but Xojo documents no API 2 replacement. It keeps working; there is simply nothing to rename it to. |

The status comes from the per-release tables in Xojo's own `deprecations.md`, not from whether a replacement happens to be documented; those are different questions, and treating them as one put `AddressBook` and `Line` (both still compiling) in the same bucket as symbols that had been deleted, while `FolderItem.AbsolutePath` and the rest of the genuinely-removed set were missing from the matrix altogether.
