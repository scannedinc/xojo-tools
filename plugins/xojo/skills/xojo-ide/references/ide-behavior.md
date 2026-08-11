# IDE behavior

The IDE Communicator protocol answers in ways that surprise people. This page lists what the IDE really does and what `xojoctl` does about it. Read it when a result confuses you.

## Build never reports warnings

`BuildApp` reports errors only. A clean build does **not** mean your project has no warnings. Every `build` run emits a `warnings_not_reported` note that says so.

Run `analyze` when you need warnings.

## A clean analyze returns nothing at all

`DoCommand("CheckProjectErrors")` on a project with no findings emits nothing. Not `{}`, not an empty `buildError`. Silence.

Silence is also what a hung IDE produces, so `xojoctl` adds a `Print` sentinel to the script. A clean project then returns at once instead of waiting for the timeout ceiling.

## An empty build result is ambiguous

Build scripts end with a sentinel too, and every artifact reports `script_completed`.

- `true` means the script finished and `BuildApp` produced nothing. That is a real answer. You see it when a toolchain is missing, such as Android without Android Studio, or when a target needs configuring, such as Xojo Cloud.
- `false` means the sentinel never arrived and the build may still be running. The run fails with a `build_sentinel_not_seen` note, and `xojoctl` skips the remaining targets. It skips them because a busy IDE answers the next few commands with empty responses, which read as failures that never happened.

A rejected script is the exception. It can never print its sentinel, so `xojoctl` does not wait for one.

The protocol cannot tell you *why* a build produced no output. It can only tell you whether the script finished.

## The socket is recreated between connections

The IDE unlinks and rebuilds `/tmp/XojoIDE` after a client disconnects. Back-to-back commands would otherwise hit `ENOENT` or `ECONNREFUSED`. `xojoctl` retries when it connects. This is normal operation, not a fault.

## A cold IDE takes minutes to answer

The IDE unpacks hundreds of megabytes of plugins before it services anything.

Timeouts are safety ceilings, not expected durations: 900 seconds for the first reply, 300 seconds once the IDE is warm, and 1800 seconds for work that compiles (`--analyze-timeout`, `--build-timeout`). A note goes to stderr after 20 seconds, so a long wait never looks like a hang.

Those ceilings are generous on purpose. Setting them low is worse than useless. A ceiling that expires while a build is running abandons that build, and the IDE then answers the next few commands with empty responses. That reads as "the target failed" when nothing failed.

## One reply can arrive as several messages

A script's `Print` output and a compiler warning come back as separate messages under the same tag.

When the warning comes from compiling, the output only arrives when the script finishes, which can be much later. `xojoctl script` reads every part before it decides. If a compile-time warning arrives first, it waits up to 30 seconds more for the output, and any further reply part ends that wait early. So the output is reported as the output and the warning as a warning, instead of whichever won the race becoming the answer.

The wait is capped rather than running to the reply ceiling. A script that warns and never prints can never end it, because the IDE answers only when a script prints, so the ceiling would stall a command that already has its answer.

If the output never arrives, `result.output` is null and a `script_output_not_captured` note says so. `result.reply_parts` tells you how many messages made up the reply.

## The IDE replies only when a script prints

A script with no output gets no reply, and the read blocks until the ceiling. The script still ran. End your scripts with a `Print` when you need to know they finished.

## The IDE pushes unsolicited messages and reuses tags

This is verified. Connect, send one request, then click Project ▸ Analyze Project by hand. About six seconds later an unrequested message arrives carrying the full `buildError`, tagged with the already-completed request's tag. Xojo staff have acknowledged this as a bug.

`xojoctl` never reuses a tag, but that is not complete protection. The observed message reused the **last tag sent**. So analysis you trigger in the IDE while a command is in flight can be mistaken for that command's reply. This is harmless for `analyze`, where the payload is the analysis result you wanted. For `build` it could report analysis diagnostics as build diagnostics. Nothing at the protocol level separates them: both are a `buildError`.

