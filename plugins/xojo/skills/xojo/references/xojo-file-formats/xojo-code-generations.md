# Tagged-text generations

Xojo's line-oriented tagged text exists in two generations. Both are built from the same containers — `#tag` regions and `Begin`/`End` object blocks — described in [shared-text-grammar.md](shared-text-grammar.md). They differ in which regions and metadata fields are written, in a small number of value spellings, and in the file extensions used on disk. A reader that must accept projects of any age needs both vocabularies. A writer selects the designer vocabulary from the control class rather than from the file, and IDE output sometimes carries both spellings of a renamed property in the same block.

This document uses **legacy generation** for the `.rb*` companions and **current generation** for the `.xojo_*` companions.

## Extensions

| Item kind | Legacy generation | Current generation |
| --- | --- | --- |
| Language item (class, module, interface, app, build automation) | `.rbbas` | `.xojo_code` |
| Desktop window or container design | `.rbfrm` | `.xojo_window` |
| Menu bar | `.rbmnu` | `.xojo_menu` |
| Desktop toolbar | `.rbtbar` | `.xojo_toolbar` |
| Compiled icon resources | `.rbres` | `.xojo_resources` |
| File type set | `.rbbas` | `.xojo_filetypeset` |
| Multi-file project manifest | `.rbvcp` | `.xojo_project` |

A file type set is the one item whose container changed kind rather than only extension: the legacy generation stores it in a general-purpose `.rbbas` file whose sole content is a `#tag FileTypeSet` region, while the current generation gives it a dedicated extension. Determine the variant from the first outer tag in either generation, not from the extension.

The extension is a strong signal of generation but not a guarantee. A file carrying a legacy extension may still use current-generation designer key spellings. Route on content.

## The project manifest

The manifest grammar is identical across the two generations. Both open with the same `Type=`, `RBProjectVersion=` and `MinIDEVersion=` header lines and continue with the same `Kind=Name;relative-path;ID;ParentID;flag` member rows, in the same order, with the same item and parent ID spellings. Item IDs are stable across a generation change; they are not reissued.

Three things inside that stable frame do differ: the extension inside each member's relative path, the extension recorded for a `FileTypeSet` row, and the `RBProjectVersion` value. `RBProjectVersion` records the version of the writing IDE rather than the generation, so it is not a reliable generation test and must not be copied from an unrelated project.

`MinIDEVersion` is unchanged by a generation change.

One layout convention differs. In the legacy generation a module that owns a folder of children is commonly stored inside that folder, as `Parent/Module/Module.rbbas`; in the current generation the same module is stored beside the folder, as `Parent/Module.xojo_code`. Both generations accept either arrangement, since the manifest records the path explicitly, but rewriting extensions alone leaves a manifest whose module paths no longer match the paths the current generation would write.

## What is identical

The following carry over unchanged, and code that handles them needs no generation switch:

- The `#tag KIND` / `#tag EndKIND` region syntax, its nesting, and its tab indentation.
- The `Begin <class> <instance-name>` / `End` block syntax and its three-space designer indentation.
- Tab-indented source bodies inside source-bearing regions, and the blank-line and trailing-whitespace conventions within them. Whitespace shape is not a generation signal.
- Line endings. Both generations are predominantly LF, with carriage-return and CRLF files occurring in each. Line-ending style is a property of an individual file, not of a generation.
- `Flags = &h...` scope masks, including `&h0`, `&h1`, `&h21`, `&h1000` and their combinations.
- The `Inherits <name>` superclass form on a class declaration line. Class, module and interface declaration lines are otherwise identical, including their `Protected`, `Private` and `Public` prefixes.
- `#tag Constant` metadata and its serialization: `Name`, `Type`, `Dynamic`, `Default` and `Scope`, with `Default` written as a `\"`-opened escaped string and `Dynamic` spelled `True` or `False`.
- `#tag Note` bodies, which are unescaped indented text in both generations.
- `#tag EnumValues` children of an enum-typed `ViewProperty`. Both generations write one quoted `"ordinal - Caption"` row per value, and both attach the region to every `EditorType="Enum"` entry.

