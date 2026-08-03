# `.xojo_window`

Desktop window and desktop container layouts use this text companion. The expanded corpus contains both current `DesktopWindow` and legacy `Window` files. Both variants combine a designer object tree, source code, control events, and Inspector metadata.

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

## Object tree and controls

Nested `Begin <class> <name>` blocks describe the root and placed controls. Their physical nesting is meaningful, but `InitialParent` also records the container name. Examples include buttons, labels, text controls, canvases, list boxes, page panels, tab panels, separators, scroll bars, timers, sockets, threads, toolbars, custom subclasses, and many framework controls. The block grammar is open-ended: use the class name and fields emitted by the target Xojo version rather than a fixed control whitelist.

Common geometry fields are `Left`, `Top`, `Width`, `Height`, `LockLeft`, `LockTop`, `LockRight`, and `LockBottom`. Common identity/state fields include `Name`, `Index`, `Scope`, `TabIndex`, `TabStop`, `Visible`, `Enabled`, and `InitialParent`. Class-specific properties follow in the same block.

`Index = -2147483648` is the normal sentinel on controls that are not members of a control set. Other index values are observed, but the corpus does not isolate every control-set rule. Treat `Scope` and other numeric designer enums as opaque unless a same-class example establishes them.

Panel membership is represented by `InitialParent` plus fields such as `TabPanelIndex`. Do not flatten nested blocks or renumber panel indexes. A key may repeat, and newer mobile-style constraint fields can also appear on custom controls.

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

## Inspector metadata

The trailing `ViewBehavior` region controls how root and custom properties appear in the Inspector. It is metadata, not the current value of a placed control. See [shared-text-grammar.md](shared-text-grammar.md#inspector-behavior-viewbehavior).

When hand-editing a window, preserve unknown root/control properties and their order. Designer defaults and duplicate legacy fields vary substantially by IDE generation.
