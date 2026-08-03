# `.xojo_report`

Report companions are tagged text layouts. The four examples contain a root report, ordered bands, report controls inside those bands, and a `ReportCode` region.

## Layout shape

```text
#tag Report
Begin Report InvoiceReport
   Compatibility = ""
   Units = 0
   Width = 8.5
   Begin  PageHeader
      Type = 1
      Height = 0.5
      Begin ReportLabel TitleLabel
         Text = "Invoice"
         Left = 0.25
         Top = 0.1
         Width = 2.0
         Height = 0.25
      End
   End
   Begin  Body
      Type = 3
      Height = 0.25
   End
   Begin  PageFooter
      Type = 5
      Height = 0.4
   End
End
#tag EndReport
#tag ReportCode
   ...source members if present...
#tag EndReportCode
```

Band start lines intentionally have two spaces after `Begin`: the class position is empty and the final token is the band name. Do not parse them as ordinary `Begin <class> <instance>` rows.

## Bands

Observed names include `PageHeader`, `Body`, `PageFooter`, `GroupHeader1`, `GroupHeader2`, `GroupFooter1`, and `GroupFooter2`. The corpus correlates band `Type` values as follows:

| Type | Observed band role |
| --- | --- |
| `1` | Page header |
| `2` | Group header |
| `3` | Body/detail |
| `5` | Page footer |
| `6` | Group footer |

No controlled example establishes values `0` or `4`, or all band-ordering and grouping rules. Preserve the IDE's order, names, type values, and long decimal layout values.

## Report controls

Observed control classes are `ReportLabel`, `ReportField`, `ReportPicture`, `ReportRectangleShape`, and `ReportLineShape`. Each is a nested `Begin` block with geometry plus class-specific formatting/data properties. Report fields carry fields such as `DataField`, `OutputFormat`, `SummaryFunc`, `SummaryType`, and `Text`; labels carry literal `Text`. Shapes and pictures have their own border, fill, or image settings.

The control property set is extensible across Xojo versions. Copy an IDE-produced control of the same class and preserve unfamiliar fields rather than reducing it to the properties shown above.

## Report code

The trailing `ReportCode` region is the source container for report methods, properties, events, constants, and related class members. The supplied reports do not provide broad nonempty code coverage; use the member grammar in [xojo-code-language.md](xojo-code-language.md) and an IDE-created report event as the template for executable report code.
