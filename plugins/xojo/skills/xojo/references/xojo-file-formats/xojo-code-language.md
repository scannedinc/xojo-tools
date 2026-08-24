# Language items in `.xojo_code`, `.xojo_window`, and UI code regions

This document describes source entities serialized inside Xojo tags. The same entity grammar appears in class/module/interface files, window code, screen code and report code.

## Classes

```text
#tag Class
Protected Class Widget
Inherits DesktopCanvas
Implements Iterable
	...
End Class
#tag EndClass
```

The declaration carries the type access (`Public`, `Protected`, `Private`, or omitted), name, optional language attributes, base class and implemented interfaces. `Inherits` and `Implements` are separate source lines immediately after the declaration. Multiple spaces are possible (`Implements  Iterable`): the stored interface string is kept verbatim and may begin with its own space — the XML form holds ` Iterable` where the text states `Implements  Iterable` — so a writer emits `Implements ` followed by the stored string, and a reader must not strip the stored string's leading whitespace.

Attributes precede the declaration on the same line:

```text
Attributes ( PrimaryKeyName = "ID", Version = 123 ) Protected Class TestClass
```

Classes nested in module namespaces are still separate files. Their namespace relationship is the `.xojo_project` parent ID, not an enclosing `#tag Module`.

## Modules and namespaces

```text
#tag Module
Protected Module Utilities
	...
End Module
#tag EndModule
```

A module file contains methods, properties, constants, delegates, enums, and structures using the same tags as a class. Modules do not define events. A manifest item whose parent ID is a module's item ID is a child of that namespace. Classes, interfaces, and modules can be nested inside modules. Every nested item remains a separate file; the child module's manifest row uses the outer module's item ID as its parent and its path follows the nested directory.

A file-level `Using` clause is serialized as an empty named region within the class or module:

```text
#tag Using, Name = Utilities
#tag EndUsing
```

The region appears after ordinary members and before `ViewBehavior` when that region is present. Repeated file-level clauses are repeated `Using` regions in source order, with no enclosing collection or count field. A method-local `Using Utilities` statement remains ordinary source text inside its `Method` region.

In XML each clause is a `Using` element containing `ItemName`. In RbBF it is a `USng` group whose `name` record contains the namespace.

## Interfaces

```text
#tag Interface
Protected Interface Observer
	#tag Method, Flags = &h0
		Sub Update(value As Integer)
		End Sub
	#tag EndMethod
End Interface
#tag EndInterface
```

Interface signatures use the ordinary `Method` tag and retain an empty method body. The manifest item kind is `Interface` and its companion remains `.xojo_code`.

## Methods

```text
#tag Method, Flags = &h21
	Private Shared Function Find(id As Integer) As Thing
		...
	End Function
#tag EndMethod
```

Everything needed to reproduce a method—scope, `Shared`, `Extends`, `Assigns`, parameters, return type, attributes, code and comments—is ordinary Xojo source inside the tag. Overloads are repeated `Method` regions with the same name. Constructors and operators are also methods. Constructors use the ordinary method scope flags in both base classes and subclasses: `&h0` for public, `&h1` for protected, and `&h21` for private.

Some older files carry an additional `&h1000` bit on methods, producing values such as `&h1000`, `&h1001`, and `&h1021`. The bit occurs on constructors and ordinary methods. Deleting and recreating an otherwise identical constructor in the current IDE removes it, so it is legacy method metadata rather than a constructor or inheritance flag. Its historical meaning is unknown. Readers should accept it, lossless editors should preserve it, and writers should not add it based on constructor or inheritance semantics.

An optional `Description = <hex>` field on the opening tag is the Inspector description encoded as hexadecimal UTF-8 bytes.

Tagged text can retain editor indentation before each source line. The corresponding XML `SourceLine` elements and RbBF `srcl` records are left-aligned, so leading code indentation is presentation data that is normalized when text passes through either single-file format. Relative indentation is not part of Xojo's language semantics.

## Stored and computed properties

A stored property is a one-line declaration:

```text
#tag Property, Flags = &h1
	Protected Shared Cache As Dictionary
#tag EndProperty
```

