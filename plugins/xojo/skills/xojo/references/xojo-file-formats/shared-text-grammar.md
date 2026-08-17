# Shared grammar of Xojo text-project files

Most Xojo project companions are line-oriented text assembled from two simple containers: `#tag` regions and `Begin`/`End` object blocks. This document covers the syntax shared by `.xojo_code`, `.xojo_window`, `.xojo_menu`, `.xojo_report`, `.xojo_toolbar`, `.xojo_image`, `.xojo_color`, and `.xojo_filetypeset`. The same two containers are used by the legacy tagged-text generation — `.rbbas`, `.rbfrm`, `.rbmnu`, `.rbtbar` and `.rbres` — whose region kinds, metadata fields and value spellings differ in the ways described in [xojo-code-generations.md](xojo-code-generations.md).

## `#tag` regions

A region starts with `#tag KIND`, may carry comma-separated metadata, and ends with the matching `#tag EndKIND`:

```text
#tag Class
Protected Class Example
	#tag Method, Flags = &h0
		Sub Run()
		End Sub
	#tag EndMethod
End Class
#tag EndClass
```

Regions nest. Indentation normally reflects nesting, but parsers should match tag kinds rather than depend on a fixed number of tabs. Tag spelling is not uniform across kinds: both `#tag IOSLayout` and `#tag iOSLayout` occur, and which one an item uses is determined rather than arbitrary — see [xojo-code-ui.md](xojo-code-ui.md). Localized-constant children use capitalized `#Tag Instance`.

The metadata after a tag kind is not general CSV. Known fields include `Flags`, `CompatibilityFlags`, `Description`, `Name`, `Type`, `Dynamic`, `Default`, `Scope`, `Attributes`, and `Binary`. `Description` is written only by the current tagged-text generation, and `CompatibilityFlags` is common there but rare in the legacy one; a reader of legacy files must not require either. A comma inside a metadata-serialized value is escaped as `\x2C`, so split only on unescaped metadata commas. This does not apply to the Xojo source declaration inside a region: commas there remain ordinary source punctuation.

## Blank lines between regions

Blank lines inside a code region are structural. A code region — the body of `#tag Class`, `#tag Module`, `#tag Interface`, `#tag WindowCode`, `#tag ScreenCode` and their relatives — holds its item regions in runs of one kind at a time, and the blank lines mark where one run ends and the next begins:

- no blank line before the first item region;
- one blank line between two item regions in the same run;
- two blank lines wherever the run changes.

Stored properties and computed properties form a single run, and so do methods, external methods and delegate declarations. Every other item kind is a run of its own: implemented events, event definitions, menu handlers, constants, enumerations, structures, notes, and `#tag Using`. A closing `#tag ViewBehavior` counts as one more run, so two blank lines separate it from the item above it and none precede it when it is the region's only content.

`#tag Class`, `#tag Module` and `#tag Interface` close immediately after their last region: no blank line stands between it and `End Class`, `End Module` or `End Interface`. A designer's `#tag WindowCode` or `#tag ScreenCode` instead closes on two blank lines when it holds any item region, and closes immediately when it is empty.

At file scope in a designer companion the order is the designer block, one blank line, the code region, one blank line, then the `#tag Events` regions written one after another with no blank line between them, and finally `#tag ViewBehavior` immediately after the last of them — or one blank line after the code region when the file has no `#tag Events` region at all.

Blank lines inside a source body are a different thing: they belong to the source, are stored line for line, and carry no layout meaning. The separators above are stored nowhere — neither the Xojo Binary Project nor the Xojo XML Project has a record for them — so a writer emitting text reconstructs them from the kinds of the items it writes.

## `Begin`/`End` blocks

Designer objects use nested blocks:

```text
Begin DesktopWindow MainWindow
   Width = 600
   Begin DesktopButton SaveButton
      Caption = "Save"
   End
End
```