## Region kinds

No `#tag` kind is confined to the legacy generation. The current generation adds kinds, and every legacy kind survives:

Present in both: `Class`, `Module`, `Interface`, `Window`, `WindowCode`, `Menu`, `Toolbar`, `FileType`, `FileTypeSet`, `BuildAutomation`, `Method`, `Property`, `ComputedProperty`, `Getter`, `Setter`, `Constant`, `Event`, `Hook`, `MenuHandler`, `ExternalMethod`, `DelegateDeclaration`, `Enum`, `EnumValues`, `Structure`, `Note`, `ViewBehavior`, `ViewProperty`.

Observed only in the current generation: `Using`, `DesktopWindow`, `DesktopToolbar`, `Session`, `Worker`, `ScreenCode`, `Report`, `ReportCode`, `WebPage`, `WebContainerControl`, `WebStyle`, `WebStyleStateGroup`, `MobileScreen`, `MobileContainer`, `IOSLayout`, `iOSLayout`, `IOSScreen`, `IOSView`, `IOSContainerControl`, `IOSLaunchScreen`, `Color`, `ColorGroup`, `MultiImage`, `ImageSpecification`, `ImageRepresentation`.

Most of these belong either to project families that the legacy generation did not target, or to container kinds whose legacy form is outside the scope of this document; their absence is therefore not a removal. Two are directly comparable, because both generations serialize them inside the containers described here:

- `Using` names a namespace import at the head of a language item. It has no legacy counterpart; a legacy file expresses the same code with fully qualified names and writes no region.
- `DesktopWindow` and `DesktopToolbar` are alternative outer tags for a window and a toolbar. A legacy window always opens with `#tag Window`; a current-generation window opens with either `#tag Window` or `#tag DesktopWindow`.

## Member metadata fields

The metadata that follows a member's tag kind gained fields and lost none:

| Field | Legacy generation | Current generation |
| --- | --- | --- |
| `Flags` | Yes | Yes |
| `Name`, `Type`, `Dynamic`, `Default`, `Scope` (on `Constant`) | Yes | Yes |
| `Name` (on `Enum`, `Structure`, `Note`) | Yes | Yes |
| `Type` (on `Enum`) | Yes | Yes |
| `Attributes` (on `Constant`, `Structure`) | Yes | Yes |
| `CompatibilityFlags` | Rare, and only on `Method` | Common, and also on `Property`, `ComputedProperty` and `Constant` |
| `Description` | Not written | Written on `Method`, `Property`, `ComputedProperty`, `Constant`, `Event`, `Hook`, `Enum` and `DelegateDeclaration` |
| `Binary` (on `Enum`) | Not written | Written, rarely |
| `Name` (on `Using`) | Not applicable | Yes |

`Description` is the clearest generation marker in a language item: it is a current-generation field only. A legacy file has no place to store an Inspector description, so the information is absent rather than encoded elsewhere.

Compatibility expressions follow the same asymmetry. The legacy generation writes at most a bare target atom such as `TargetHasGUI`; the API-generation atoms `API1Only` and `API2Only`, the parenthesized target expressions, and the all-disabled form `CompatibilityFlags = false` belong to the current generation.

## Inspector behavior (`ViewBehavior`)

The `ViewProperty` field set is where the two generations differ most sharply.

| Field | Legacy generation | Current generation |
| --- | --- | --- |
| `Name` | Always | Always |
| `Group` | Almost always; the empty spelling is not written | Almost always; may be `""` |
| `Type` | Optional | Effectively always present |
| `InheritedFrom` | Common; names the ancestor that declares the property | Rare |
| `Visible` | Normally written only when `true` | Written as `true` or `false` |
| `InitialValue` | Normally written only when non-empty | Written, including as `""` |
| `EditorType` | Normally written only when non-empty | Written, including as `""` |

