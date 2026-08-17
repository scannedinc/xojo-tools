# Build automation in `.xojo_code`

A project normally has a `BuildSteps` manifest item whose companion is `Build Automation.xojo_code`.

A build-step list belongs to that item and is written inside its region. A project may instead hold a list whose container is the project root, and such a list is a project item in its own right: it is left out of the `#tag BuildAutomation` region, it gets an empty code file named after it, and the manifest states no row for it. An empty `.xojo_code` file with no manifest row is therefore well formed and should not be treated as a truncated item.

## Structure

```text
#tag BuildAutomation
	Begin BuildStepList Linux
		Begin BuildProjectStep Build
		End
	End
	Begin BuildStepList Mac OS X
		Begin BuildProjectStep Build
		End
		Begin SignProjectStep Sign
		  DeveloperID=
		  macOSEntitlements={...}
		End
	End
	Begin BuildStepList Windows
		...
	End
#tag EndBuildAutomation
```

Observed list names are `Linux`, `Mac OS X`, `Windows`, `Android`, `iOS`, and `Xojo Cloud`. Every project carries the three desktop lists, even when its actual target is mobile or Web. List and step order is execution order.

## Build and sign steps

`BuildProjectStep` has no observed body. `SignProjectStep` may contain:

```text
DeveloperID=
macOSEntitlements={"App Sandbox":"False","Hardened Runtime":"False","Notarize":"False","UserEntitlements":""}
```

The entitlement value is compact JSON on one unquoted line. Depending on project type, the sign step may omit the JSON or both fields. Preserve additional JSON keys.

## Copy Files steps

```text
Begin CopyFilesBuildStep CopyDatabase
	AppliesTo = 0
	Architecture = 0
	Target = 0
	Destination = 1
	Subdirectory =
	FolderItem = Li4vLi4vRGF0YWJhc2UvRmlsZS5zcWxpdGU=
End
```

`FolderItem` is standard Base64 of the source path bytes; examples decode to relative paths such as `../../Databases/File.sqlite`. Spaces can remain percent-encoded as `%20` inside that decoded path. It is not a project item ID. The key may repeat to copy several inputs, and repeated values retain list order.

The numeric fields have these established meanings:

| Field | Value | IDE meaning |
| --- | ---: | --- |
| `AppliesTo` | 0 | Both |
| `AppliesTo` | 1 | Debug |
| `AppliesTo` | 2 | Release |
| `AppliesTo` | 3 | None |
| `Architecture` | 0 | Any |
| `Architecture` | 1 | Intel |
| `Architecture` | 2 | ARM |
| `Destination` | 0 | App Parent Folder |
| `Destination` | 1 | Resources Folder |
| `Destination` | 2 | Framework Folder |
| `Destination` | 3 | Bundle Parent Folder |
| `Destination` | 4 | Contents Folder |

The same menus and values are used on the Linux, Mac OS X, and Windows lists. `Target` has no current Inspector control; the IDE writes `0` for a new step but preserves other integer values loaded from a project. Preserve it rather than clamping it. The IDE also preserves out-of-range values for the three menus, displaying no selected menu item, so a format reader must not silently normalize them.

`Subdirectory` is raw UTF-8 after `Subdirectory = `, including spaces and non-ASCII characters, with no quoting or escaping. An empty value leaves the space following `=` at the end of the line.

Each copied input has one `FolderItem` line, in list order. The Base64 payload is a percent-encoded, UTF-8 relative POSIX path. The path is relative to the project file as if that file were a directory, so a sibling file is represented as `../File.txt`. A path naming a folder rather than a file ends in a separator, and the separator is part of what the path means.

Saving the project to a new location re-aims such a path only while it stays inside the directory holding the project. A path that climbs out of that directory names a location the project has no bearing on — a temporary folder, or a directory on the machine that first saved it — and it is written unchanged. The tested literal set includes ASCII letters, digits, `.`, `,`, `=`, `@`, `'`, `!`, `$`, `&`, `+`, `~`, `(`, `)`, and `/`. The tested percent-encoded set includes spaces, semicolons, square and curly brackets, `^`, `%`, `?`, `#`, double quotes, angle brackets, `|`, backticks, and non-ASCII UTF-8 bytes; hexadecimal digits are uppercase. On macOS, filenames can consequently reflect the filesystem's decomposed Unicode form. Decode Base64 first and percent-decoding second when resolving a path. Preserve the original encoded bytes when rewriting without relocating the file.

## IDE script steps

An IDE script step puts its filters on the `Begin` line and its XojoScript body directly inside the block:

```text
Begin IDEScriptBuildStep SetVersion , AppliesTo = 0, Architecture = 0, Target = 0
	PropertyValue("App.ShortVersion") = "1.2.3"
End
```

The spacing before the metadata comma is part of observed IDE output. The body is source text and may contain blank lines, comments, continuations, and calls such as `DoShellCommand`. Step order relative to `BuildProjectStep` determines whether it runs before or after the build.

In XML this is an `IDEScriptStep` block. Its `StepAppliesTo`, `ScriptText`, `CopyFileStepArch`, and `Target` children correspond respectively to RbBF records `StpA`, `SCtx`, `Arch`, and `Targ` in a `BSsc` block. `ScriptText`/`SCtx` contains the UTF-8 body with LF separators and no automatic trailing LF; XML normally uses a `Hex` child because the value contains line breaks.

## External IDE script steps

An external script step references a standalone `.xojo_script` file rather than embedding source:

```text
Begin ExternalIDEScriptStep ExternalScript1
	AppliesTo = 0
	Architecture = 0
	Target = 0
	FolderItem = Li4AVW50aXRsZWQueG9qb19zY3JpcHQ=
End
```

`AppliesTo`, `Architecture`, and `Target` use the same fields and preservation rules as Copy Files steps. `FolderItem` is standard Base64 of Xojo's alias bytes. For an observed script beside the project, those bytes are `..`, a NUL byte, and the filename, such as `b"..\x00Untitled.xojo_script"`; this differs from the percent-encoded slash path used by Copy Files. Treat the alias as opaque bytes so the embedded NUL is not converted to `/` or discarded.

In XML this is an `ExternalScriptStep` block with `StepAppliesTo`, `CopyFileStepArch`, `Target`, and `FileAlias` children. Because the observed alias contains NUL, XML represents `FileAlias` with a `Hex` child. RbBF uses block tag `IExs` and records `StpA`, `Arch`, `Targ`, and `alis` after the common `Name`, `Cont`, and `pasw` header.

The referenced `.xojo_script` is plain XojoScript source and remains an external file. It is not a manifest project item and is not embedded in binary or XML project data. Its format is documented in [xojo-script.md](xojo-script.md).

## The signing step and the project type

A `SignProjectStep` states `DeveloperID` even when it holds nothing — except in an iOS project, where the step is written with no properties at all. The division is by project type and holds for every signing step.