The start line is normally `Begin <class> <instance-name>`, where the instance name is the remainder of the line and can contain spaces (for example the `Mac OS X` build-step list). Some report bands have an empty class position (`Begin  PageHeader`), and `ScreenContent` uses `End ScreenContent` rather than a bare `End`. Property spacing is cosmetic: all of `Key=Value`, `Key = Value`, and aligned `Key          =   Value` occur.

The same key can occur repeatedly. In particular, mobile controls use one `AutoLayout = ...` row per constraint. Preserve order and duplicates.

### Two spellings of the same property

A group of appearance properties has two names, an older and a current one: `TextSize`/`FontSize`, `TextFont`/`FontName`, `TextUnit`/`FontUnit`, `HelpTag`/`Tooltip`, `AutoDeactivate`/`AllowAutoDeactivate`, `TextAlign`/`TextAlignment`, `TabStop`/`AllowTabStop`, `Mode`/`RunMode` and `ButtonStyle`/`MacButtonStyle`.

Both forms occur in tagged text, and both occur on the same class, so the class name does not determine which one a block carries. A `Begin RadioButton` block may carry either `TextSize` or `FontSize`. What it carries is whatever the project itself holds: a project that has never been through a writer that renames the property keeps the older name, and one that has carries the current name.

A reader must therefore accept both spellings for these properties and must not treat one as invalid. A writer must preserve the spelling it was given rather than normalizing to either form, because doing so would change the file for every project that had the other.

A block usually carries one of the two, but it may carry both, and a reader must not treat a block that states both as malformed. Where both are present the values agree, and both rows are preserved rather than collapsed. The both-form is confined to the current-generation classes for the font and text-alignment pairs, and occurs on classic-named classes as well for `HelpTag`/`Tooltip` and `AutoDeactivate`/`AllowAutoDeactivate`.

### Item order inside a code region

A code region states its constants, its methods, its properties, its menu handlers, its enumerations, its structures and its event definitions each in name order, using the same comparison a `Begin` block uses for its properties: case-insensitive, with an underscore sorting after every letter. `MakeObjectFromClassMethod` therefore precedes `m_blackColor`, and `ExecuteJavascriptXC` precedes `ExecuteJavascript_Result`. Stored and computed properties share one run and are ordered together, so a `#tag ComputedProperty` may stand between two `#tag Property` regions.

Overloads share a name and are ordered among themselves by their parameters, compared one parameter at a time: one class states `IndexOf` for a `DesktopRadioGroup`, then a `RowSet`, then a `WebRadioGroup`, where the project holds them in another order entirely. The number of parameters plays no part: a class states `Constructor` for a `Color`, then for four `Integer`s, then for a `Ptr`.

Two things about a parameter place it, and its name is not one of them.

1. The declared type, compared without regard to case — the `As` keyword joining a parameter to its type is itself written either way, and one overload group states `button As WebUIControl` beside `button as WebToolbarButton`. A modifier saying how the argument is passed is part of the type here, compared as though the type were spelled `ByRef Integer`: `ByRef`, `ByVal` and `Extends` all join it. That is why `ByRef value As Integer` precedes `value As Double` while `value As Boolean` precedes `ByRef value As Variant` — the two orderings look contradictory and are one rule. A modifier saying how many arguments there are does not join the type, so an `Optional Boolean` sorts as a plain `Boolean`.
2. Whether the parameter is an array, which precedes a scalar of the same type.

`ParamArray` is not part of the key either, and neither is the method's scope: a `Private` overload takes its place by type like any other. `theColumns() As String` precedes `paramarray columns As String` because the `ParamArray` form carries no `()` and is therefore the scalar of that pair; where both forms carry `()`, the two tie and the order the project holds stands.

The order is per run, and a run is a section rather than a single kind. Methods, external methods and delegate declarations share one section and are ordered together, so a delegate declaration standing between two methods does not divide them; stored and computed properties share another. No item moves across the blank lines that separate one run from the next.

A type's own implemented events are ordered by name with everything else. A control's handlers are not: the regions inside `#tag Events <control-name>` keep the order the project holds them in, and sorting them is wrong.

### Property order inside a `Begin` block