`InheritedFrom` and `Type` are complements rather than a rename. A legacy entry for an inherited property may carry `InheritedFrom` and omit `Type`, may carry both, or may carry `Type` alone for a locally declared property. A current-generation entry carries `Type` unconditionally and normally omits `InheritedFrom`, so the name of the declaring ancestor is not recorded. When rewriting a legacy entry that has `InheritedFrom` but no `Type`, the type must be resolved from the property declaration; it cannot be recovered from the entry itself.

The other four rows are omission conventions, not vocabulary changes. Where the legacy generation normally omits a field, the current generation writes its empty or false spelling explicitly. `Visible=false`, `InitialValue=""`, `EditorType=""` and `Group=""` are therefore current-generation shapes, and their absence from a legacy entry does not mean the property is invisible or has no editor.

`Type` spellings are not normalized between the generations. Both spell the same Xojo type names, in mixed case — `Boolean` and `boolean`, `Double` and `double`, `Single`, `Integer` — and both leave user-defined class and enumeration names as written. Compare type names case-insensitively; do not rewrite them.

Relative entry order within a `ViewBehavior` region is normally preserved across the two generations, but it is not guaranteed; items may be reordered. Match entries by `Name`, not by position.

## Designer property values

Value spellings inside `Begin`/`End` blocks changed in four ways. Legacy spellings are still valid input and must be read, but should not be produced when writing current-generation files.

| Concern | Legacy spellings | Current spelling |
| --- | --- | --- |
| Color | `&hRRGGBB`, a plain decimal integer such as `16777215`, or a quoted `"&cRRGGBB"` | `&cRRGGBBAA` |
| Number | Exponent notation such as `3.99e+2` and `4.42e+2` occurs alongside plain decimals | Plain decimal only; exponent notation is not written |
| Unset object reference | `""` — for example `Backdrop = ""`, `MenuBar = ""` | `0` |
| Unset boolean or number | `""` | The typed default, such as `False`, `0` or `0.0` |

The empty-string convention is the largest single source of difference between the two generations, because the legacy generation uses one spelling — `""` — for the unset state of every property type, while the current generation writes a value of the property's own type. Do not translate a legacy `""` to a current-generation `""` without knowing the property's type.

Quoting of designer values is not uniform in either generation, and it is not a reliable generation signal. Integers, booleans and floating-point numbers occur both bare and quoted; quoted forms are more frequent in the current generation. Preserve the quoting an existing file uses rather than normalizing it.

Boolean spelling is unchanged. `True` and `False` dominate in `Begin` blocks in both generations, with lowercase `true` and `false` appearing in both; inside `ViewProperty` entries the lowercase spelling dominates in both, and quoted `"True"` and `"False"` appear in both.

## Designer property names and control classes

Many desktop control properties have two names — a classic spelling and a later alias — and the pair is a property of the **control class**, not of the tagged-text generation:

| Classic spelling | Later alias |
| --- | --- |
| `AcceptFocus` | `AllowFocus` |
| `AcceptTabs` | `AllowTabs` |
| `AutoDeactivate` | `AllowAutoDeactivate` |
| `UseFocusRing` | `AllowFocusRing` |
| `BackColor` | `BackgroundColor` |
| `HasBackColor` | `HasBackgroundColor` |
| `Border` | `HasBorder` |
| `CloseButton` | `HasCloseButton` |
| `MaximizeButton`, `MinimizeButton` | `HasMaximizeButton`, `HasMinimizeButton` |
| `FullScreenButton` | `HasFullScreenButton` |
| `MinWidth`, `MinHeight` | `MinimumWidth`, `MinimumHeight` |
| `MaxWidth`, `MaxHeight` | `MaximumWidth`, `MaximumHeight` |
| `Minimum`, `Maximum` | `MinimumValue`, `MaximumValue` |
| `Frame` | `Type` |
| `Placement` | `DefaultLocation` |
| `TextAlign` | `TextAlignment` |
| `TextFont`, `TextSize`, `TextUnit` | `FontName`, `FontSize`, `FontUnit` |
| `HelpTag` | `Hint` |
| `LimitText` | `MaximumCharactersAllowed` |
| `Mask` | `ValidationMask` |
| `Styled` | `AllowStyledText` |
| `ScrollbarVertical` | `HasVerticalScrollbar` |
| `EnableDrag` | `AllowRowDragging` |

