# `.xojo_resources`

This is a binary compiled-icon sidecar. It is not a generic asset archive and must not be decoded as Xojo tagged text. Files can contain one or many concatenated top-level records; resource-rich applications in the expanded corpus contain a separate record for each selectable document icon.

All integers described below are unsigned big-endian 32-bit values unless a consumer imposes a narrower limit.

## Top-level record

```text
offset  size  meaning
0       4     ASCII "ICNS"
4       4     marker, observed value 8
8       4     payload byte length N
12      N     zero or more icon chunks
```

An empty record is exactly these 12 bytes:

```text
49 43 4E 53  00 00 00 08  00 00 00 00
I  C  N  S        8              0
```

A zero-byte `.xojo_resources` placeholder also occurs in older projects and is readable as an empty resource set. Xojo 2026.2.1 rewrites such a placeholder as the 12-byte empty record above, so validators can accept the old form with a migration warning.

If bytes remain after the declared payload, parse another top-level `ICNS` record at the next offset. This occurs in file-type icon resources; it must not be mistaken for trailing corruption. The next record begins at the current record offset plus `12 + N`.

## Icon chunks

The payload is a sequence of chunks:

```text
offset  size  meaning
0       4     four-byte chunk code
4       4     chunk data length M
8       M     chunk data
```

Unlike the standard macOS `icns` chunk convention, the observed chunk length excludes the 8-byte chunk header. The outer uppercase `ICNS` wrapper also has a separate marker and payload-length field. A parser should therefore implement this observed Xojo framing rather than pass the whole file directly to a standard ICNS parser.

One older variant writes the 12-byte `ICNS`, marker, and zero-length prefix and then places a single chunk stream directly after it through EOF. The chunk records retain the same `4-byte code + 4-byte data length + data` framing. A reader can distinguish this from a modern empty record because bytes remain and the next four bytes are a chunk code rather than another `ICNS` record. Xojo 2026.2.1 accepted a project containing this representation but rewrote its resource sidecar as a 12-byte empty record. Treat it as structurally readable legacy data and warn that a current-IDE save will migrate or discard it.

Observed chunk codes are `ICN#`, `h8mk`, `ic07`, `ic08`, `ic09`, `ic10`, `ic1m`, `ich#`, `ich8`, `icl8`, `ics#`, `ics8`, `ih32`, `il32`, `is32`, `it32`, `jp2m`, `l8mk`, `s8mk`, `t8mk`, and `x8mk`. Some payloads begin with a PNG signature; others are legacy planar image data or masks. Chunk codes and payloads should remain opaque unless the corresponding Apple icon format is implemented deliberately.

## References and editing guidance

Manifest settings such as `AppIcon=Project.xojo_resources;&h0` and file type `DocIcon` values refer to this sidecar plus a hexadecimal selector. Controlled correlation against files containing many records establishes that the selector is the byte offset of the chosen top-level `ICNS` record. For example, a record with payload length `0x257F0` occupies `12 + 0x257F0 = 0x257FC` bytes, and the next document icon is referenced with `;&h257FC`. Empty 12-byte records likewise advance selectors from `;&h0` to `;&hC` to `;&h18`.

Validate a selector by seeking to that offset and requiring the `ICNS` magic. Do not treat it as an ordinal or project item ID.

Prefer letting Xojo regenerate resources from source icons. If a binary editor must preserve a file, validate every boundary:

1. top-level magic is `ICNS`;
2. the observed marker is `8`;
3. the outer payload ends exactly at the next record or EOF;
4. every chunk header and data area fits inside that payload.

For the legacy zero-length-wrapper variant, apply the same chunk boundary checks through EOF instead of the zero-byte outer payload boundary.

A controlled malformed example contained one valid record followed by another icon-sized byte range without an `ICNS` wrapper at the declared next-record offset. Xojo 2026.2.1 re-saved exactly the valid first 5,588,572-byte prefix and discarded the malformed remainder. This confirms that nonzero trailing data must begin with another top-level `ICNS` record; it is not an implicit second chunk stream.

Do not confuse this format with `.xojo_image`, which is a text descriptor for external image representations.
