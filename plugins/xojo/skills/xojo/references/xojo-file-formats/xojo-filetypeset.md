# `.xojo_filetypeset`

A file type set is a tagged group of one or more `FileType` records. Both single-record and multi-record sets occur, so the filename is a group name rather than necessarily a single type.

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

`Extension` can contain a semicolon-separated list and examples vary on whether each suffix starts with a dot. Preserve the leading-dot convention of the source item. `UTIConformsTo` can also contain a delimiter list; a leading comma is valid format data and must not be normalized away.

Tagged text and the binary `cnfT` record can hold different values. On export the IDE appends `,<UTIPhysicalType>` to the conformance list unless the list already contains that type, so an empty `cnfT` becomes a text value with a leading comma. On import it stores the text value without removing the appended type, but spaces every separator: importing `,public.data` stores `, public.data`. No observed `cnfT` record uses a comma that is not followed by a space. A file type definition whose physical type was absent from `cnfT` therefore does not survive an IDE export and reimport byte-for-byte, while a definition that already includes it can remain unchanged. A conversion reproduces each direction rather than trying to invert the other.

A project can contain multiple file type groups. Each `FileTypeSet` row in the manifest names a separate `.xojo_filetypeset` companion, and each companion becomes an independent XML `FileTypes` block or RbBF `pFTy` block. A current IDE-written project with groups named `ImagesFileTypes`, `MovieFileTypes`, and `DocumentTypes` stores three blocks containing five, two, and three `FileType`/`fTyp` definitions respectively. Group names are not required to be `FileTypes`.

The project-wide XML `Project` block and RbBF `Proj` block also permit `FileType`/`fTyp` records, but this is a separate legacy duplication rather than the representation of file type groups. Across the paired IDE files, those project-wide records occur only for a group named exactly `FileTypes`; differently named groups remain fully represented by their own `FileTypes`/`pFTy` blocks and are not copied into `Project`/`Proj`. The three-group project described above consequently has ten definitions in its three group blocks and none in its project block.

`MacCreator` and `MacType` are legacy four-byte codes. Tagged text omits trailing spaces, so a value such as `MacType=BMP` becomes `BMP ` in XML and RbBF. Empty values remain empty; nonempty values shorter than four bytes are padded on the right when converted to either single-file format.

Observed `Flags` are `&h0`, `&h1`, `&h2`, `&h5`, and `&h9`; observed `HandlerRank` values are `&h5`, `&h9`, and `&h11`. Not every bit or rank is assigned. Both `Imported=True` and `Imported=False` occur (with casing varying in older files).

`DocIcon` references a resource sidecar, not an image item ID:

```text
DocIcon=ProjectName.xojo_resources;&h0
```

The suffix is the hexadecimal byte offset of the selected top-level `ICNS` record within that file. See [xojo-resources.md](xojo-resources.md).

When the special project-wide copy exists, its definitions retain the same field values and optional document icon as the definitions in the `FileTypes`/`pFTy` block named `FileTypes`. Other groups have no project-wide copy.
