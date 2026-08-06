# `.xojo_library`

A compiled Xojo library is a ZIP archive. It is generated from a `Library` project item and contains API descriptions plus platform/architecture object files. Treat compiled object payloads as opaque and let the matching Xojo IDE produce them.

## Observed archive layout

A Desktop library has this structure:

```text
Library1/
  LibraryInfo.json
  Desktop/
    API/
      Fruit.xojo_code
      Module1.xojo_code
    OSX_x86_64/
      Fruit.o
      Module1.o
    OSX_ARM64/
      Fruit.o
      Module1.o
    Linux_x86_64/
      Fruit.o
      Module1.o
    Windows_x86_64/
      Fruit.o
      Module1.o
```

The root directory is the library name. Immediately below it, a target-family directory contains `API/` and the object-code directories. These layouts are established:

| Project type | Target-family directory | Object-code directories |
| --- | --- | --- |
| Desktop | `Desktop/` | `OSX_x86_64`, `OSX_ARM64`, `Linux_x86_64`, `Windows_x86_64` |
| Console | `Console/` | `OSX_x86_64`, `OSX_ARM64`, `Linux_x86_64`, `Windows_x86_64` |
| Web | `Web/` | `OSX_x86_64`, `OSX_ARM64`, `Linux_x86_64`, `Windows_x86_64` |
| iOS | `iOS/` | `iOS_ARM64` |

Each target-family archive has one `API/` directory under its target-family directory. Platform and architecture directory names are format data and should not be normalized. Xojo does not support libraries in Android projects, so there is no Android target-family layout. Debug, simulator, and additional architecture layouts remain unassigned.

## `LibraryInfo.json`

The root metadata file is pretty-printed JSON. Observed keys are:

```json
{
  "Version": "MyVersion",
  "Copyright": "MyCopyright",
  "Description": "MyDescription",
  "BuildDate": "2026-07-31 14:54:36",
  "IDEVersion": "2026.021",
  "AndroidPackage": ""
}
```

The three user-entered values come from the project settings serialized as `ShortVersion`, `LongVersion`, and `InfoVersion`, respectively. A populated Windows `WinFileDescription` does not replace `Description` and is not copied to another observed JSON key. All four documented target families use the same metadata keys. Preserve unknown keys. `BuildDate` is local-looking text with no serialized timezone.

## API source

Files under `<target-family>/API/` use the ordinary `.xojo_code` grammar, but they are an interface view rather than original source:

- exported class/module declarations and their exposed signatures are retained in the samples; protected and private constructors remain present with their original scope flags;
- method bodies are emptied;
- private stored properties are omitted;
- Inspector metadata can be regenerated or reduced.

Consumers should read these files for signatures only. They must not be used to reconstruct the library implementation.

## Consumer project behavior

A `.xojo_library` is discovered when it is either beside the project or in the IDE's plugins folder. It is not added as a project item. Compilation resolves types and modules against the libraries available in those locations, so the `.xojo_project` manifest contains no library-file row or search-path reference. Do not invent a manifest reference for a consumed library.
