# Build automation in `.xojo_code`

Each project in the corpus has a `BuildSteps` manifest item whose companion is normally `Build Automation.xojo_code`.

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

`FolderItem` is standard Base64 of the source path bytes; examples decode to relative paths such as `../../Databases/File.sqlite`. Spaces can remain percent-encoded as `%20` inside that decoded path. It is not a project item ID. The key may repeat to copy several inputs. Folder/framework paths, nonempty `Subdirectory` values, `AppliesTo` values 0 through 3, `Architecture` values 0 and 1, and `Destination` values 0 through 4 occur in the expanded corpus. Those enums were not isolated by controlled experiments, so copy an IDE-produced step with the intended destination and filters instead of assigning meanings from frequency.

## IDE script steps

An IDE script step puts its filters on the `Begin` line and its XojoScript body directly inside the block:

```text
Begin IDEScriptBuildStep SetVersion , AppliesTo = 0, Architecture = 0, Target = 0
	PropertyValue("App.ShortVersion") = "1.2.3"
End
```

The spacing before the metadata comma is part of observed IDE output. The body is source text and may contain blank lines, comments, continuations, and calls such as `DoShellCommand`. Step order relative to `BuildProjectStep` determines whether it runs before or after the build.

No `ExternalScriptBuildStep` occurs in the supplied corpus. Standalone `.xojo_script` files are IDE automation scripts and do not establish the external build-step grammar.
