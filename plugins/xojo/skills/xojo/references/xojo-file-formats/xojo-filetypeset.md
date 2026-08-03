# `.xojo_filetypeset`

A file type set is a tagged group of one or more `FileType` records. The expanded corpus contains both single-record sets and sets with many records, so the filename is a group name rather than necessarily a single type.

```text
#tag FileTypeSet
   #tag FileType
      CodeName=TextFile
      Extension=.txt;text
      Flags=&h0
      MacCreator=
      MacType=TEXT
      Name=Text File
      UTI=public.plain-text
      UTIConformsTo=public.text
      Description=Plain text document
      MimeType=text/plain
      Imported=false
      HandlerRank=&h9
      UTIPhysicalType=public.data
   #tag EndFileType
#tag EndFileTypeSet
```

The values are unquoted text after the first `=`. Empty values are meaningful. Observed fields are:

- identity: `CodeName`, `Name`, and `Description`;
- filename/content metadata: `Extension`, `MimeType`, `MacCreator`, and `MacType`;
- Uniform Type Identifier metadata: `UTI`, `UTIConformsTo`, `UTIPhysicalType`, `Imported`, and `HandlerRank`;
- `Flags`, an opaque bitmask;
- optional `DocIcon`.

`Extension` can contain a semicolon-separated list and examples vary on whether each suffix starts with a dot. Preserve the leading-dot convention of the source item. `UTIConformsTo` can also contain a delimiter list; one corpus value begins with a comma, which must not be normalized away.

Observed `Flags` are `&h0`, `&h1`, `&h2`, `&h5`, and `&h9`; observed `HandlerRank` values are `&h5`, `&h9`, and `&h11`. The examples do not provide enough controlled differences to assign every bit or rank. Both `Imported=True` and `Imported=False` occur (with casing varying in older files).

`DocIcon` references a resource sidecar, not an image item ID:

```text
DocIcon=ProjectName.xojo_resources;&h0
```

The suffix is the hexadecimal byte offset of the selected top-level `ICNS` record within that file. See [xojo-resources.md](xojo-resources.md).
