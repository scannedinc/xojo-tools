# `.xojo_menu`

Menu bar files are tagged text containing a nested menu-item tree. Current files use desktop menu items; the legacy `MenuItem` variants still occur in files written by older IDE generations.

## Structure

```text
#tag Menu
Begin Menu MainMenuBar
   Begin DesktopMenuItem FileMenu
      SpecialMenu = 0
      Index = -2147483648
      Text = "&File"
      AutoEnabled = True
      Begin DesktopMenuItem FileSave
         Text = "&Save"
         ShortcutKey = "S"
         MenuModifier = True
         AutoEnabled = True
      End
   End
End
#tag EndMenu
```

The root and all descendants use `Begin`/`End`; nesting defines submenus. The common current classes are `DesktopMenuItem`, `DesktopQuitMenuItem`, and `DesktopApplicationMenuItem`. Legacy files use `MenuItem` and `QuitMenuItem`. Preserve the class names chosen by the IDE.

Common fields are:

- `Text`, `Visible`, `Index`, and `SpecialMenu`;
- `AutoEnabled` and the legacy spelling `AutoEnable`, emitted together in the current generation and singly in the legacy one — see below;
- `ShortcutKey` and legacy `Shortcut`, also sometimes emitted together;
- `MenuModifier`, with occasional `AltMenuModifier`;
- `MacOptionKey` and `PCAltKey` when the shortcut distinguishes the Mac Option key from the Windows Alt key;
- `SubMenu` in a small number of legacy records.

Fields are not guaranteed to be present on every menu-item subclass. Numeric values such as `SpecialMenu` are designer enums and should be copied from a known equivalent item.

`MacOptionKey` maps to XML `MacOptionModifier` and RbBF `Mopt`; `PCAltKey` maps to XML `PCAltModifier` and RbBF `MiAK`.

`AutoEnabled` and `AutoEnable` are two tagged-text spellings of the same XML `MenuAutoEnable` / RbBF `maEn` value. When both appear, they carry the same Boolean. `SubMenu=True` maps to bit 0 of XML `ItemFlags` / RbBF `flag`; the nested child tree remains the authoritative submenu contents.

### Two generations of menu item

A menu item is written in one of two forms, and the property set and the field order move together — a file does not mix them:

| Generation | `AutoEnable` spelling | Field order |
| --- | --- | --- |
| current | both `AutoEnabled` and `AutoEnable` | `Index` before `Text` |
| legacy | `AutoEnable` only | `Text` before `Index` |

The legacy order is an exception to the property ordering other designer families follow, so a writer must not sort a legacy menu item's fields by name. Neither the item's class name nor its `AutoEnable` value identifies the generation on its own: `MenuItem` rather than `DesktopMenuItem` still occurs with the current layout. The pair of properties and the field order decide it together. Because RbBF stores one `maEn` record for both spellings, the generation is not recoverable from a binary project alone.

## Text, localization, and separators

Ampersands in menu text define platform mnemonic behavior where supported. Localized values can be dynamic constant references such as `Text = "#App.kFileMenu"`. A separator is represented by an ordinary item whose `Text` is `"-"`; keep the IDE-emitted class and remaining properties.

## Connecting menu items to code

The menu file describes the tree only. An action implementation is a `MenuHandler` in a window, class-like item, or application source file:

```text
#tag MenuHandler
   Function FileSave() As Boolean Handles FileSave.Action
     SaveDocument
     Return True
   End Function
#tag EndMenuHandler
```

The exact function signature follows the target API generation. The handler's `Handles <item>.Action` clause binds it to the menu item by name. Renaming a menu item therefore requires updating handlers and any source references.
