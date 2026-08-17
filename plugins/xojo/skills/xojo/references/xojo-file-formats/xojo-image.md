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

- `PartialPath` is normally the portable project-relative path and uses backslashes as its separator. It is relative to the directory holding the project file that references the image, not to the image declaration itself, so a converter writing the project to a different directory must resolve the stored path against the original location and re-express it against the new one. Writing the string unchanged aims it at nothing whenever the two directories differ, which is what happens when a binary project — a single file — becomes a project directory one level deeper.
- `FullPath` is an absolute path from the creating machine. It is useful to the IDE but is not portable, and it cannot be used to re-aim `PartialPath`: it names an ancestor directory rather than the one `PartialPath` is relative to.
- `SaveInfo` is opaque Base64 bookmark/alias data. Do not decode, edit, or synthesize it unless its platform format is independently understood. One structural property is worth stating because it makes a naive reading look plausible: the path inside a bookmark is an array of offsets into the blob, one entry per path component, and identical component strings are stored once and referenced by every entry that uses them. A path that repeats a folder name therefore holds that name once, and reading the stored strings in sequence yields a path that appears to have had a component dropped.

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
