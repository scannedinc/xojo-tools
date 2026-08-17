# Xojo binary project (`.xojo_binary_project`)

This document describes the `RbBF` container used by the single-file Xojo Binary Project format and its relationship to the XML and text formats.

All integers are big-endian.

## File header

The observed header is 28 bytes:

| Offset | Size | Meaning |
| ---: | ---: | --- |
| 0 | 4 | ASCII `RbBF` |
| 4 | 4 | format version; observed value `2` |
| 8 | 4 | reserved; observed as zero |
| 12 | 4 | reserved; observed as zero |
| 16 | 4 | header size; observed value `28` |
| 20 | 4 | reserved; observed as zero |
| 24 | 4 | minimum IDE version as `YYYYRRVV` |

Blocks begin at the offset recorded by the header-size field. The file ends immediately after the four bytes `EOF!`.

## Blocks

Each block begins with a 32-byte header:

| Offset | Size | Meaning |
| ---: | ---: | --- |
| 0 | 4 | ASCII `Blok` |
| 4 | 4 | block-type four-character code |
| 8 | 4 | opaque project item ID |
| 12 | 4 | reserved |
| 16 | 4 | total block size, including header and padding |
| 20 | 12 | three reserved integers |

Observed block sizes are multiples of 1024. Records follow the header. A block ends with `PadnPadn`, a four-byte padding length, and that many ASCII `*` bytes. The length must land exactly at the boundary declared by the block header.

Project-item IDs are opaque. The manifest text format can retain 64-bit ID spellings, while the compared binary and XML blocks expose the low 32-bit pattern. Cross references frequently render that pattern as a signed decimal.

## Records

A record begins with a four-character semantic tag and a four-character value type. The following value types are established:

| Type | Payload |
| --- | --- |
| `Int ` | signed 32-bit integer |
| `Dbl ` | IEEE-754 binary64 |
| `Strn` | unsigned byte length, raw bytes, then spaces to four-byte alignment |
| `Rect` | four signed 32-bit integers |
| `Grup` | nested record group described below |

A `Grup` payload begins with an unsigned length and opaque group ID. The length starts at the group-ID field and ends immediately before the closing record. Nested records follow, then `EndGInt ` and the same group ID. Group IDs do not carry known semantics; newly generated files allocate unique sequential IDs.

Strings are byte sequences rather than inherently UTF-8 values. When expressed as XML, values that cannot be represented safely as ordinary XML character data, including tab- and line-break-bearing strings, use Xojo's `<Hex bytes="...">...</Hex>` representation.

## Ordering

Record and block order is part of the serialized model. A writer must preserve the input order of blocks, records, and repeated groups unless it is reconstructing fields omitted by the input format and has an established target order. Alphabetically sorting records or appending reconstructed header records after members can produce a binary project that the IDE reports as containing unsupported items.

The `Proj` block is first in established IDE-written projects. When present, the `pUIs` UI-state block is last. Blocks between them retain project-item order. `Cont` references do not imply a universal parent-before-child rule: build-step lists and a small number of nested project items validly refer to a container that appears later. A converter must therefore retain explicit source order rather than globally topologically sorting blocks.

Build-step blocks are not individual manifest rows in Xojo Project format. Their companion records list and step order but does not record where the generated binary blocks were positioned relative to the `BSts` Build Automation container or unrelated project items. Established binaries place the step sequence both immediately before and immediately after `BSts`; a valid IDE resave can also preserve a canonical text import in which `BSts` remains at its manifest position and all generated step blocks occur near the end. Preserve explicit binary/XML order when it exists, but do not infer that one of these text reconstructions is the unique earlier binary order.

Build-step block tags are `BSbu` for Build Project, `BScf` for Copy Files, `BSsc` for an embedded IDE script, `IExs` for an external IDE script, and `BSsn` for Sign Project. `Bsls` is a platform step list and `BSts` is the Build Automation container. Copy Files records follow `Name`, `Cont`, `pasw`, `StpA`, `Arch`, `Targ`, `DstR`, `Dest`, then one `alis` per input. External script records follow `Name`, `Cont`, `pasw`, `StpA`, `Arch`, `Targ`, `alis`. Repeated `alis` records are ordered and must not be collapsed.

