# `.xojo_window`

Desktop window and desktop container layouts use this text companion. Both current `DesktopWindow` and legacy `Window` files occur. Both variants combine a designer object tree, source code, control events, and Inspector metadata.

## File shape

```text
#tag DesktopWindow
Begin DesktopWindow MainWindow
   Backdrop        =   0
   MenuBar         =   0
   Width           =   600
   Height          =   400
   Begin DesktopButton OKButton
      Caption         =   "OK"
      InitialParent   =   ""
      Left            =   20
      Top             =   20
   End
End
#tag EndDesktopWindow
#tag WindowCode
   ...methods, properties, constants and handlers...
#tag EndWindowCode
#tag Events OKButton
   #tag Event
      Sub Pressed()
      End Sub
   #tag EndEvent
#tag EndEvents
#tag ViewBehavior
   ...ViewProperty records...
#tag EndViewBehavior
```

The outer and root kinds are normally both `DesktopWindow`. A desktop container uses `#tag DesktopWindow` with `Begin DesktopContainer`. Legacy projects instead use `#tag Window` and `Begin Window`. Preserve the variant already used by the project.

The root `Begin` declaration can carry interfaces or class attributes after the instance name:

```text
Begin DesktopWindow MainWindow Implements AppearanceChangedHandler
Begin DesktopContainer ResultViewer Attributes ( DefaultEvent = "ValueChanged" )
```

These suffixes belong to the root class metadata, not to its instance name. XML stores them as `Interfaces` and `Attributes`; RbBF stores them as `Intr` and `Atrb`.

## Object tree and controls

Nested `Begin <class> <name>` blocks describe the root and placed controls. Their physical nesting is meaningful, and some controls also carry a `Parent` field naming the container. `InitialParent` is an independent Inspector property: do not synthesize it merely because a block is nested, because IDE-written XML and RbBF can omit it while the text tree remains nested. Examples include buttons, labels, text controls, canvases, list boxes, page panels, tab panels, separators, scroll bars, timers, sockets, threads, toolbars, custom subclasses, and many framework controls. The block grammar is open-ended: use the class name and fields emitted by the target Xojo version rather than a fixed control whitelist.

Common geometry fields are `Left`, `Top`, `Width`, `Height`, `LockLeft`, `LockTop`, `LockRight`, and `LockBottom`. Common identity/state fields include `Name`, `Index`, `Scope`, `TabIndex`, `TabStop`, `Visible`, `Enabled`, and `InitialParent`. Class-specific properties follow in the same block.

`Index = -2147483648` is the normal sentinel on controls that are not members of a control set. Other index values occur, but not every control-set rule is assigned. Treat `Scope` and other numeric designer enums as opaque unless a same-class example establishes them.

Panel membership is represented by the object-tree nesting, optional `Parent`, and fields such as `TabPanelIndex`. Do not flatten nested blocks or renumber panel indexes. A key may repeat; identical duplicate property rows collapse to one property in IDE-written binary/XML, while differently valued repeats must be retained for analysis. Newer mobile-style constraint fields can also appear on custom controls.

An indexed control set is written as separate sibling `Begin` blocks with the same instance name and distinct integer `Index` values. The event source appears once under that shared name, and applicable event signatures include an `index As Integer` parameter. `TabIndex` is independent of the control-set `Index` even when both happen to use the same sequence.

Nested page and tab panels use literal `Begin` nesting together with `InitialParent` names. `TabPanelIndex` identifies panel membership and is not derived from physical depth; nested panels restart their child panel numbering. Preserve the stored combination of tree position, parent name, and panel index rather than attempting to calculate one from the others.

Legacy `Window` text uses several old/new property pairs asymmetrically. IDE-written XML and RbBF can contain both `BackColor`/`BackgroundColor`, `HasBackColor`/`HasBackgroundColor`, `Placement`/`DefaultLocation`, `Frame`/`Type`, `MaxHeight`/`MaximumHeight`, `MaxWidth`/`MaximumWidth`, `MinHeight`/`MinimumHeight`, `MinWidth`/`MinimumWidth`, and the `FullScreenButton`, `MinimizeButton`, `MaximizeButton`, and `CloseButton` names alongside their `Has…` forms even when tagged text writes only the legacy name. Legacy `PushButton.ButtonStyle` similarly becomes `MacButtonStyle`. The paired color properties use the legacy integer-backed `Color` type.

Legacy `SegmentedButton` and `SegmentedControl` designer blocks retain those names as XML group elements rather than using the generic XML `Control` element. Their RbBF group tags are `segB` and `segC`, respectively. Current desktop segmented controls use the exceptional text opener `BeginDesktopSegmentedButton <class> <name>` with no space after `Begin`; the corresponding RbBF/XML mapping is `Dseg`/`DesktopSegmentedButton`. A parser that recognizes only `Begin <class> <name>` will omit these controls and can incorrectly attach their properties to the surrounding control.

## References to project items

Properties such as `MenuBar`, `Backdrop`, and `Icon` can contain a project item reference as a signed 32-bit decimal. Zero means no referenced item in the observed files. For a negative value, compare its two's-complement 32-bit pattern with the low 32 bits of manifest IDs; legacy IDs are often sign-extended to 64 bits in `.xojo_project`. Do not mistake these values for Navigator indexes. See [xojo-project.md](xojo-project.md#ids-and-cross-references).

## Window source and events

`WindowCode` contains the same member tags used by classes: methods, stored and computed properties, constants, event definitions, external methods, enums, structures, notes, and menu handlers. Their syntax is covered by [xojo-code-language.md](xojo-code-language.md).

Implemented control events are grouped by control instance:

```text
#tag Events SaveButton
   #tag Event
      Sub Pressed()
        Save
      End Sub
   #tag EndEvent
#tag EndEvents
```

The group name must match the placed control. A `MenuHandler` lives in `WindowCode`, not in the menu file. Window-level event implementations can be serialized with the window's own event source in the same general form.

In RbBF, a control does not contain its event behavior directly. Its `CBix` record indexes the block's preceding `CBhv` table, and the selected behavior's `Supr` class matches the control's `ccls`. Controls with no implemented events can share a class-compatible behavior; control-set members can share an event-bearing behavior. A text-to-binary writer must construct this table from the `Events <instance>` owner names and assign matching indexes rather than pairing behavior regions and controls solely by their respective list positions.

The control group's `ccls` and `name` records both contain the control class. The placed instance name is instead the value of the nested `PDef` whose `name` is `Name`. Substituting the instance name into the group's direct `name` record produces a project the IDE rewrites on save.

## Inspector metadata

The trailing `ViewBehavior` region controls how root and custom properties appear in the Inspector. It is metadata, not the current value of a placed control. See [shared-text-grammar.md](shared-text-grammar.md#inspector-behavior-viewbehavior).

When hand-editing a window, preserve unknown root/control properties and their order. Designer defaults and duplicate legacy fields vary substantially by IDE generation.