A `Begin Label` block uses the classic spellings; a `Begin DesktopLabel` block uses the aliases. The same split holds for `Window` against `DesktopWindow`, `PushButton` against `DesktopButton`, `TextField` against `DesktopTextField`, `TextArea` against `DesktopTextArea`, `ListBox` against `DesktopListBox`, `Slider` against `DesktopSlider`, and the rest of the `Desktop`-prefixed family. Because the `Desktop`-prefixed classes are current-generation only, the alias vocabulary is reachable only from a current-generation file — but the reverse does not hold: a current-generation file that contains classic control classes uses the classic spellings throughout, and a legacy-extension file may be written with the alias vocabulary. Read the `Begin` class name, not the file extension, to decide which spellings to expect.

The renaming is not exhaustive, so the pairing cannot be inferred from a spelling rule. `Caption` on a button or group box, `Text` on a label or text field, `Value` on a checkbox, and the misspelled `Resizeable` on a window are all carried into the `Desktop`-prefixed classes unchanged. Only the pairs listed above are defined.

A block may carry both members of a pair with matching values. This is a compatibility superset, not an inconsistency; preserve both rows.

Control class names themselves follow the same pattern. `StaticText` is observed only in the legacy generation, having been superseded by `Label`. The `Desktop`-prefixed classes — `DesktopWindow`, `DesktopLabel`, `DesktopButton`, `DesktopCheckBox`, `DesktopTextField`, `DesktopTextArea`, `DesktopListBox`, `DesktopCanvas`, `DesktopMenuItem`, `DesktopPopupMenu`, `DesktopProgressBar`, `DesktopContainer`, `DesktopScrollBar`, `DesktopToolbar` and their siblings — are observed only in the current generation, alongside the `Web`- and `Mobile`-prefixed families. Class names are not interchangeable: a class name determines which property vocabulary, `ViewBehavior` entries and event signatures are legal for the block.

## Constructs with no counterpart

When a construct exists in one generation only, the other generation writes nothing for it rather than substituting an equivalent. Consequences for a tool that rewrites one generation into the other:

- Converting current to legacy loses `Description` text, `Using` imports, API-generation compatibility expressions, and any item whose kind has no legacy container.
- Converting legacy to current loses the `InheritedFrom` ancestor name, and requires a `Type` to be supplied for every `ViewProperty` that lacked one.
- A legacy file type set must be moved from a `.rbbas` container into a `.xojo_filetypeset` container, and the manifest path updated accordingly.

Neither direction is lossless, so neither should be performed by mechanical extension rewriting.

## Reading rules

1. Accept both vocabularies on input. Resolve a designer key against the enclosing `Begin` class, not against a global table: a few names, `Type` and `Value` among them, denote different properties on different classes.
2. Decide the output vocabulary once per file, from the outer tag and the `Begin` class names, and apply it consistently.
3. Do not treat an omitted `ViewProperty` field as equivalent to its written empty spelling. In the legacy generation omission is the normal encoding of the empty state; in the current generation the empty spelling is written out.
4. Do not treat a designer `""` as a string when the property is an object reference, a boolean or a number.
5. Preserve quoting, exponent notation, color notation and duplicate compatibility keys exactly as found when round-tripping a file you are not deliberately converting.