Class-like blocks use structural stages. Optional records are omitted without closing the gap between the surrounding stages:

```text
Name, Cont, pasw, bCls, Supr, Intr, flag, bNtr, bApO, Comp
early language members
PDef records
VwBh
Cnst, Strx, Enum, and USng records
platform- or designer-specific records
Rpsc records
CBhv records
Ctrl, Dseg, segB, and segC records
toolbar item records
```

`Supr` and `Intr` are optional. `bApO` is present with value `1` on the application object and absent from every other `pObj` block. It follows the superclass rather than the item name: the application object can be renamed, and every marked block inherits from `Application`, `ConsoleApplication`, `DesktopApplication`, `IOSApplication`, `MobileApplication`, `ServiceApplication`, or `WebApplication`. Early language members include event implementations, methods, delegates, external methods, menu handlers, hooks, notes, and properties. Their relative order must be retained. `PDef` precedes `VwBh`; `CBhv` precedes every placed control. A Worker block's settings are ordinary `PDef` records and occupy that stage, so they follow the block's events, methods, and properties and precede its constants. Tagged text states them in the opposite place: the `#tag Worker` region is written before the language members, so a conversion moves them rather than preserving their textual position. Three IDE-written Worker blocks agree, the largest carrying four event handlers, six methods, eight properties, and two constants. Different placed-control group types can be interleaved and retain their source order.

Several nested groups have fixed record order. Established examples include:

| Group | Record order |
| --- | --- |
| `PDef` | `name`, `type`, `PrGp`, `visi`, optional `Enco`, `PVal` |
| `Meth` and `Dmth` | `name`, `Comp`, optional `Atrb`, `Vsbl`, optional `kCod`, `PtID`, `sorc`, `Enco`, `Alas`, `flag`, `shrd`, `parm`, `rslt` |
| `XMth` | method order followed by `Lib `, `Soft`, `objC` |
| `Prop` | `name`, `Comp`, optional `Atrb`, `Vsbl`, optional `kCod`, `PtID`, `sorc`, `Enco`, `decl`, `flag`, `shrd`, optional `CPrs`, optional `CPrg` |
| `Cnst` | `name`, `Comp`, `Vsbl`, `PtID`, `Enco`, `type`, `defn`, `flag`, then zero or more `CIns` groups |
| `CIns` | `pltf`, `lang`, `defn` |
| `Hook` | `name`, `Enco`, `flag`, `SySF`, `parm`, `rslt`, optional `Atrb`, optional `kCod` |
| `Enum` (2024.04 and later) | `Enco`, `flag`, optional `type`, optional `binE`, `name`, `Comp`, optional `Atrb`, `Vsbl`, `PtID`, `sorc` |
| `Enum` (2020.02 through 2023.02) | `Enco`, `name`, `flag`, optional `type`, optional `binE`, `name`, `Comp`, `Vsbl`, `PtID`, `sorc` |
| ordinary `Ctrl` | `ccls`, `name`, `PDef` records, `HLCn` records, `CBix`, `iLck`, `PtID` |
| report `Ctrl` | `Rpsc`, `ccls`, `PDef` records, `CBix`, `iLck` |
| `HLCn` | `Cni1`, `Ci1a`, `Cni2`, `Ci2a`, `CnLk`, `CnMP`, `CnPr`, `CnRo`, `CnPv`, `HCnm`, `HCla` |
| `MItm` | `spmu`, `name`, `text`, `indx`, `scut`, optional `MiSK`, `MiMk`, `MiAM`, `Mopt`, `MiAK`, and `Icon`, then `maEn`, `Enco`, `mVis`, `flag`, `Name`, `Supr`, and child `MItm` groups |
| `ImgS` | `comM`, `deVi`, `itHt`, `orie`, `plFM`, `resZ`, `itWd`, `itHd`, `itwD` |
| `fTyp` | `name`, `MacC`, `type`, `defn`, `flag`, `kUTI`, `Name`, `cnfT`, `dscR`, `mimT`, `imPo`, `FTRk`, `FTpt`, optional `Icon` |
| `conn` | `name`, `path`, `enky`, `tout`, `tyin`, `ldex`, `wahl` |
| `ti  ` | `Supr`, `name`, `text`, `tis `, `tims`, `bhlp`, `styl`, `enbl`, `flag`, optional `Icon` |
| `brkG` and `bkGP` | `PtID`, `name`, `unTY`, `unID`, `lnNM` |

