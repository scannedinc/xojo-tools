# Xojo project-format reference

This directory documents Xojo's three project formats and the companion files used by the multi-file **Xojo Project** text format. All format relationships and confidence qualifiers are described within this directory.

Use the narrowest relevant file:

| Need | Format or file extension | Read |
| --- | --- | --- |
| Single-file Xojo XML Project format | `.xojo_xml_project` | [xojo-xml-project.md](xojo-xml-project.md) |
| Single-file Xojo Binary Project (`RbBF`) format | `.xojo_binary_project` | [xojo-binary-project.md](xojo-binary-project.md) |
| RbBF four-character tags and their XML names | `.xojo_binary_project` ↔ `.xojo_xml_project` | [xojo-binary-xml-mapping.md](xojo-binary-xml-mapping.md) |
| What an individual RbBF tag denotes, including tags with no XML element | `.xojo_binary_project` | [rbbf-tag-dictionary.md](rbbf-tag-dictionary.md) |
| Tags, `Begin` blocks, values, escaping, flags, compatibility expressions, Inspector metadata | `.xojo_code`, `.xojo_window`, `.xojo_menu`, `.xojo_report`, `.xojo_toolbar`, `.xojo_image`, `.xojo_color`, `.xojo_filetypeset` | [shared-text-grammar.md](shared-text-grammar.md) |
| Differences between the legacy and current tagged-text generations | `.rbbas`, `.rbfrm`, `.rbmnu`, `.rbtbar`, `.rbres` ↔ `.xojo_code`, `.xojo_window`, `.xojo_menu`, `.xojo_toolbar`, `.xojo_resources` | [xojo-code-generations.md](xojo-code-generations.md) |
| Project manifest, Navigator hierarchy, namespaces, external assets | `.xojo_project` | [xojo-project.md](xojo-project.md) |
| Source-file overview and top-level variants | `.xojo_code` | [xojo-code.md](xojo-code.md) |
| Compiled Xojo library archive | `.xojo_library` | [xojo-library.md](xojo-library.md) |
| Methods, properties, events, classes, modules, interfaces, constants, declares, delegates, enums, structures, notes | `.xojo_code`, `.xojo_window`, `.xojo_report` | [xojo-code-language.md](xojo-code-language.md) |
| Web/mobile screens, dialogs, containers, layouts, launch screens, table cells, sessions and workers | `.xojo_code` | [xojo-code-ui.md](xojo-code-ui.md) |
| Build, sign, copy-file and IDE-script steps | `.xojo_code` | [xojo-code-build-automation.md](xojo-code-build-automation.md) |
| Desktop windows, containers and controls | `.xojo_window` | [xojo-window.md](xojo-window.md) |
| Menus and menu item trees | `.xojo_menu` | [xojo-menu.md](xojo-menu.md) |
| Desktop toolbars | `.xojo_toolbar` | [xojo-toolbar.md](xojo-toolbar.md) |
| File types and file type sets | `.xojo_filetypeset` | [xojo-filetypeset.md](xojo-filetypeset.md) |
| Color groups | `.xojo_color` | [xojo-color.md](xojo-color.md) |
| Images, scale variants, app icons and launch-image sets | `.xojo_image` | [xojo-image.md](xojo-image.md) |
| IDE-managed SQLite connections | `.xojo_database_connection` | [xojo-database-connection.md](xojo-database-connection.md) |
| Report layouts | `.xojo_report` | [xojo-report.md](xojo-report.md) |
| Compiled icon resources | `.xojo_resources` | [xojo-resources.md](xojo-resources.md) |
| IDE UI state, breakpoints, bookmarks, and transient editor state | `.xojo_uistate` | [xojo-uistate.md](xojo-uistate.md) |
| IDE scripts | `.xojo_script` | [xojo-script.md](xojo-script.md) |

## Safety rules for generators and editors

1. Treat tag names, key names, capitalization, and ordering as format data. Preserve unknown entries. Tagged-text indentation is structural; XML indentation between elements is presentation whitespace.
2. Do not synthesize or renumber project item IDs unless creating a genuinely new item. IDs are referenced from manifests, windows, layouts and toolbars.
3. Do not treat an omitted property as equivalent to an empty or false value.
4. Copy an existing item of the same platform and kind when possible. Xojo has accumulated legacy spellings and duplicate compatibility properties.
5. Let the Xojo IDE open and save generated projects before considering a transformation validated.
6. Ignore `.xojo_uistate` in source control. It is transient binary editor state, not project source.

## Confidence terminology

These files qualify their statements, and the qualifiers are not interchangeable.

- **Observed** — the construct occurs in Xojo-written files. Its shape is described as found; what governs it may not be.
- **Established** — the construct's meaning is pinned down, so a reader may rely on it and a writer may produce it.
- **Opaque** — the field's shape is known but its meaning is not. Numeric values and bit fields described this way must be preserved as they stand rather than interpreted or regenerated.

Where a statement carries no qualifier, it is established.
