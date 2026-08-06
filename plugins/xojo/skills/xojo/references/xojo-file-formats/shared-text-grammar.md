# Shared grammar of Xojo text-project files

Most Xojo project companions are line-oriented text assembled from two simple containers: `#tag` regions and `Begin`/`End` object blocks. This document covers the syntax shared by `.xojo_code`, `.xojo_window`, `.xojo_menu`, `.xojo_report`, `.xojo_toolbar`, `.xojo_image`, `.xojo_color`, and `.xojo_filetypeset`.

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

Regions nest. Indentation normally reflects nesting, but parsers should match tag kinds rather than depend on a fixed number of tabs. Tag spelling is not fully normalized: both `#tag IOSLayout` and `#tag iOSLayout` occur, while localized-constant children use capitalized `#Tag Instance`.

The metadata after a tag kind is not general CSV. Known fields include `Flags`, `CompatibilityFlags`, `Description`, `Name`, `Type`, `Dynamic`, `Default`, `Scope`, and `Attributes`. A comma inside a metadata-serialized value is escaped as `\x2C`, so split only on unescaped metadata commas. This does not apply to the Xojo source declaration inside a region: commas there remain ordinary source punctuation.

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

## Scalar values

Observed scalar spellings include:

| Kind | Examples | Notes |
| --- | --- | --- |
| Boolean | `True`, `False`, `true`, `false` | Casing varies by subformat. |
| Decimal integer | `0`, `-2147483648`, `726177791` | Designer references use signed 32-bit decimal representations. |
| Hex integer/bitmask | `&h21`, `&h00000000548D0FFF` | Xojo notation. Width is significant for project IDs. |
| Floating point | `50.00`, `+1.00`, `0.3800000000000000044409` | Do not shorten designer values merely for aesthetics. |
| String | `"Save"`, `""` | Designer strings are quoted. |
| Empty | `BackgroundColor =` | Empty is distinct from absent. |
| Color | `&cRRGGBBAA` | The last byte is transparency in Xojo notation; `00` is opaque. |
| Reference | `Icon = 204128255` | Usually the low 32-bit project ID pattern rendered as signed decimal. |

Designer strings use backslash escapes such as `\n`. Constant metadata uses a different serialization: a string starts with `\"` and ends with `"`, with delimiter-sensitive bytes escaped as `\xNN` (for example comma `\x2C` and equals `\x3D`). Large JavaScript constants demonstrate byte escapes such as `\xC2\xA0`. Preserve unknown escapes byte-for-byte.

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

The core fields are `Name`, `Visible`, `Group`, `InitialValue`, `Type`, and `EditorType`. Observed editors include empty/default, `MultiLineEditor`, `Enum`, `ColorGroup`, `Boolean`, `String`, `Integer`, `Double`, `SegmentEditor`, `Picture`, `Color`, `DataField`, `DataSource`, `File`, `FolderItem`, `MenuBar`, and `PanelEditor`. Treat editor names as extensible.

`ViewBehavior` describes the Inspector; it does not store the current value of a control instance. Current values live in the enclosing `Begin` block. A custom public property can therefore have a code declaration, a ViewProperty definition, and one value in each placed control instance.