Array bounds and initial values remain part of that line. `Shared` is not in the flag mask. Two public custom-control properties exposed in the Inspector use `Flags = &h4`; ordinary public properties use `&h0`.

A computed property places accessor regions first and its declaration last:

```text
#tag ComputedProperty, Flags = &h0
	#tag Getter
		Get
			Return mValue
		End Get
	#tag EndGetter
	#tag Setter
		Set
			mValue = Value
		End Set
	#tag EndSetter
	Value As Integer
#tag EndComputedProperty
```

Getter-only examples omit the entire Setter region. Accessor scope is carried by the final declaration/outer flags. A shared class computed property adds `Shared` to the final declaration and otherwise uses the identical layout:

```text
#tag ComputedProperty, Flags = &h0
	#tag Getter
		Get
			Return mValue
		End Get
	#tag EndGetter
	Shared CurrentValue As Integer
#tag EndComputedProperty
```

A module computed property omits `Shared`, as module members are already global to the module. Both getter-only and getter/setter shared class examples are established.

## Implemented events and event definitions

`Event` stores an implemented handler body:

```text
#tag Event
	Sub Opening()
		...
	End Sub
#tag EndEvent
```

At class or WindowCode level this implements an inherited event. For a placed control, handlers are grouped by instance name:

```text
#tag Events SaveButton
	#tag Event
		Sub Pressed()
			...
		End Sub
	#tag EndEvent
#tag EndEvents
```

`Hook` defines a new event (the IDE calls it an Event Definition):

```text
#tag Hook, Flags = &h0
	Attributes( CompletionKind = "Final" ) Event Completed(result As String)
#tag EndHook
```

Event definitions belong to classes; modules do not have events. The IDE does not offer a scope setting for an event definition. Definitions are displayed in red, consistent with `RaiseEvent` being callable only from the defining class. Tagged text always uses `Flags = &h0` for an event definition, while the corresponding XML `ItemFlags` and RbBF `flag` use the private-scope value `33` (`&h21`). This is a format-specific translation performed by the IDE, not evidence of a user-selectable scope.

Event-definition attributes precede `Event` on the declaration line. XML stores their contents in `Attributes`; RbBF stores them in an optional `Atrb` record after `rslt` and before `kCod`. Attributes do not change the event-definition flag translation. Hooks can also carry a hex `Description` field, which maps to XML `CodeDescription` and RbBF `kCod`. Event implementations can carry descriptions in newer examples. Compatibility flags are not observed on events, consistent with current IDE behavior.

## Menu handlers

Menu handlers are methods in a class/window code region with a dedicated tag:

```text
#tag MenuHandler
	Function FileAbout() As Boolean Handles FileAbout.Action
		...
		Return True
	End Function
#tag EndMenuHandler
```

The link to the menu item is the `Handles <name>.Action` clause. The menu tree itself is in `.xojo_menu`. XML and RbBF also store the menu-handler identity separately. A current binary saved from a native Xojo Project can retain the complete declaration, including the `Handles` suffix, while older binary/XML source can omit the suffix even though exporting that binary as Xojo Project adds it. A reader must accept both forms. A writer importing Xojo Project must preserve a supplied suffix; the separate identity is sufficient to interpret an older declaration that omits it but is not a reason to delete text added by the IDE's export.

## Constants and localization

Constants encode their definition in tag metadata rather than a source declaration:

```text
#tag Constant, Name = kQuit, Type = String, Dynamic = False, Default = \"&Quit", Scope = Public
	#Tag Instance, Platform = Windows, Language = Default, Definition = \"E&xit"
#tag EndConstant
```

`Dynamic=True` marks a dynamic/localizable constant. Each `Instance` supplies a platform/language override. Strings use the metadata escape rules described in `shared-text-grammar.md`; do not parse these rows as ordinary CSV.

The five opening fields always appear, in the order shown. A constant may then carry `CompatibilityFlags`, `Attributes`, and `Description`:

```text
#tag Constant, Name = kPrompt, Type = String, Dynamic = False, Default = \"", Scope = Private, Description = 5468652074657874207061737465642066726F6D207468652070757A7A6C6520706167652E0A
#tag Constant, Name = kPaddingSize, Type = Double, Dynamic = False, Default = \"5", Scope = Private, Attributes = \"Hidden"
```

`Description` is the Inspector description as hexadecimal UTF-8, exactly as on a method or property. `Attributes` takes the metadata-escaped form rather than the declaration-line form, and an empty attribute list is spelled out in full as `Attributes = \""` instead of being omitted. `CompatibilityFlags` holds an ordinary compatibility expression.

A constant carries no `Flags` field, because its stored flag mask holds two facts the header spells out separately. The low bits give the scope on the same scale as other members — `&h0` public, `&h1` protected, `&h21` private — and bit `&h40` marks the constant dynamic. A stored mask of `&h41` therefore describes the protected localizable constant whose header reads `Dynamic = True, Scope = Protected`.

## External methods and declares

An IDE external method is a single Declare statement:

```text
#tag ExternalMethod, Flags = &h21
	Private Soft Declare Function NativeCall Lib "Library" Alias "symbol" (...) As Integer
#tag EndExternalMethod
```

`Soft`, `Alias`, macOS `Selector`, parameter modes and return type are source syntax. Declares written locally inside a method are simply part of that method's code and do not get `ExternalMethod` tags.

## Delegates

```text
#tag DelegateDeclaration, Flags = &h1
	Protected Delegate Sub Handler()
#tag EndDelegateDeclaration
```

Scope is represented both by the flags and declaration keyword. The signature is ordinary source.

## Enumerations

```text
#tag Enum, Name = Comparison, Type = Integer, Flags = &h0
	Less = -1
	  Equal
	Greater
#tag EndEnum
```

The member list is laid out the way a method body is: the first and last members sit at the region's own depth and every member between them is indented two further spaces. A member carries no indentation of its own, so all of it comes from position — a two-member list gains nothing, and a three-member list indents only the middle one. Structures follow the same rule.

`Name`, underlying `Type`, and `Flags` are header metadata. `Type` appears only when the enumeration stores an underlying type; where it does not, the field is left out rather than written with an implied default. An enumeration may also carry `Binary`, written as `Binary = True`, and `Description`, the Inspector description as hexadecimal UTF-8:

```text
#tag Enum, Name = CellKind, Type = Integer, Flags = &h0, Description = 486F7720612063656C6C2073746F726573206974732076616C75652E0A
#tag Enum, Name = SearchDomains, Flags = &h0, Binary = True
```

Values are one per line; explicit assignments and implicit increments may be mixed. No separate scope keyword appears inside the body.

## Structures

```text
#tag Structure, Name = PointPair, Flags = &h21, Attributes = "StructureAlignment \x3D 1"
	First As Int32
	Second As Int32
#tag EndStructure
```

Fields are source-like declarations. Structure-level attributes are an escaped tag field, unlike ordinary language attributes on declaration lines.

## Notes and comments

A Navigator Note is named in its tag and contains raw indented lines:

```text
#tag Note, Name = Docs
	Arbitrary note text
#tag EndNote
```

An unnamed Note can be nested inside a Property region, so Notes are not limited to top-level Navigator items. Code comments remain ordinary method/event source and accept both `//` and apostrophe forms.

In XML and RbBF, the source of a named top-level Note repeats the Note name as its first `NoteLine`/`ntln` entry. The text tag carries the name instead, so the repeated first line is not written as part of the text body. An intentional blank line immediately before `#tag EndNote` is stored as a final empty source line and must not be stripped. A nested property Note does not use the top-level Navigator-note framing rule.

## Breakpoints and bookmarks

Breakpoints and bookmarks are not annotated in these source files. Their records live in `.xojo_uistate` and identify an item, unit type/signature, and line number. Breakpoints are established for methods, computed-property accessors, class and control event handlers, while bookmarks use the same reference fields and can coexist with a breakpoint on one source line. IDE scripts do not support breakpoints. See `xojo-uistate.md`; do not move these transient records into source files.