The older `Enum` layout repeats the enumeration name before `flag` as well as after `binE`, and the two values are always identical. `binE` is not unconditional in either layout; an enumeration may omit it. A conversion retains whichever layout the input expresses instead of rewriting one into the other.

IDE-written XML retains binary block order and the order of binary-representable child records. Xojo Project companions can normalize repeated collections, such as alphabetizing language members or designer properties. A conversion from text cannot infer a previous binary ordering that the text serialization discarded; it must retain the order expressed by the text and reconstruct only the surrounding structural stages.

## Opaque and target-omitted structures

Some structures are framed well enough to preserve without having an assigned meaning:

- The three reserved header integers and four reserved block-header integers are zero in the observed files. They have no XML or text field. A binary rewrite preserves them; a newly constructed binary writes zero. Their purpose cannot be inferred without a file in which one changes.
- Group IDs are unique within an observed file but can begin above one and contain gaps. XML and text omit them. A binary rewrite preserves them; cross-format construction assigns new unique IDs. No semantic or cross-reference relationship has been established.
- Block allocation size, `PadnPadn`, and `*` padding are binary-container allocation details. XML and text omit them. A binary rewrite preserves the allocation when possible; cross-format construction recalculates it.
- Project-item blocks contain a `pasw` string record. It is empty in the observed projects and absent from XML and text. Cross-format construction restores an empty record in its established block position. A nonempty value would need separate study and must not be assumed equivalent to empty.
- An empty `pItm` block occurs as an obsolete placeholder. It has no XML block or text manifest row. Only the established empty form may be omitted; a nonempty `pItm` or any other unknown block must be preserved or treated as an unmapped structure.
- Numeric bit fields such as `Bflg`, `flag`, file-type flags, and platform/architecture selectors can be framed and carried through other formats even when every bit meaning is not assigned. Preserve the raw integer instead of rejecting or normalizing it.

These cases differ from an unknown RbBF primitive value type. A known `Int `, `Strn`, `Dbl `, `Rect`, or `Grup` value with an unknown semantic tag can still be bounded and preserved in binary. An unknown primitive type may have an unknown payload length, so parsing cannot safely resume after it.

## Semantic mappings

Block and record four-character codes correspond to semantic XML names. The complete established correspondence is listed in [xojo-binary-xml-mapping.md](xojo-binary-xml-mapping.md). Unknown codes must be preserved by a lossless editor or rejected; silently discarding them changes the project model.

Placed-control event behavior is indirect. A class-like block stores its `CBhv` groups before its `Ctrl`, `Dseg`, `segB`, or `segC` groups, and each control's integer `CBix` selects one zero-based `CBhv` entry. The selected behavior's `Supr` class must match the control's `ccls` class. Several controls can share one behavior, notably generic controls without implemented events and members of a control set; an event-bearing behavior can therefore also have more than one referring control. Pairing controls and behaviors by list position instead of following `CBix` can attach event handlers to unrelated classes and produces a binary project that the IDE reports as containing unsupported items.

One important non-bijective case is a binary `PDef` group. A complete observed property definition has this order:

```text
name  Strn  property name
type  Strn  Inspector/value type
PrGp  Strn  Inspector group
visi  Int   visibility flag
Enco  Int   text encoding, when the value requires it
PVal  varies property value
```

XML collapses the group to:

```xml
<PropertyVal Name="property-name">value</PropertyVal>
```