A `Begin` block lists its properties in one order, case-insensitive by name with an underscore sorting after every letter. A constraint row is an `AutoLayout` property line and takes its place among the rest rather than trailing them; several rows share the one name and keep their own relative order. `LockedInPosition` is a property line like any other and sorts with them.

The property is never written with an empty value where it would carry a constraint: a control with no constraints states no `AutoLayout` line at all.

Report bands and their controls follow the same order. Toolbar regions are a separate family that does not, and are described with the toolbar format.

### The declared type decides a value's form

A designer property's declared type, not its value and not its name, decides how the value is written.

- A property declared `String` is quoted; one declared anything else is bare. The same property name therefore appears both ways: one control states `TabPanelIndex = 0` and another `TabPanelIndex = "0"`, and both are correct for the control that carries them.
- A property declared `Color` is written as a `&c` literal, so a stored `0` becomes `&c00000000`. A property declared `ColorGroup` holds a reference rather than a color: a plain number in one is an index and stays as it stands, while a `&h` or `&c` literal it may also hold keeps the `&c` form. `TextColor = 0` and `ColorOff = 0` are both ordinary, and neither can be told from the other by name.
- A property whose declared type is an enumeration, written `Class.Members`, is stated as the enumeration's zero rather than as an empty string when the item stores no value for it.

The declared type is Inspector metadata. A Xojo Binary Project records it; the Xojo XML Project does not, so a conversion that passes through XML cannot recover which form a given property should use.

### A class may state one property twice

A `Begin` block states a property once per declaration in the class's hierarchy rather than once per value. Where a class declares the same property at two levels, an instance carries the line twice, both copies holding the one value the project stores. `iOSMobileTable` does this with `EditingEnabled`.

### Two generations of mobile designer

A mobile screen or container is written in one of two forms, and a file uses one or the other throughout.

| | Android target | iOS target |
|---|---|---|
| code region | `#tag ScreenCode` | `#tag WindowCode` |
| `Device`, `Orientation` | padded like every other property | written `Device = 1`, with single spaces |

The padding follows the project rather than the designer family: in an iOS project every designer writes those two properties unpadded, whether it is a screen, a container, a launch screen or a legacy view, and in an Android project every one of them pads. No file mixes the two.

`Device` and `Orientation` are not Inspector properties and are stored as records of their own. The record naming the device differs between the generations, and both are written as `Device`.

A screen states both. A container states `Orientation` always, and states `Device` only on the iOS side: an Android container states none.

### Which control a control is nested inside

Two properties name a control's container, and they are not interchangeable. `Parent` is the one the nesting follows: a control whose `Parent` names another control is written inside that control's `Begin` block. `InitialParent` agrees with `Parent` wherever both are set, but a control nested inside another may carry only `Parent`, so a reader that consults `InitialParent` alone will place such a control at the top level.

The nesting is stated, not derived. It is not recoverable from the controls' positions, and a control need not sit within its parent's bounds.

A control that belongs to a control set is addressed as `Name$Index`, so a child of the member at index 0 names `GroupBoxes$0`. A control outside any set is addressed by bare name.

### Control-set index

A desktop or web designer states `Index` on every control, carrying the sentinel `-2147483648` where the control is not part of a control set. A mobile or iOS designer states no `Index` line at any nesting level.

### A type's compatibility condition

A class, module or interface states its own compatibility condition as `#tag CompatibilityFlags` **inside** its body: indented one tab like a member region, standing after the declaration and any `Inherits` or `Implements` line, and before the first member. It is not written outside the declaration, and a type available on every target states nothing.

This is distinct from the `CompatibilityFlags` field that a member region carries in its own `#tag` metadata.

### Which root blocks state a compatibility condition

A designer's root block states `Compatibility`, empty when the item is available on every target, in these families only: mobile screens and containers, web pages and containers, and iOS containers and launch screens. A desktop window, an iOS layout, a class, a module and an interface state no such line.

## Scalar values

Observed scalar spellings include:

| Kind | Examples | Notes |
| --- | --- | --- |
| Boolean | `True`, `False`, `true`, `false` | Casing varies by subformat. |
| Decimal integer | `0`, `-2147483648`, `726177791` | Designer references use signed 32-bit decimal representations. |
| Hex integer/bitmask | `&h21`, `&h00000000548D0FFF` | Xojo notation. Width is significant for project IDs. |
| Floating point | `50.00`, `+1.00`, `0.3800000000000000044409`, `3.99e+2` | Do not shorten designer values merely for aesthetics. Exponent notation occurs in legacy-generation designer files; current-generation files write plain decimals only. |
| String | `"Save"`, `""` | Designer strings are quoted. |
| Empty | `BackgroundColor =`, `Backdrop = ""` | Empty is distinct from absent. Legacy-generation designer files write `""` for the unset state of an object reference, boolean or number, where current-generation files write a typed default such as `0` or `False`. |
| Color | `&cRRGGBBAA`, `LabelColor`, `0` | In `&c` notation the last byte is transparency; `00` is opaque. A color value is never quoted. Where a property references a color group rather than holding a color, the value is the group's name or its index written plainly, so `TextColor = LabelColor` and `TextColor = 0` are both ordinary. Legacy-generation designer files also spell a color as `&hRRGGBB`, as a plain decimal integer, or as a quoted `"&cRRGGBB"`. |
| Reference | `Icon = 204128255` | Usually the low 32-bit project ID pattern rendered as signed decimal. |

Designer strings use backslash escapes such as `\n`. Constant metadata uses a different serialization: a string starts with `\"` and ends with `"`, with delimiter-sensitive bytes escaped as `\xNN` (for example comma `\x2C` and equals `\x3D`). Large JavaScript constants demonstrate byte escapes such as `\xC2\xA0`. Preserve unknown escapes byte-for-byte.

Metadata escaping uses the named forms `\t`, `\n`, `\r`, `\\`, `\"`, `\'` and `\?` where one exists, and the `\xNN` byte form only where none does. A tab is written `\t` rather than `\x09`, and an apostrophe and a question mark carry their escapes even though neither is a delimiter.

## Source item flags and scope

Methods, stored properties, computed properties, delegates, external methods, enums, and structures carry a `Flags = &h...` value. The following scope correlations are established across these member kinds:

| Flags | Declaration form | Practical meaning |
| --- | --- | --- |
| `&h0` | no access keyword | Public/default scope |
| `&h1` | `Protected` | Protected scope |
| `&h21` | `Private` | Private scope |
| `&h4` | public properties also exposed in the control Inspector | Public plus an Inspector-related bit; only two examples |
| `&h1000` | legacy high bit combined with an ordinary scope value | Historical method metadata; preserve it, but do not infer it from inheritance |

Do not compute flags solely from this table. The source declaration is the clearest scope signal, and unknown bits may carry IDE state. When changing scope, use a same-kind IDE-produced example; otherwise preserve the full mask.

`Shared` is source syntax, not a separate tag field:

```text
#tag Method, Flags = &h0
	Shared Function Create() As Thing
#tag EndMethod
```

The same applies to extension methods (`Extends`) and assigning setters (`Assigns`): they are part of the serialized declaration.

## Compatibility expressions

An entire class-like item may begin with:

```text
#tag CompatibilityFlags = (TargetWeb and (Target32Bit or Target64Bit))
```

Members place the same field on their opening tag:

```text
#tag Method, Flags = &h0, CompatibilityFlags = API2Only and ( (TargetDesktop and (Target32Bit or Target64Bit)) )
```

Observed atoms are `API1Only`, `API2Only`, `Target32Bit`, `Target64Bit`, `TargetAndroid`, `TargetConsole`, `TargetDesktop`, `TargetHasGUI`, `TargetIOS`, and `TargetWeb`, combined with lowercase `and`, `or`, `false`, and parentheses. These expressions are the inclusion rules for project family, word size, and API generation. An all-disabled member is written `CompatibilityFlags = false`; a default member omits the field. The IDE emits API 1 and API 2 forms asymmetrically, for example:

