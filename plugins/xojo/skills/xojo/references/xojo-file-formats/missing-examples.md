# Remaining examples needed

These examples would resolve format details that are not assigned safely by the current reference. Use Xojo Project (text) format and keep each project small.

## Libraries, assets, and dependencies

- Add at least two Android package dependencies to one project, ideally one with version qualifiers, to determine the multi-value delimiter and escaping.
- Create a file type set by changing one Inspector option at a time: exported versus imported UTI, multiple conformances, each handler rank, each IDE-visible option, creator/type codes, and multiple document icons, to map the remaining `Flags` and `HandlerRank` values.
- Isolate the meaning of legacy color-group `Platform=0`.
- Save ordinary images and complete app-icon/launch-image sets for every supported platform and scale, including intentionally empty slots, to map every `Device`/`Platform`/`Orientation` value.
- Starting with one PNG-backed macOS app icon, isolate which project or image condition makes an RbBF save preserve compressed PNG chunks with empty masks versus expand them into four-byte pixels with populated masks.

## UI and IDE state

- Save a minimal window with two controls of the same class and no implemented events, then add and remove one event and duplicate one control across separate saves, to determine when the IDE shares an empty `CBhv` entry and when it allocates equivalent separate entries.
- Save the same minimal built-in controls in each available IDE generation to isolate version-dependent `PDef` type, Inspector-group, visibility, and `Enco` metadata for properties such as `Scope`, `InitialParent`, `TabPanelIndex`, and `AllowTabStop`.
- Save a plain `DesktopCanvas` from a new project and from a migrated project as each format to determine when tagged-text `TabStop` becomes binary/XML `AllowTabStop` and when it remains `TabStop`.
- In a minimal Desktop and Mobile project, compare the original `App` block with a binary produced by opening the exported Xojo Project and saving it as binary, to establish whether omitted `Index`, `Super`, `Left`, and `Top` application-object `PDef` records are regenerated or intentionally remain absent on text import.
- In minimal Android and Mobile projects, perform the same import/resave comparison for the App theme-color `PDef` records and the `MobileScreen.Index` `PDef`; their `ViewProperty` defaults are present in text, but otherwise equivalent binaries inconsistently allocate instance values.
- Create and resave a minimal subclass of `WebToolbar` to determine whether its framework instance defaults are regenerated when tagged text carries only its `ViewProperty` declarations.
- Create equivalent current Web, iOS, and Android custom controls with custom Inspector properties, plus each platform toolbar/button/event variant.
- Create one minimal mobile screen that varies one `AutoLayout` field at a time: relation, source/target attribute, priority, multiplier, constant, active state, and safe-area target.
- In one current mobile project, add iOS and Android screens, containers, navigation and tab layouts, launch screens, and custom table cells, saving after each item.
- Save one external file reference, move the project and referenced file independently, and resave after each move to distinguish when `path`, `ppth`, and the macOS `svin` bookmark are regenerated.

## Build, database, and reports

- Add database connections for every supported engine and stage, including a remote server, encryption, extensions, populated metadata, auto-connect, and a nondevelopment selected stage.
- Create reports containing every available band and report control, grouping and sorting options, expressions, images, and nonempty report events/methods.

## Recommended capture procedure

Record the exact Xojo version, host OS, project type, and single IDE action for each save. Commit or otherwise preserve the before/after pair, including the generated `.xojo_uistate` for research. These isolated diffs distinguish format behavior from project history and IDE-version differences.