The exact omitted values cannot always be recovered from XML or text, but `name` plus `PVal` is not a complete binary property definition. A binary writer must reconstruct `type`, `PrGp`, and `visi`, and must add `Enco` when required. Useful evidence includes the owning class's `VwBh`/`VwPr` schema, the control class, known framework-property schemas, and the value's primitive type. The `VwBh` schema is evidence rather than an authority: a `PDef` and the owning class's `VwBh` entry for the same property can disagree, and `Index` is a known case, carrying `PrGp` `Obsolete` in its `PDef` where the `VwBh` entry states the group `ID`. If the required shape cannot be reconstructed safely, the writer should refuse to emit a binary project rather than serialize the incomplete group. Similar requirements apply to language items, controls, constants, hooks, menus, and toolbars: their RbBF groups contain mandatory metadata that their XML or text spellings may omit.

String-valued property definitions use both `Enco = 134217984` and `Enco = 1536`. The two track whether the value is empty rather than which encoding the text is in: a nonempty string almost always carries `134217984` and an empty one almost always `1536`. Neither correspondence is absolute. This field must not be populated mechanically with the source-code encoding merely because `PVal` has the `Strn` primitive type. Non-string property types do not normally carry `Enco`, even when their compact XML or text value was initially parsed as lexical text before schema completion.

`VwPr` uses a different storage rule from `PDef`. Its `type` record describes the Inspector property, but its optional default `PVal` is a lexical `Strn` even when `type` is `Integer`, `Double`, or `Single`. Converting the default to an `Int ` or `Dbl ` primitive based on `type` does not match IDE-written binary output.

### Concrete round-trip example

"Byte-exact" applies to parsing a binary project and writing that same binary model without translating it. It does not apply after passing through a less expressive format.

Provenance matters when interpreting a three-format comparison. A Xojo Project that was exported from an older binary is not equivalent evidence to a project authored natively as Xojo Project and then saved as binary. The export can omit binary-only allocation choices and can add text syntax, such as a menu handler's `Handles … .Action` clause, that was not present in the source records of the older binary. Reimporting that text follows the current IDE's text-import rules; it cannot reverse the earlier export and recover the older bytes.

For example, a `Top` property can be represented by a `PDef` group containing five records:

```text
name  Strn  "Top"
type  Strn  "Integer"
PrGp  Strn  "Position"
visi  Int   0
PVal  Int   0
```

The corresponding XML contains only:

```xml
<PropertyVal Name="Top">0</PropertyVal>
```

The property type, Inspector group, and visibility flag are absent. XML also does not unambiguously identify the original `PVal` record type. A reconstruction can recover the five-record binary shape from an established property schema, but it cannot claim that inferred metadata is byte-for-byte identical to the source fields that the IDE omitted. For example, a text control's `Scope = 0` supplies neither the binary type nor Inspector group. IDE-written binaries have stored `Scope` as type `Enum`, while generic reconstruction from the lexical value alone can only guess `Integer` or `String`; observed IDE generations also disagree about whether the Inspector group is `ID` or empty.

Method-like groups have the same issue. For example, a complete `Meth` group contains `name`, `Comp`, `Vsbl`, `PtID`, `sorc`, `Enco`, `Alas`, `flag`, `shrd`, `parm`, and `rslt`. A `Prop` group contains `name`, `Comp`, `Vsbl`, `PtID`, `sorc`, `Enco`, `decl`, `flag`, and `shrd`. Emitting only source text loses structural records the IDE expects even though the method declaration remains readable to a custom parser.

There are also byte-level container details that XML does not represent: original group IDs, block allocation sizes, and padding. A binary -> XML -> binary conversion therefore cannot promise byte identity even when the representable project semantics are unchanged. Xojo Project format stores the `pUIs` record stream in the conventionally named hidden `.xojo_uistate` sidecar even though the manifest does not list that file; this data can be carried between binary and text formats, although group IDs may be renumbered when XML is an intermediate format.

Control behavior allocation is another non-bijective case. `CBix` indexes a table of `CBhv` groups. Multiple controls of the same class with no implemented events can share one empty class-compatible behavior group, but IDE-written projects can instead contain separate equivalent empty groups. The text format records no identity for an empty behavior and therefore cannot reveal which allocation the earlier binary used. Both allocations represent the same event behavior, and an IDE resave can preserve the shared form rather than expanding it to the earlier table.

