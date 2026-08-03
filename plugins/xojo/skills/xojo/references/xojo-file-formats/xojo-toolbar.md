# `.xojo_toolbar`

The supplied corpus has four desktop toolbar companions. Each is a tagged designer tree with a `DesktopToolbar` root and nested toolbar buttons.

```text
#tag DesktopToolbar
Begin DesktopToolbar MainToolbar
   Inherits DesktopToolbar
   Style = 0
   Begin DesktopToolbarButton NewButton
      Caption = "New"
      Tooltip = "Create a document"
      ButtonStyle = 0
      Icon = 204128255
      Symbol = ""
   End
   Begin DesktopToolbarButton FlexibleSpace
      ButtonStyle = 6
   End
End
#tag EndDesktopToolbar
```

Observed button fields are `Caption`, `Tooltip`, `ButtonStyle`, `Symbol`, optional `Enabled`, and `Icon`. `Icon` is the referenced image's low 32-bit project ID pattern written as signed decimal. For example, image ID `&h000000000C2ABFFF` becomes `204128255`; a value with bit 31 set is negative. It is not an image-array index. See the conversion rule in [xojo-project.md](xojo-project.md#ids-and-cross-references).

The corpus establishes these style uses:

| `ButtonStyle` | Observed use |
| --- | --- |
| `0` | Regular clickable button |
| `1` | Separator |
| `5` | Fixed space |
| `6` | Flexible space |

Style `3` occurs on example buttons named for charts and dates, but the corpus does not isolate its general meaning. Preserve unknown style values.

Toolbar action code is attached where the toolbar is placed or through normal event handlers; it is not embedded in this companion in the supplied examples. Web and mobile toolbars are designer controls inside their page/screen source, not demonstrated as `.xojo_toolbar` companions here.