```text
CompatibilityFlags = API1Only or ( (TargetConsole and (Target32Bit or Target64Bit)) or ... )
CompatibilityFlags = API2Only and ( (TargetConsole and (Target32Bit or Target64Bit)) or ... )
```

Preserve the IDE's operator choice, spacing, target list, and parenthesization. In particular, do not simplify the API 1 expression using ordinary boolean-algebra assumptions.

## Descriptions, attributes and comments

Member Inspector descriptions are hex-encoded UTF-8 bytes on the tag header:

```text
#tag Method, Flags = &h0, Description = 5365747320746865...
```

A region that states no flags still leaves the slot they would occupy, so its first stated field is preceded by a space as well as a comma. An event carrying a description therefore opens:

```text
#tag Event , Description = 507572706F73653A...
```

Language attributes are part of the declaration line:

```text
Attributes( Deprecated = "Replacement" ) Sub OldMethod()
Attributes( Hidden ) Sub InternalMethod()
Attributes ( PrimaryKeyName = "ID", Version = 123 ) Protected Class TestClass
```

This declaration-line form is ordinary Xojo source syntax. Commas and equals signs remain unescaped inside quoted attribute values, double quotes inside strings are doubled, and non-ASCII characters are stored directly as UTF-8. Preserve the source text rather than applying tag-metadata escaping.

Structure-specific attributes can instead appear in tag metadata, encoded as a quoted escaped string:

```text
#tag Structure, Name = GtkRequisition, Flags = &h21, Attributes = "StructureAlignment \x3D 1"
```

In the metadata form, equals is escaped as `\x3D` and comma as `\x2C`, while UTF-8 characters are retained. It is therefore governed by metadata escaping, unlike class, module, method, property, and event-definition attribute declarations.

Code comments are ordinary Xojo source (`//` or `'`) inside source-bearing tags. Navigator Notes use `#tag Note` and contain unescaped, indented text.

## Inspector behavior (`ViewBehavior`)

Classes and designer items commonly end in a `#tag ViewBehavior` region with one `ViewProperty` per Inspector-visible or inherited property:

```text
#tag ViewProperty
	Name="Mode"
	Visible=true
	Group="Behavior"
	InitialValue="0"
	Type="Modes"
	EditorType="Enum"
	#tag EnumValues
		"0 - First"
		"1 - Second"
	#tag EndEnumValues
#tag EndViewProperty
```

A `ViewBehavior` entry is the authority on what an instance of that class states, and it does not have to correspond to a property the class declares in code: a class may re-expose an inherited property to the Inspector without declaring it. An entry of that kind carries its own `Type`, and an instance states the line with that type's zero value. An entry that is both undeclared and `Visible=false` is a different matter — it is a backing field rather than a property, and an instance states nothing for it.

A class whose `ViewBehavior` is empty is given five entries — `Name`, `Index` and `Super` in group `ID`, `Left` and `Top` in group `Position` — since every class carries those in the Inspector. The application object is the exception: its `ViewBehavior` stays empty, and one that does hold entries holds them because the project stores them rather than because they are supplied.

The core fields are `Name`, `Visible`, `Group`, `InitialValue`, `Type`, and `EditorType`. A further field, `InheritedFrom`, names the ancestor that declares the property; it is characteristic of the legacy tagged-text generation and is rare in current-generation files, which carry `Type` on every entry instead. Current-generation files also write the empty and false spellings `Visible=false`, `InitialValue=""`, `EditorType=""` and `Group=""`. Legacy-generation files normally omit all four; `Group=""` is not written there at all, and the other three occur only rarely. Observed editors include empty/default, `MultiLineEditor`, `Enum`, `ColorGroup`, `Boolean`, `String`, `Integer`, `Double`, `SegmentEditor`, `Picture`, `Color`, `DataField`, `DataSource`, `File`, `FolderItem`, `MenuBar`, and `PanelEditor`. Treat editor names as extensible.

`ViewBehavior` describes the Inspector; it does not store the current value of a control instance. Current values live in the enclosing `Begin` block. A custom public property can therefore have a code declaration, a ViewProperty definition, and one value in each placed control instance.