Application-object defaults provide another concrete omission. A binary `App` block can contain `PDef` records such as `Index = -2147483648`, `Super = ""`, `Left = 0`, and `Top = 0`, while the Xojo Project `App.xojo_code` contains only the class declaration and `ViewBehavior` schema. Established binaries with the same application superclass and an `Index` ViewProperty exist both with and without those four `PDef` records. The text form has no marker that distinguishes the two histories, so a converter can use a documented canonical import policy but cannot reconstruct which earlier binary allocation was used.

External-file blocks can contain an absolute `path`, a relative `ppth`, and an `svin` macOS bookmark blob, in that order after the item header. Xojo Project records the relative path but not the previous absolute path or bookmark bytes. A converter can resolve a new absolute path at its current location, but it cannot recreate the previous machine's volume identifier, file identifier, and bookmark serialization byte for byte. The IDE generates a new bookmark when it resolves and resaves the reference.

This distinction is mostly about editor and serialization metadata, not Xojo source code. It is still important: claiming byte identity would imply that omitted values and IDE-version migrations had somehow been reversed exactly. Conversely, treating the fields as optional merely because XML omits them produces a structurally deficient binary project.

### Expected invariants by starting format

An XML -> binary -> XML conversion should preserve the binary-representable XML model, but not necessarily the original XML bytes. XML declaration quoting, indentation, empty-element spelling, and numeric spelling may be canonicalized. For example, a floating-point value written as `0.0` may return as `0`. Some default-only XML fields have no RbBF record; their absence can express the same default while making the XML trees lexically different. See [xojo-xml-project.md](xojo-xml-project.md#relationship-to-rbbf).

A text -> binary -> text conversion has the same normalization plus text-file formatting and manifest-ID normalization. A manifest states an item ID as sixteen hex digits while RbBF stores only the low 32 bits, so the upper half has to be reconstructed on the way back. It is the sign extension of bit 31 of the low half: `FFFFFFFF` where that bit is set and `00000000` where it is clear. An ID written `&hFFFFFFFFB934E1B5` therefore returns as `&hFFFFFFFFB934E1B5`, and nothing is lost.

The exception is an ID whose upper half is neither of those two values, or is the wrong one of them for its low half. Such an ID carries information the binary and XML formats cannot hold, and a conversion through either loses it — not merely respelled but replaced by a different identity, spelled exactly as a deliberate sign-extended ID is. A text-to-text conversion must carry the manifest's own spelling through rather than recompute it. Two IDs differing only above bit 31 are distinct items even though a 32-bit format collapses them onto one.

## Text-project safety and resources

The text format is multi-file. The `.xojo_project` manifest is authoritative for project items: a reader must not enumerate sibling files or consume an unreferenced `.xojo_code` file. The conventionally named hidden `.xojo_uistate` sidecar is the known exception because Xojo does not list UI state in the manifest. Folder and parent IDs determine generated item paths. A writer must reject duplicate target paths before writing.

`.xojo_resources` files can contain multiple concatenated `ICNS` segments. Each segment is `ICNS`, integer `8`, a payload length, and a sequence of four-character resource type, data length, and data. Manifest `AppIcon` and file-type `DocIcon` values select a segment by byte offset. Cross-format tools must preserve this offset model when reading and reconstruct it when writing. Modern PNG chunks embedded into an RbBF `Icon` group are followed by empty legacy mask elements; see [xojo-resources.md](xojo-resources.md#rbbf-icon-groups).

## Limitations

Cross-format results cannot be byte-identical where a target format omits metadata. Legacy or third-party blocks and record tags may extend the vocabulary documented here. Preserve an unknown value with its exact type, ordering, and bytes when possible; otherwise stop rather than guess. A deliberately lossy conversion may omit a safely parsed but unmapped block or record only when it reports the exact omission. Malformed framing, invalid lengths, truncation, and unknown primitive value types are not safely skippable.
