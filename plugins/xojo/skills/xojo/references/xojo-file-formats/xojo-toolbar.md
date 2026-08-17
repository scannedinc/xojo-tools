# `.xojo_toolbar`

A desktop toolbar companion is a tagged designer tree with a `DesktopToolbar` root and nested toolbar buttons.

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

A toolbar region is indented with tabs, not spaces, in both generations. `Inherits` is the exception to the nesting: it belongs to the root block but is written at zero indentation, where the root's own properties sit at one tab. A legacy `Toolbar` root states no `Inherits` line at all.

Toolbar regions do not order their properties the way other designer families do, and no ordering rule is established for them beyond `Enabled` following `Caption` on a button that states it.

Observed button fields are `Caption`, `Tooltip`, `ButtonStyle`, `Symbol`, optional `Enabled`, and `Icon`. `Icon` is the referenced image's low 32-bit project ID pattern written as signed decimal. For example, image ID `&h000000000C2ABFFF` becomes `204128255`; a value with bit 31 set is negative. It is not an image-array index. See the conversion rule in [xojo-project.md](xojo-project.md#ids-and-cross-references).

The following style uses are established:

| `ButtonStyle` | Observed use |
| --- | --- |
| `0` | Regular clickable button |
| `1` | Separator |
| `5` | Fixed space |
| `6` | Flexible space |

Style `3` occurs on buttons associated with charts and dates, but its general meaning is not established. Preserve unknown style values.

Toolbar action code is attached where the toolbar is placed or through normal event handlers; it is not embedded in this companion. Web and mobile toolbars are designer controls inside their page/screen source, not demonstrated as `.xojo_toolbar` companions here.

## Legacy toolbar

A legacy manifest uses `Toolbar` rather than `DesktopToolbar`, and its companion has a `Toolbar` root with `ToolButton` children:

```text
#tag Toolbar
Begin Toolbar MainToolbar
Inherits Toolbar
	Begin ToolButton General
		Caption = "General"
		HelpTag = ""
		Style = 2
		Pushed = True
		Icon = 204128255
	End
End
#tag EndToolbar
```

The legacy text names `HelpTag`, `Style`, and `Pushed` correspond to XML `ItemHelp`, `ItemStyle`, and bit 0 of `ItemFlags`. The XML block type is `Toolbar`, represented by the RbBF block tag `pTbr`; the current `DesktopToolbar` block instead uses `pDTb`.

Both toolbar generations use XML `ToolbarStyle`, `ToolItemSymbol`, and `ToolItemAllowMulticolorSymbol`. Their RbBF tags are respectively `tbs `, `tis `, and `tims`; the spaces in `tbs ` and `tis ` are significant.

Current desktop toolbar output supplies `ToolItemAllowMulticolorSymbol = 0`/`tims = 0` even when the text button omits an explicit multicolor field. The `pDTb` class header also contains an `Atrb` string, which is normally empty, and its `VwBh` contains the standard `Name`, `Index`, `Super`, `Left`, `Top`, `Width`, `Height`, `Enabled`, and `Visible` properties. These are single-file defaults reconstructed from the more compact toolbar companion rather than user-authored toolbar fields.

A toolbar item states `Enabled` only when the item is disabled; an enabled item states nothing.
