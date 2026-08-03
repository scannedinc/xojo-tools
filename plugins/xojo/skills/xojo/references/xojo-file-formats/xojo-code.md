# `.xojo_code`

`.xojo_code` is an umbrella extension. It stores ordinary language items, platform UI designs, Web session metadata, Worker metadata, and build automation. Determine the variant from its first outer tag, not from the filename.

## Variant routing

| Outer tag | Meaning | Detail |
| --- | --- | --- |
| `Class` | class, App, Session, Worker, custom control | [xojo-code-language.md](xojo-code-language.md) |
| `Module` | module/namespace | [xojo-code-language.md](xojo-code-language.md) |
| `Interface` | interface | [xojo-code-language.md](xojo-code-language.md) |
| `WebPage` | Web page or Web dialog (`Begin` class distinguishes them) | [xojo-code-ui.md](xojo-code-ui.md) |
| `WebContainerControl` | Web container | [xojo-code-ui.md](xojo-code-ui.md) |
| `WebStyle` | legacy Web style definition | [xojo-code-ui.md](xojo-code-ui.md) |
| `MobileScreen` | current mobile screen | [xojo-code-ui.md](xojo-code-ui.md) |
| `MobileContainer` | current mobile container | [xojo-code-ui.md](xojo-code-ui.md) |
| `IOSContainerControl` | older iOS container or custom table cell | [xojo-code-ui.md](xojo-code-ui.md) |
| `IOSLayout`, `iOSLayout`, `IOSScreen` | iOS layout/navigation tree | [xojo-code-ui.md](xojo-code-ui.md) |
| `IOSLaunchScreen`, `iOSLaunchScreen` | iOS launch-screen design | [xojo-code-ui.md](xojo-code-ui.md) |
| `BuildAutomation` | target build-step lists | [xojo-code-build-automation.md](xojo-code-build-automation.md) |

The manifest item kind can be more specific than the outer tag. A `NotificationCenter` item is an ordinary `#tag Class` inheriting `MobileNotifications`; a `Worker` is a class inheriting `Worker` with an additional `#tag Worker` settings region.

## Shared source-bearing regions

Class-like and UI variants reuse these regions:

- `Method`, `Property`, `ComputedProperty`, `Constant`;
- `Event` for implemented event code;
- `Hook` for an event definition;
- `ExternalMethod`, `DelegateDeclaration`, `Enum`, `Structure`, `Note`;
- `MenuHandler` for `Handles <menu>.Action` methods;
- `ViewBehavior` for Inspector definitions.

UI files put code in `WindowCode` or `ScreenCode`, and put control event handlers in one `Events <control-name>` region per control. See the shared grammar and the language-items reference before editing these regions.

## Preservation rules

- Keep the exact outer tag spelling and capitalization used by the item.
- Keep the `Begin` class, outer tag, manifest kind, and project type mutually compatible; these names are related but are not always identical.
- Do not remove empty code regions. IDE output commonly includes an empty `WindowCode` or `ScreenCode` pair.
- Preserve `ViewBehavior`, including inherited-looking entries and private `_m...` properties. It is IDE metadata, not redundant source code.
- Preserve compatibility expressions and unknown tag metadata.
