# `.xojo_image`

Despite its extension, `.xojo_image` is tagged text, not image pixels. It describes one logical image and its representations, whose actual PNG/JPEG/etc. files remain external. The same container is used for ordinary images, app-icon slot sets, and launch-image sets.

## Structure

```text
#tag MultiImage
   Image Bell
      #tag ImageRepresentation
         SaveInfo = <opaque Base64>
         FullPath = /developer/path/bell-2x.png
         PartialPath = ..\Images\bell-2x.png
         #tag ImageSpecification
            Comment = 1x
            Device = 0
            HSize = 16
            Orientation = Any
            Platform = 0
            PPI = 72
            VSize = 16
         #tag EndImageSpecification
      #tag EndImageRepresentation
End Image
#tag EndMultiImage
```

There may be many `ImageRepresentation` regions. Their order is part of the IDE's slot table and should be retained.

## Paths and bookmark data

- `PartialPath` is normally the portable project-relative path and uses backslashes in the examples.
- `FullPath` is an absolute path from the creating machine. It is useful to the IDE but is not portable.
- `SaveInfo` is opaque Base64 bookmark/alias data. Do not decode, edit, or synthesize it unless its platform format is independently understood.

An empty app-icon or launch-image slot omits the path/bookmark fields but keeps its `ImageSpecification`. This is not the same as deleting the representation. Parsers should also accept representations without all three path fields.

## Scale variants and specifications

The image container terminates with `End Image`, not a bare `End`. `ImageSpecification` has observed fields `Comment`, `Device`, `HSize`, `VSize`, `Orientation`, `Platform`, and `PPI`. Values are not uniformly numeric—`Orientation = Any` is common. In an ordinary three-scale image, `PPI` values `72`, `144`, and `216` correspond to 1x, 2x, and 3x resources while `HSize`/`VSize` retain the logical design size. One 16-point example therefore uses source files with 2x/4x/6x naming while keeping sizes at 16 and assigning those three PPI values.

Do not infer pixel dimensions solely from filenames. Slot comments and the device/platform/orientation enums are IDE metadata. Not every numeric enum value has a future-proof assigned meaning.

## Ordinary images, app icons, and launch images

The companion syntax alone does not declare its project role. The manifest item kind does:

- `MultiImage` — an ordinary image asset;
- `AppIcons` — the target's app-icon slot table;
- `LaunchImages` — a launch-image slot table.

`Image <name>` supplies the logical name. Preserve empty predefined slots in app-icon and launch-image files: Xojo uses their order and specifications to associate them with platform requirements.

Compiled desktop icons may also appear in `.xojo_resources`; those binary resources are distinct from this external-image descriptor.
