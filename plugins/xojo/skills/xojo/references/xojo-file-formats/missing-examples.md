# Remaining examples needed

These examples would resolve format details that cannot be assigned safely from the current corpus. Use Xojo Project (text) format and keep each project small.

## Libraries, assets, and dependencies

- Add at least two Android package dependencies to one project, ideally one with version qualifiers, to determine the multi-value delimiter and escaping.
- Create a file type set by changing one Inspector option at a time: exported versus imported UTI, multiple conformances, each handler rank, each IDE-visible option, creator/type codes, and multiple document icons, to map the remaining `Flags` and `HandlerRank` values.
- Isolate the meaning of legacy color-group `Platform=0`.
- Save ordinary images and complete app-icon/launch-image sets for every supported platform and scale, including intentionally empty slots, to map every `Device`/`Platform`/`Orientation` value.

## UI and IDE state

- Make a current desktop project with a small indexed control set, nested page/tab panels, and a custom `DesktopContainer` exposing one property for every Inspector editor type. Save after each change to isolate `Index`, parent, panel, and editor metadata.
- Create equivalent current Web, iOS, and Android custom controls with custom Inspector properties, plus each platform toolbar/button/event variant.
- Create one minimal mobile screen that varies one `AutoLayout` field at a time: relation, source/target attribute, priority, multiplier, constant, active state, and safe-area target.
- In one current mobile project, add iOS and Android screens, containers, navigation and tab layouts, launch screens, and custom table cells, saving after each item.
- Add breakpoints in a method, property accessor, class event, control event, and IDE script; add a conditional breakpoint and Navigator/code bookmark if supported.
- Save a Worker with an explicitly empty `ProjectItemsToInclude` setting.

## Build, database, and reports

- Add an external-script build step on every supported target.
- Create copy-file steps while varying exactly one option at a time across all destinations, build stages, architectures, and targets, to assign the numeric enum meanings.
- Add database connections for every supported engine and stage, including a remote server, encryption, extensions, populated metadata, auto-connect, and a nondevelopment selected stage.
- Create reports containing every available band and report control, grouping and sorting options, expressions, images, and nonempty report events/methods.

## Recommended capture procedure

Record the exact Xojo version, host OS, project type, and single IDE action for each save. Commit or otherwise preserve the before/after pair, including the generated `.xojo_uistate` for research. These isolated diffs distinguish format behavior from project history and IDE-version differences.