**Do not touch the IDE during unattended runs.**

Each message in `raw.messages` carries a `channel`:

- `tagged` — the reply a command claimed.
- `trailing` — more output from our own script. Analyze legitimately returns the `buildError` *and* the `Print` sentinel under one tag.
- `out-of-band` — genuinely started by the IDE. This also raises an `unsolicited_messages` note.

## Commands act on the frontmost project

Xojo runs as a single instance, so several open projects share one connection. `xojoctl projects` shows which project is frontmost, and `--select` changes it.

`WindowTitle` is 0-based and index 0 is the frontmost. Only the front project exposes its path, through `ProjectShellPath`. The others show no path, because reading theirs would mean selecting each window in turn.

## Closing takes a prompt flag, not a save flag

Xojo's `CloseProject(prompt As Boolean = True)` shows a dialog when `prompt` is true. During automation that parks a modal dialog in front of nobody. `CloseProject` can never save.

So `xojoctl close --save` runs `SaveFile` first and then closes with `prompt=False`. `--discard` closes and loses your changes; typing it is the confirmation.

## To pick up edits made outside the IDE, reload or close-and-reopen

Through Xojo 2026r2.1 there is no revert or reload command. `OpenFile` on an already-open project does nothing. This is verified: edit a file on disk, send `OpenFile` again, and the stale diagnostics do not change.

Run `xojoctl close --discard`, then `xojoctl open <path>`. Xojo 2026r3 adds Reload Project and its scripting commands (per its release notes; not yet verified against a shipping 2026r3), so there `xojoctl reload --discard` does it in one step.

## Script error line numbers are corrected

The IDE wraps your script in a line of boilerplate before it compiles, so every `scriptError` line number is one greater than the line you sent.

`xojoctl` subtracts that offset and sets `line_source` to `line_field_unwrapped`. `line_raw` keeps the IDE's original number. A raw line too small to carry the offset passes through unchanged, with `line_source` set to `line_field`.

A negative column becomes null, because the IDE uses `-1` for "unknown". Other column values pass through exactly as the IDE sent them, because it is not established whether the IDE counts columns from 0 or from 1. A line of 0 or less becomes null rather than a guess.

This applies only to errors in scripts `xojoctl` sends. Project diagnostics from `buildError` are untouched.

## Nothing to analyze is an error, not a pass

With no project open, `CheckProjectErrors` emits nothing, which looks exactly like a clean project.

`xojoctl` checks `WindowCount` first and exits 6 with `no_project_open`. If that check itself returns nothing usable, `xojoctl` refuses to continue rather than analyze blind.

## A mistyped item is an error, not a pass

`SelectProjectItem` returns false for a name it does not know. `xojoctl` branches on that result and exits 64.

Without the branch, `CheckItemErrors` would run against whatever was selected before and report a clean pass for an item nobody analyzed. The name must match the navigator exactly.

## Some failures arrive under missingFiles

This key is undocumented but real. An Android build with no key store configured returns:

```json
{"missingFiles": "Unable to build. Please specify a Key Store properties file in the Android Build Settings."}
```

`xojoctl` reports that message as the summary and as a diagnostic with `kind: "config"`. That separates "something needs configuring" from "your code is broken".

## Mobile targets share output folders

Desktop targets write to their own folders, such as `macOS ARM 64 bit/` and `Windows 64 bit/`, so the path identifies the target.

Every iOS target writes to `iOS/`, and both Android targets write to `Android/`. Building several mobile targets in one run therefore **overwrites** the earlier artifact, and the path cannot tell you which target produced it.

## Build paths come back shell-escaped

`BuildApp` returns a path like `Test\ Project/Builds\ \-\ Test/...`. `xojoctl` unescapes it, and `raw_path` keeps the original.

This applies on macOS and Linux only. On Windows the backslash is the path separator, so the path passes through untouched.
