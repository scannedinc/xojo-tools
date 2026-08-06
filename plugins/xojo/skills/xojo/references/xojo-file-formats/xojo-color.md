# `.xojo_color`

Color assets are text files containing one `ColorGroup` symbol and one or more platform/appearance representations. A group can contain either one record or multiple records.

```text
#tag ColorGroup
   CodeName=AccentColor
   #tag Color
      Type=1
      Platform=0
      Light=3366FFFF
      Dark=6699FFFF
   #tag EndColor
#tag EndColorGroup
```

`CodeName` on the group is the project symbol. A `Name` inside a Type 2 record instead names the platform/system color. Color bytes are eight bare hex digits in `RRGGBBAA` form; unlike Xojo source colors, these values do not start with `&c`.

## Observed color forms

| `Type` | Stored fields | Meaning established by examples |
| --- | --- | --- |
| `0` | `Light` | One fixed color |
| `1` | `Light`, `Dark` | Paired light/dark appearance colors |
| `2` | `Name` | Named platform/system color |

Named examples include Apple-style names such as `labelColor`, Android tokens such as `Android|disabled_text`, Windows tokens such as `win|1`, Web named colors such as `web|Maroon`, and Bootstrap tokens such as `bootstrap|tertiary-bg`.

The current `Platform` values are:

| `Platform` | Project families observed |
| --- | --- |
| `1` | Desktop |
| `2` | iOS and Android |
| `3` | Web |

All three `Type` values occur with each current platform value. `Platform=0` also occurs in older iOS examples as a fixed fallback record beside a `Platform=2` named color, but its full cross-target semantics have not been isolated. Keep the numeric value paired with the data produced by the target IDE.

For `Platform=2`, the provider is carried by `Name`, not by a separate iOS or Android platform number. Both project families can contain Apple names and `Android|...` names, and both serialize with `Platform=2`.

A group can contain several records for different platforms, all contributing to the one `CodeName` symbol. For example, one group pairs an iOS named color record with a fixed fallback record. The `.xojo_project` manifest references the file as one `ColorAsset` item, and code uses the group `CodeName`.
