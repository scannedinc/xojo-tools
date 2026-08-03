# `.xojo_menu`

Menu bar files are tagged text containing a nested menu-item tree. The 245 examples use current desktop menu items, with a small number of legacy `MenuItem` variants.

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
- `AutoEnabled` and the legacy spelling `AutoEnable`, sometimes emitted together with the same logical setting;
- `ShortcutKey` and legacy `Shortcut`, also sometimes emitted together;
- `MenuModifier`, with occasional `AltMenuModifier`;
- `SubMenu` in a small number of legacy records.

Fields are not guaranteed to be present on every menu-item subclass. Numeric values such as `SpecialMenu` are designer enums and should be copied from a known equivalent item.

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
