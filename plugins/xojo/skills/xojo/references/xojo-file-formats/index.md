# Xojo project text-format reference

This directory documents the files that make up a Xojo text project (the IDE calls this the **Xojo Project** format). The descriptions were derived from a large corpus of example and real-world projects and, where noted, from controlled Xojo 2026r2.1 experiments.

Use the narrowest relevant file:

| Need | Read |
| --- | --- |
| Tags, `Begin` blocks, values, escaping, flags, compatibility expressions, Inspector metadata | [shared-text-grammar.md](shared-text-grammar.md) |
| Project manifest, Navigator hierarchy, namespaces, external assets | [xojo-project.md](xojo-project.md) |
| `.xojo_code` overview and top-level variants | [xojo-code.md](xojo-code.md) |
| Compiled Xojo library archive | [xojo-library.md](xojo-library.md) |
| Methods, properties, events, classes, modules, interfaces, constants, declares, delegates, enums, structures, notes | [xojo-code-language.md](xojo-code-language.md) |
| Web/mobile screens, dialogs, containers, layouts, launch screens, table cells, sessions and workers | [xojo-code-ui.md](xojo-code-ui.md) |
| Build, sign, copy-file and IDE-script steps | [xojo-code-build-automation.md](xojo-code-build-automation.md) |
| Desktop windows, containers and controls | [xojo-window.md](xojo-window.md) |
| Menus and menu item trees | [xojo-menu.md](xojo-menu.md) |
| Desktop toolbars | [xojo-toolbar.md](xojo-toolbar.md) |
| File types and file type sets | [xojo-filetypeset.md](xojo-filetypeset.md) |
| Color groups | [xojo-color.md](xojo-color.md) |
| Images, scale variants, app icons and launch-image sets | [xojo-image.md](xojo-image.md) |
| IDE-managed SQLite connections | [xojo-database-connection.md](xojo-database-connection.md) |
| Report layouts | [xojo-report.md](xojo-report.md) |
| Compiled icon resources | [xojo-resources.md](xojo-resources.md) |
| IDE UI state, breakpoints and transient editor state | [xojo-uistate.md](xojo-uistate.md) |
| IDE scripts | [xojo-script.md](xojo-script.md) |
| Features for which the corpus has no adequate example | [missing-examples.md](missing-examples.md) |

## Safety rules for generators and editors

1. Treat tag names, key names, capitalization, ordering and indentation as format data. Preserve unknown entries.
2. Do not synthesize or renumber project item IDs unless creating a genuinely new item. IDs are referenced from manifests, windows, layouts and toolbars.
3. Do not treat an omitted property as equivalent to an empty or false value.
4. Copy an existing item of the same platform and kind when possible. Xojo has accumulated legacy spellings and duplicate compatibility properties.
5. Let the Xojo IDE open and save generated projects before considering a transformation validated.
6. Ignore `.xojo_uistate` in source control. It is transient binary editor state, not project source.

## Evidence and confidence

“Observed” means a construct occurs in the project corpus behind this reference. “Established” is reserved for a mapping confirmed by controlled IDE save/diff experiments or by an exact cross-file correlation (such as a resource selector landing on an `ICNS` record boundary). Unexplained numeric values and bit fields are explicitly described as opaque; preserve them instead of guessing.
