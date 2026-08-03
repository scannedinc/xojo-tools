# UI and runtime-specialized `.xojo_code` variants

These variants combine a designer `Begin` tree with source tags. Designer properties are class-specific and evolve across Xojo versions; copy a nearby same-platform item and preserve unknown properties.

## Web pages and dialogs

Both use outer `#tag WebPage` / `#tag EndWebPage`. The root `Begin` class distinguishes them:

```text
#tag WebPage
Begin WebPage MainPage
   ...
End
#tag EndWebPage
```

```text
#tag WebPage
Begin WebDialog AboutDialog
   Position = 1
   ...
End
#tag EndWebPage
```

Child controls are nested `Begin WebButton`, `Begin WebLabel`, and similar blocks. Code follows in `WindowCode`; control handlers use `Events <name>`; Inspector metadata follows in `ViewBehavior`.

Web containers use `#tag WebContainerControl` around `Begin WebContainer` and otherwise follow the same arrangement. The manifest kind is `WebContainer`.

## Legacy Web styles

Legacy Web projects store a style as a `WebStyle` manifest item and a `.xojo_code` file with this form:

```text
#tag WebStyle
WebStyle WarningText
Inherits WebStyle
	#tag WebStyleStateGroup
		text-color=FF0000FF
	#tag EndWebStyleStateGroup
	#tag WebStyleStateGroup
	#tag EndWebStyleStateGroup
	#tag WebStyleStateGroup
	#tag EndWebStyleStateGroup
	#tag WebStyleStateGroup
	#tag EndWebStyleStateGroup
End WebStyle WarningText
#tag EndWebStyle
```

The observed files always retain four ordered state groups, including empty ones. State properties are unquoted CSS-like rows such as `text-color`, `text-font`, `text-size`, `text-align`, `text-decoration`, `misc-background`, per-edge borders, corner radii, and padding. The state-order semantics were not isolated; preserve all four groups and their order.

## Mobile screens

Current Android and current cross-platform mobile projects use:

```text
#tag MobileScreen
Begin MobileScreen Screen1
   Device = 1
   Orientation = 0
   Begin MobileButton OKButton
      ...
   End
End
#tag EndMobileScreen

#tag ScreenCode
...
#tag EndScreenCode
```

Controls use `Mobile...`, `Android...`, custom, or inherited classes. Repeated `AutoLayout` rows store constraints. Each row is a comma-separated positional tuple containing source control/attribute, target control/attribute, relation, multiplier, priority/strength, constant, optional expression, and active flag. The precise numeric enum mapping is not fully established; clone and modify an IDE-produced constraint rather than constructing tuples from guessed numbers.

## Mobile containers

`#tag MobileContainer` encloses `Begin MobileContainer`. It uses `ScreenCode` and the same event/ViewBehavior regions as a screen. Placed controls are nested inside the root block. The manifest kind is `MobileContainer`.

## iOS custom table cells and older containers

The outer tag is `IOSContainerControl` (capital IOS). The root class identifies the actual kind. A custom table cell appears as:

```text
#tag IOSContainerControl
Begin MobileTableCustomCell InvoiceCell
   AllowDynamicHeight = False
   Begin MobileLabel InvoiceNumber
      AutoLayout = ...
   End
End
#tag EndIOSContainerControl
```

Other examples use container/view root classes. Code may be under `WindowCode`, despite the item being mobile. Preserve the existing code-region name rather than normalizing it.

## iOS layouts and layout trees

The corpus contains both `IOSLayout` and `iOSLayout` spellings. A layout is not a control designer. It stores supported orientations and a nested navigation tree:

```text
#tag IOSLayout
	OrientationPortrait = True
	OrientationLandscapeLeft = False
	OrientationLandscapeRight = False
	OrientationPortraitUpsideDown = False
	Begin ScreenContent
		ItemName = Events
		Target = 1656041471
		Icon = 0
	End ScreenContent
#tag EndIOSLayout
```

For a leaf, `Target` is normally the referenced screen's low 32-bit project ID pattern written as signed decimal. Eight top/container nodes instead use `-1` or `-2` as structural sentinels; their exact distinction is not established, so do not try to resolve those values as project IDs. `Icon` is zero or an image reference using the same signed-decimal convention. Nested `ScreenContent` nodes form tab/navigation hierarchies. Empty top nodes occur. Do not reorder nodes; their order is UI order.

Legacy `IOSScreen` files use the same orientation and `ScreenContent` grammar but a different outer tag/project item kind.

## Launch screens

`IOSLaunchScreen`/`iOSLaunchScreen` wraps a designer root, commonly `Begin iosView LaunchScreen` and in some generations `Begin MobileScreen LaunchScreen`. It may be followed by empty `WindowCode` and `ViewBehavior` regions. Launch artwork referenced as an image set is separately represented by `.xojo_image` with manifest kind `LaunchImages`.

## Web sessions

A Web session is an ordinary class inheriting `WebSession`, plus an unindented settings region inside the class:

```text
#tag Session
  interruptmessage=...
  disconnectmessage=...
  confirmmessage=
  AllowTabOrderWrap=True
  ColorMode=0
  SendEventsInBatches=False
  LazyLoadDependencies=True
#tag EndSession
```

The manifest kind is `WebSession`. Keep message text unquoted and to end of line; these entries do not use designer-string quoting.

## Workers

A Worker is an ordinary class inheriting `Worker`, with a settings region:

```text
#tag Worker
  CorePercent=50
  MaximumCoreCount=4
  ProjectItemsToInclude=WordCounter
#tag EndWorker
```

Worker events and properties then use ordinary source tags. The manifest kind is `Worker`. `ProjectItemsToInclude` is a name/list field, not a project ID. For multiple items the value remains on one physical line and joins names with literal `\n` escapes:

```text
ProjectItemsToInclude=JobClass\nUtilities\nUtilities.Record
```

Names may be namespace-qualified. One-item and multi-item forms are observed; an explicit empty form has not been isolated.

## Threads and notification centers

Threads are not separate file formats. They are class items inheriting `Thread`, or placed nonvisual controls such as `Begin Thread` inside a designer. Notification centers likewise use a `Class` outer tag and inherit `MobileNotifications`; only the manifest kind is specialized.
