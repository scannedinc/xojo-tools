# `.xojo_project`

A project manifest is line-oriented UTF-8 text containing the project header, ordered Navigator items, and project and target settings. Known gaps and unresolved fields are collected under [Blind spots](#blind-spots).

---

## File structure and parse rules

A `.xojo_project` file is **line-oriented UTF-8 text, LF-terminated**, with no sections, no nesting, and no comments. Every line is `Key=Value`.

Three line categories, in order: header, item references, settings.

- **Key order is stable.** Xojo writes keys in a fixed order. Preserve that order when editing a manifest.
- **Duplicate keys are legal** for item references (`iOSLayout` appears twice in the iOS project). A parser must accumulate, not overwrite.
- **Values are never quoted or escaped**, including JSON blobs and values containing spaces. A value runs to end-of-line.
- **Empty value ≠ absent.** `InfoVersion=` is a present key with an empty string.
- **An omitted key means "the default"**—but which keys omit, and at which value, is inconsistent. See [Defaults and omission](#defaults-and-omission).

### Header

```
Type=Desktop
RBProjectVersion=2026.021
MinIDEVersion=20210300
OrigIDEVersion=20260201
```

| Key | Meaning |
|-----|---------|
| `Type` | `Desktop`, `Console`, `Web2`, `iOS`, `Mobile` (Android) |
| `RBProjectVersion` | Format version—"RB" is vestigial *REALbasic* |
| `MinIDEVersion` | Oldest IDE that can open it, `YYYYRRVV` |
| `OrigIDEVersion` | IDE that created it (`20260201` = 2026r2.1) |

Known `MinIDEVersion` values are Console `20070100`, iOS `20140300`, Android `20190200`, Web2 `20200200`, and Desktop `20210300`.

### Project item rows

```text
<Kind>=<Name>;<RelativePath>;&h<ID>;&h<ParentID>;<Boolean>
```

Example:

```text
Folder=UI;UI;&h0000000031BB07FF;&h0000000000000000;false
DesktopWindow=Main;UI/Main.xojo_window;&h0000000015DA9FFF;&h0000000031BB07FF;false
```

| Field | Notes |
|-------|-------|
| `Kind` | IDE role, not the companion-file extension |
| `Name` | Name shown in the Navigator |
| `RelativePath` | Companion or external file, relative to the project file |
| `ID` | Opaque 64-bit hexadecimal item identity |
| `ParentID` | Zero for a top-level item; otherwise another item's ID |
| Boolean | `false` in known files; purpose unknown |

Do not split unrelated setting values merely because they contain semicolons. For example, `AppIcon=Project.xojo_resources;&h0` is a two-field setting, not an item row.

### Item kinds

| Kind | Companion or payload |
| --- | --- |
| `Class`, `Interface`, `Module`, `Worker`, `WebStyle` | `.xojo_code` |
| `BuildSteps` | build-automation `.xojo_code` |
| `DesktopWindow`, legacy `Window` | `.xojo_window` |
| `DesktopToolbar`, legacy `Toolbar` | `.xojo_toolbar` |
| `MenuBar` | `.xojo_menu` |
| `WebSession`, `WebView`, `WebContainer` | `.xojo_code` |
| `MobileScreen`, `MobileContainer` | `.xojo_code` |
| `iOSScreen`, legacy `iOSView`, `iOSContainerControl`, `iOSLayout`, `iOSLaunchScreen` | `.xojo_code` |
| `FileTypeSet` | `.xojo_filetypeset` |
| `ColorAsset` | `.xojo_color` |
| `MultiImage`, `AppIcons`, `LaunchImages` | `.xojo_image` |
| `Report` | `.xojo_report` |
| `SQLiteLocalConnection` | `.xojo_database_connection` |
| `Sound`, `Movie`, `RawData`, `AppleScript`, `Plist` | referenced external file |
| `NotificationCenter` | class-like `.xojo_code` |
| `Library` | source-library folder; child source items hold its API |
| `Folder` | Navigator/disk directory, no companion file |

Kinds are IDE semantics, not extensions. For example, an app icon and an ordinary image both use `.xojo_image`, but their item kinds differ.

### Navigator parents, folders, and module namespaces

`ParentID` is significant. A child of a `Folder` appears beneath that project folder and normally has a correspondingly nested disk path:

```text
Folder=Extras;Extras;&h000000004B9BC7FF;&h0000000000000000;false
Folder=iOSDesignExtensions;Extras/iOSDesignExtensions;&h000000000D697FFF;&h000000004B9BC7FF;false
Module=UIKit;Extras/iOSDesignExtensions/UIKit.xojo_code;&h0000000048070FFF;&h000000000D697FFF;false
```

A class, interface, or module whose parent is a `Module` is in that module's namespace. A nested class can also use a module as its parent:

```text
Module=UIKit;Extras/iOSDesignExtensions/UIKit.xojo_code;&h0000000048070FFF;...;false
Class=UIColor;Extras/iOSDesignExtensions/UIKit/UIColor.xojo_code;&h000000000E1A86FB;&h0000000048070FFF;false
```

Directory nesting alone is therefore not authoritative. Resolve the parent ID to distinguish a plain project folder from a module namespace. Nested modules use the same parent-ID mechanism.

### IDs and cross-references

Item IDs are allocated when a project is created; they are not derived from names. Recent IDs often have their low 11 bits set and fit below `2^31`, but older files violate both patterns and may set the high 32 bits. Treat every ID as an opaque 64-bit identity: never validate, truncate, or generate one from the recent pattern.

IDs must be unique within one manifest, and every nonzero parent ID must resolve to another item row. Xojo may replace duplicate IDs and reset unresolved parents to the root when saving. A validator should report both conditions as errors.

The low 32-bit identity pattern can appear elsewhere as a signed decimal:

- a window's `MenuBar` property;
- a toolbar button's `Icon` property;
- an iOS layout `Target`;
- other designer references.

For example, hexadecimal image ID `&h000000000C2ABFFF` appears as positive decimal `204128255` in a toolbar button. A legacy manifest ID such as `&hFFFFFFFFB7E87A7B` appears in a window as `-1209501061`: the same low 32 bits interpreted as a two's-complement signed integer. To resolve a designer reference, compare its raw 32-bit pattern with the manifest ID's low 32 bits. Do not convert the entire 64-bit spelling to decimal, and do not truncate or rewrite the manifest ID itself.

### External assets

Sounds, movies, scripts, plist files, and raw data are not copied into the text manifest. The item row points to the source file, often with `../` components:

```text
Sound=Pop;../Sounds/Pop.wav;&h...;&h...;false
RawData=invoice;../invoice.html;&h...;&h...;false
AppleScript=Add;../Add.scpt;&h...;&h...;false
```

The Navigator name becomes the project symbol; spaces may be removed or normalized by the IDE. Preserve the actual relative path and parent ID. A Navigator parent does not require the asset itself to reside in a matching disk directory: sound, movie, AppleScript, and raw-data items can remain next to the manifest while their parent IDs place them in nested Navigator folders.

### Libraries and dependencies

A source library is a folder-like project item whose child classes and modules use its ID as their parent:

```text
Library=Library1;Library1;&h000000003B5427FF;&h0000000000000000;false
Class=Fruit;Library1/Fruit.xojo_code;&h000000004C4907FF;&h000000003B5427FF;false
```

Building it produces a `.xojo_library` archive; see [xojo-library.md](xojo-library.md). A consuming project does not require a corresponding manifest item to inherit the archive's public classes or call its public module methods. Do not add a guessed `Library=` row to a consuming project.

`ProjectDependencies` accepts an unquoted Maven-style dependency:

```text
ProjectDependencies=androidx.print:print:1.1.0
```

The delimiter and escaping for multiple coordinates remain unknown. No separate framework or plugin manifest item is currently known.

---

## `BuildFlags`

A hex bitmask written `&hNNNN`. It mixes **two unrelated concerns**—which targets to build, and one Shared build option. This is the most misleading thing in the format.

Do not confuse it with source-item `CompatibilityFlags` expressions, which control whether a class or member is included for particular project types, 32/64-bit targets, and API generation. Those expressions are documented in [shared-text-grammar.md](shared-text-grammar.md).

| Bit | Hex | Control | Where |
|----:|-----|---------|-------|
| 4 | `&h0010` | **Windows** target checkbox | Desktop, Console, Web |
| 7 | `&h0080` | **Linux** target checkbox | Desktop, Console, Web |
| 8 | `&h0100` | **Include Function Names** — *not a target* | all |
| 11 | `&h0800` | unidentified; see below | Desktop only |
| 12 | `&h1000` | **macOS** target checkbox | Desktop, Console, Web |
| 14 | `&h4000` | **This Computer** target checkbox | Desktop, Console |
| 15 | `&h8000` | **Xojo Cloud** target checkbox | Web |

### Target combinations

| Targets checked | Desktop | Console | Web |
|-----------------|---------|---------|-----|
| *(nothing)* | `&h0900` | `&h0100` | `&h0100` |
| run target only *(as shipped)* | `&h4900` | `&h4100` | `&h8100` |
| + macOS | `&h5900` | `&h5100` | `&h9100` |
| + Windows | `&h4910` | `&h4110` | `&h8110` |
| + Linux | `&h4980` | `&h4180` | `&h8180` |
| all four | `&h5990` | `&h5190` | `&h9190` |

"Run target" = This Computer (Desktop, Console) or Xojo Cloud (Web). `&h4000` and `&h8000` never coexist: a Web project's target list has Xojo Cloud and no This Computer, and vice versa.

### `&h0100` is "Include Function Names"

Bit 8 controls **Include Function Names** and is on by default in every project type. It is not a project-type marker; clearing it disables the option.

### `&h0800` is set only in Desktop, and no control moves it

This bit is present in Desktop projects and absent from Console, Web, iOS, and Android projects. Its meaning and corresponding UI control, if any, are unknown. Preserve it.

### The run-target bit in iOS and Android

Both ship `&h4100`, so `&h4000` is set—but neither shows any target checkboxes; Build Settings contains only *Shared* and one platform row with no checkbox.

`Build Automation.xojo_code` also carries Linux, Mac OS X, and Windows step lists in iOS, Android, and Web projects. Whether the manifest stores a hidden target superset is unknown.

### Practical rule

Modify **only** bits 4, 7, 12, 14, 15 (targets) and bit 8 (function names). Preserve everything else rather than recomputing.

```
&h5990  (Desktop, all four targets, function names on)
  = &h0010 Windows | &h0080 Linux | &h0100 FunctionNames
  | &h0800 (Desktop, unidentified) | &h1000 macOS | &h4000 ThisComputer
```

---

## Architecture

`MacBuildArchitecture`, `WindowsBuildArchitecture`, and `LinuxBuildArchitecture` use one shared enum in Desktop, Console, and Web projects.

| Value | Architecture | macOS | Windows | Linux |
|------:|--------------|:-----:|:-------:|:-----:|
| `0` | x86 32-bit | — | ✔ | ✔ |
| `1` | x86 64-bit | ✔ | ✔ | ✔ |
| `2` | ARM 32-bit | — | — | ✔ |
| `3` | ARM 64-bit | ✔ | ✔ | ✔ |
| `4` | Universal (x86-64 + ARM64) | ✔ | — | — |

"—" means the popup doesn't offer it for that platform.

### Zero is written by omission

Setting a platform to **x86 32-bit** deletes its `*BuildArchitecture` key rather than writing `=0`.

**A missing `*BuildArchitecture` means x86 32-bit, not "unspecified".** A tool that treats absence as "leave alone" silently disagrees with the IDE.

### Popup order is not numeric order

Linux lists `ARM 32-bit, x86 32-bit, x86 64-bit, ARM 64-bit`—that is, `2, 0, 1, 3`. Identical in all three types. Never infer the enum from menu position.

### iOS and Android

Both carry `MacBuildArchitecture=1` and no Linux/Windows architecture keys, with no architecture control anywhere in their UI.

---

## The Shared pane

Common to all five project types.

| Inspector label | Key | Encoding |
|-----------------|-----|----------|
| Major Version | `MajorVersion` | integer |
| Minor Version | `MinorVersion` | integer |
| Bug Version | **`SubVersion`** | integer |
| Stage Code | `Release` | `0`=Development `1`=Alpha (uncertain) `2`=Beta `3`=Final |
| Non Release Version | `NonRelease` | integer |
| Auto Increment Version | `AutoIncrementVersionInformation` | `True`/`False` |
| Version | **`ShortVersion`** | string |
| Copyright | **`LongVersion`** | string |
| Description | **`InfoVersion`** | string |
| Use Builds Folder | `UseBuildsFolder` | `True`/`False` |
| Include Function Names | `BuildFlags` bit `&h0100` | — |
| Language | `BuildLanguage` | `&h0`=Default, `&h1`=English, … |
| Optimization Level | `OptimizationLevel` | `0`=Default `6`=Moderate `4`=Aggressive |
| Command Line Arguments | `DebuggerCommandLine` | string |
| Supports Hi-DPI | `HiDPI` | omitted when off |
| Supports Dark Mode | `DarkMode` | omitted when off |

Hi-DPI and Dark Mode appear on Desktop and Web; Android has Dark Mode on its target pane instead. Web adds Port, SSL Port, Application Identifier, Debug Port and Launch Browser to this pane, as described under Web below.

The codes for `Release=1` and `BuildLanguage` values beyond Default and English remain uncertain; see [Blind spots](#blind-spots).

### Three labels that do not match their keys

The labels map to keys as follows:

- Inspector **Version** → `ShortVersion`
- Inspector **Copyright** → `LongVersion`
- Inspector **Description** → `InfoVersion`

Guessing from key names gets all three wrong. `SubVersion` is likewise the **Bug Version** field.

### `OptimizationLevel` is not ordinal

`Default=0`, `Moderate=6`, and `Aggressive=4`. Sorting or clamping this value is meaningless; treat it as an opaque code.

`DebugLanguage=&h0` exists in every project with no control on the pane.

---

## Defaults and omission

Some booleans vanish from the file at their default; others are always written. There is **no general rule**—a parser must know each key.

| Omitted when off | Always written |
|------------------|----------------|
| `HiDPI` | `UseGDIPlus=False` |
| `DarkMode` | `IncludePDB=False` |
| `LinuxNormalizeControlSizes` | `WebLaunchBrowser=False` |
| `*BuildArchitecture` (at `0`) | `CopyRedistNextToWindowsEXE=False` |
| newly-added iOS `Capabilities` entries | `MacUICompatibilityMode=False` |

The polarity differs too: `DarkMode` and `HiDPI` write `True` and omit `False`, while `*BuildArchitecture` omits its *first* enum value.

---

## Per-target panes

### macOS / Windows / Linux (Desktop, Console, Web)

| Inspector label | Key | Encoding |
|-----------------|-----|----------|
| Mac App Name | `MacCarbonMachName` | "Carbon" is vestigial |
| Windows App Name | `WindowsName` | output filename |
| Linux App Name | `LinuxX86Name` | output filename, regardless of architecture |
| Bundle Identifier | `OSXBundleID` | string |
| Product Name | `WinProductName` | string |
| Internal Name | `WinInternalName` | string |
| File Description | `WinFileDescription` | string |
| Company Name | `WinCompanyName` | ships `Example` |
| Minimum Version → mac OS | `MacOSMinimumVersion` | blank = IDE default (`11.0` placeholder) |
| UI Compatibility Mode | `MacUICompatibilityMode` | `True`/`False`, Desktop only |
| Normalize Control Sizes | `LinuxNormalizeControlSizes` | omitted when off, Desktop only |
| MDI | `MDI` | **integer `0`/`1`**, not a boolean |
| MDI Caption | `MDICaption` | string |
| Include Runtime DLL's | `CopyRedistNextToWindowsEXE` | `True`/`False` |
| Include PDB | `IncludePDB` | `True`/`False` |
| HTMLViewer uses WebView2 | `UseWebView2` | `True`/`False` |
| Privileges | `WindowsRunAs` | `0`=User `1`=Highest Available `2`=Administrator |

`UseGDIPlus` is written but has no known IDE control; its meaning remains unclear.

### iOS target pane

| Inspector label | Key | Encoding |
|-----------------|-----|----------|
| iOS App Name | `iOSName` | string |
| Bundle Identifier | `OSXBundleID` | string |
| UI Compatibility Mode | `iOSUICompatibilityMode` | `True`/`False` |
| Minimum Version → iOS | `iOSMinimumVersion` | blank = default (`15.0` placeholder) |
| Build For | `BuildForAppStore` | `False`=Development `True`=App Store |
| Capabilities (gear tab) | `Capabilities` | JSON; see below |

### Android target pane

| Inspector label | Key | Encoding |
|-----------------|-----|----------|
| Android App Name | `MobileName` | string |
| Bundle Identifier | `OSXBundleID` | string |
| Supports Dark Mode | `DarkMode` | omitted when off |
| Build For Play Store | `BuildForPlayStore` | `True`/`False` |
| Minimum SDK Version | `MinSdkVersion` | integer, ships `28` |
| Target SDK Version | `TargetSdkVersion` | integer, ships `36` |
| Project Dependencies | `ProjectDependencies` | string |
| Manifest Permissions | `ManifestPermissions` | string |
| Manifest Globals | `ManifestGlobals` | string |
| Manifest Metadata | `ManifestMetadata` | string |

`MobileThemeColorName=green` and the three `MobileTheme*Color` keys have no control in Build Settings.

### Web

| Inspector label | Key |
|-----------------|-----|
| Debug Port (Shared pane) | `WebDebugPort` |
| Launch Browser (Shared pane) | `WebLaunchBrowser` |
| Application Identifier (Shared pane) | `OSXBundleID` |

---

## Embedded JSON: `Capabilities`

iOS stores capabilities as one unquoted JSON value:

- The default object carries **14 always-present entries**, each `{"Enabled":false,"<SubKey>":{}}`—for example `"AppGroups":{"Enabled":false,"Groups":{}}`.
- Enabling one of those 14 flips `Enabled` **in place**, keeping its sub-object.
- Enabling a capability *outside* the 14 **prepends** a bare `{"Enabled":true}` entry at the front—no sub-object.
- Disabling **removes** a prepended entry entirely.

**UI labels do not always match JSON keys.** Known mappings include:

- **Push Notifications** → `RemoteNotifications`
- **Wallet** → `Passbook`

The structures and semantics of `PrivacyManifest={}`, `PlistEntries={"root":""}`, and `macOSEntitlements` inside `Build Automation.xojo_code` remain unknown.

---

## Companion files

### Formats

| Extension | Contents |
|-----------|----------|
| `.xojo_code` | `#tag Class` … `#tag EndClass`, nesting `#tag Constant`, `#tag Event`, `#tag Session`. Localized constants use `#Tag Instance, Platform = …` |
| `.xojo_window` | `#tag DesktopWindow` + `Begin DesktopWindow … End` property block, then `#tag WindowCode` |
| `.xojo_menu` | Menu tree, same `Begin`/`End` style |
| `.xojo_resources` | **Binary** ICNS container; 12 bytes when empty (`ICNS\0\0\0\x08\0\0\0\0`) |
| `.xojo_image` | Tagged **text** descriptor for external image representations, app-icon slots, and launch-image slots |
| `.xojo_uistate` | **Binary**, dot-prefixed. IDE window state; changes on every open. **Gitignore it** |

For the cross-file ID representation used by window, toolbar, and layout properties, see [IDs and cross-references](#ids-and-cross-references).

### `Build Automation.xojo_code`

Build *steps* live here, not in `.xojo_project`:

```
#tag BuildAutomation
	Begin BuildStepList Mac OS X
		Begin BuildProjectStep Build
		End
		Begin SignProjectStep Sign
		  DeveloperID=
		  macOSEntitlements={"App Sandbox":"False","Hardened Runtime":"False","Notarize":"False","UserEntitlements":""}
		End
	End
#tag EndBuildAutomation
```

**Every project type carries `Linux`, `Mac OS X` and `Windows` step lists**—including iOS, Android and Web—with the type-specific target appended (`iOS`, `Android`, `Xojo Cloud`). The `SignProjectStep` body varies: Desktop and Console carry `DeveloperID` + `macOSEntitlements`, Web and Android only `DeveloperID`, iOS neither.

---

## Per-type key matrix

100 distinct keys. Counts: Desktop 59, Web 62, iOS 57, Console 48, Android 44.

Console's keys are a strict **subset** of Desktop's. Present in Desktop, absent in Console:

```
AppCategory          DarkMode        LinuxNormalizeControlSizes   MenuBar
AppMenuBar           DefaultWindow   MacUICompatibilityMode       PlistEntries
AppSpecificPassword  DesktopWindow   HiDPI
```

**Android is the outlier**—the only type that drops the desktop-target block entirely (`WindowsName`, `MacCarbonMachName`, `LinuxX86Name`, `MacCreator`, `MDI`, `UseGDIPlus`, `WindowsVersions`, `WindowsRunAs`, `MacOSMinimumVersion`, `IsWebProject`, and the four `Win*` metadata fields). iOS keeps all of them despite having no desktop targets in its UI.

---

## Editing rules

- **Preserve unknown bits and unknown keys.** iOS files legitimately hold `WindowsName`, `MDI` and `LinuxX86Name`.
- **Absence is meaningful** for some keys and meaningless for others; see [Defaults and omission](#defaults-and-omission).
- **Preserve item IDs.** They participate in Navigator and designer cross-references.
- **`.xojo_uistate` should be gitignored.**

---

## Default build settings

| Type | `BuildFlags` | `MacBuildArchitecture` | `WindowsBuildArchitecture` | `LinuxBuildArchitecture` |
|------|--------------|------------------------|----------------------------|--------------------------|
| Desktop | `&h4900` | `4` | `1` | `1` |
| Console | `&h4100` | `4` | `1` | `1` |
| Web | `&h8100` | `4` | `1` | `1` |
| iOS | `&h4100` | `1` | omitted | omitted |
| Android | `&h4100` | `1` | omitted | omitted |

---

## Blind spots

### Unmapped or inaccessible controls

| Control | Known key | Gap |
|---------|-----------|-----|
| Use WinUI (Experimental) | `WinUIFramework` | value encoding unknown |
| Native Control Sizes | `NativeWinUISizes` | value encoding unknown |
| Port / SSL Port (Web) | `WebLivePort`, `WebSecurePort` | value encoding unknown |
| Debug Device (Android) | unknown | key and encoding unknown |
| Entitlements (iOS) | unknown | key and representation unknown |
| Key Store Properties (Android) | `KeyStoreFile` presumed | mapping and representation unknown |

The following mappings or value structures are incomplete:

- iOS **Team** (`iOSProvisioningProfile` presumed), **Property List**, **App Store Connect**, and **Privacy** (`PrivacyManifest`);
- macOS **Property List** (`PlistEntries`), **Category** (`AppCategory`), and **App Store Connect** (`AppSpecificPassword`);
- `WebProtocol`, `WebHTMLHeader`, `WebHostingIdentifier`, `WebHostingAppName`, and `WebHostingDomain`;
- `WindowsVersions`, `MacCreator`, `Region`, `DefaultEncoding`, `AppIcon`, and `IsWebProject`;
- `BuildLanguage` values beyond Default and English, and the exact status of `Release=1` as Alpha;
- `Build Automation.xojo_code` fields, including `macOSEntitlements`;
- multiple `ProjectDependencies` coordinates and their delimiter or escaping.

### Keys without a known IDE control

`UseGDIPlus` · `DebugLanguage` · `GenerateGlobalUsingClauses` · `EnvironmentVariables` (iOS) · `MobileThemeColorName` and the three `MobileTheme*Color` keys (Android)

### Open questions

- **`BuildFlags &h0800`** is specific to Desktop projects, but its meaning is unknown.
- **The trailing item-row boolean** is `false` in known files; its meaning and valid `true` behavior are unknown.
- **The item-ID generator** is unknown. Recent IDs often fit `(value << 11) | 0x7FF`, but older IDs do not.
- **The iOS/Android target model** is unclear. Both store the This Computer bit and desktop build-step lists despite not exposing desktop targets.
