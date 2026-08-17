# Xojo XML Project (`.xojo_xml_project`)

The Xojo XML Project format stores an entire project model in one XML 1.0 document. Unlike the multi-file Xojo Project text format, source items, designer objects, project settings, build steps, and IDE state are all blocks in the same file.

The format uses semantic element names, but it is still a serialization format: element order, block order, IDs, empty values, and unknown elements must be preserved.

## Document framing

Files are UTF-8 XML and normally begin with:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<RBProject version="2026r2.1" FormatVersion="2" MinIDEVersion="20210300">
  ...
</RBProject>
```

The root attributes are:

| Attribute | Meaning |
| --- | --- |
| `version` | Human-readable IDE release spelling, such as `2026r2.1` |
| `FormatVersion` | Numeric project-container format; `2` is established |
| `MinIDEVersion` | Minimum IDE version as `YYYYRRVV`, such as `20210300` |

`version` is related to the Project block's `ProjectSavedInVers` value. For example, `ProjectSavedInVers=2026.021` is rendered as `version="2026r2.1"`. Do not derive `MinIDEVersion` from either value; it is an independent compatibility field.

Every direct child of `RBProject` is a `block`:

```xml
<block type="Module" ID="1710984300">
  <ObjName>App</ObjName>
  <ObjContainerID>0</ObjContainerID>
  ...
</block>
```

`type` selects the block grammar. `ID` is the project's opaque 32-bit object identifier written as decimal; negative decimal spellings represent the same raw bit patterns as unsigned values above `2147483647`. The Project block uses ID `0`. References such as `ObjContainerID`, `DefaultViewID`, menu IDs, and control IDs compare as 32-bit patterns.

## Block types

The following block types and RbBF correspondences are established.

| XML `type` | RbBF tag | Purpose |
| --- | --- | --- |
| `Project` | `Proj` | Project-wide settings and defaults |
| `UIState` | `pUIs` | IDE editor state, breakpoints, and bookmarks |
| `Folder` | `pFol` | Navigator hierarchy folder |
| `Module` | `pObj` | Class, module, interface, App, or other source object |
| `Window` | `pVew` | Legacy desktop window |
| `DesktopWindow` | `pDWn` | Current desktop window or container |
| `WebView` | `xWbV` | Web page or dialog |
| `WebContainer` | `xWbC` | Web container control |
| `WebSession` | `xWSs` | Web session source object |
| `MobileScreen` | `mobv` | Current mobile screen |
| `MobileContainer` | `mobc` | Current mobile container |
| `IOSScreen` | `pScn` | iOS screen |
| `IOSLayout` | `pLay` | iOS layout/navigation tree |
| `IOSLaunchScreen` | `ioLS` | iOS launch screen |
| `iOSContainer` | `iosC` | iOS container or related design item |
| `NotificationCenter` | `NotC` | Mobile notification-center source item |
| `Worker` | `WrKr` | Worker source and settings |
| `Menu` | `pMnu` | Menu tree |
| `DesktopToolbar` | `pDTb` | Desktop toolbar and tool items |
| `Toolbar` | `pTbr` | Legacy toolbar and tool items |
| `FileTypes` | `pFTy` | File type set |
| `ColorAsset` | `colr` | Color group |
| `MultiImage` | `Img ` | Ordinary multi-resolution image |
| `ApplicationIcon` | `Aicn` | Application icon set |
| `LaunchImages` | `Limg` | Launch-image set |
| `Report` | `pRpt` | Report layout and code |
| `PostgreSQLConnection` | `pDC1` | IDE-managed PostgreSQL connection |
| `SQLiteLocalConnection` | `pDC2` | IDE-managed SQLite connection |
| `MySQLConnection, ` | `pDC3` | IDE-managed MySQL connection |
| `ODBCConnection` | `pDC4` | IDE-managed ODBC connection |
| `BuildAutomation` | `BSts` | Build-automation source item |
| `BuildStepsList` | `Bsls` | Ordered project build steps |
| `BuildProjectStep` | `BSbu` | Built-in build-project step |
| `SignProjectScriptStep` | `BSsn` | Signing-script step |
| `CopyFilesStep` | `BScf` | Copy-files step |
| `IDEScriptStep` | `BSsc` | Build step containing embedded XojoScript source |
| `ExternalScriptStep` | `IExs` | Build step referencing an external `.xojo_script` |
| `Script` | `pScp` | IDE script |
| `Picture` | `pPic` | External picture reference |
| `Sound` | `pSnd` | External sound reference |
| `Movie` | `pMed` | External movie reference |
| `AnyFile` | `pTxt` | Other external file reference |
| `PList` | `Plst` | Property-list reference |

The semantic fields within these blocks correspond to the text companion formats documented elsewhere in this directory. In particular:

- source entities and member groups follow [xojo-code-language.md](xojo-code-language.md);
- designer controls follow [xojo-window.md](xojo-window.md) and [xojo-code-ui.md](xojo-code-ui.md);
- menus, toolbars, file types, images, colors, reports, and databases follow their respective topic pages; and
- project hierarchy and IDs follow [xojo-project.md](xojo-project.md).

## Child elements and ordering

A block contains an ordered sequence of semantic elements. There is no generic `record` wrapper and no explicit scalar type attribute:

```xml
<ObjName>App</ObjName>
<ObjContainerID>0</ObjContainerID>
<IsClass>1</IsClass>
<Superclass>DesktopApplication</Superclass>
```

The element name and its parent context determine whether the content is an integer, floating-point number, string, rectangle, or nested group. Preserve element order even when two elements appear independent; it corresponds to record order in RbBF and to IDE serialization order.

Nested groups are represented by nested semantic elements:

```xml
<ViewBehavior>
  <ViewProperty>
    <ObjName>Title</ObjName>
    <PropertyGroup>Behavior</PropertyGroup>
    <ItemType>String</ItemType>
    <EditorType>MultiLineEditor</EditorType>
  </ViewProperty>
</ViewBehavior>
```

Repeated children represent repeated records. No count field is required unless the particular block grammar defines one.

An empty scalar and an empty group can have the same lexical shape:

```xml
<ShortVersion></ShortVersion>
<Icon>
</Icon>
```

Their element names and context distinguish them. Do not globally collapse empty elements or infer a group solely from the presence of child elements.

The RbBF four-character tag corresponding to each semantic element is listed in [xojo-binary-xml-mapping.md](xojo-binary-xml-mapping.md).

## Scalar values

Integers are decimal text and may be negative. Floating-point values are decimal text accepted by an IEEE-754 binary64 parser. Their lexical spelling is not canonical: `0`, `0.0`, and sufficiently precise longer spellings can represent the same numeric value.

Boolean storage depends on context. Ordinary RbBF integer-backed fields use `0` and `1`; `PropertyVal` values can use Xojo text spellings such as `True` and `False`. Do not apply a document-wide Boolean rewrite.

Ordinary strings are XML character data with normal XML escaping:

```xml
<PropertyVal Name="BackgroundColor">&amp;h00FFFFFF</PropertyVal>
```

Color-valued `PropertyVal` strings are not lexically canonical. IDE-written XML contains both `&amp;cRRGGBB[AA]` Xojo color literals and `&amp;h...` hexadecimal strings. Xojo Project commonly writes an `&c` literal for a value that binary/XML previously stored as `&h`, so the original lexical form cannot be recovered from that text alone. Current text imports ordinarily retain `&c`, but root properties on a custom class whose inheritance chain ends at `DesktopWindow` have also been observed canonicalized to `&h`. Semantic comparison must decode both forms and account for the byte order of the optional alpha component; byte comparison of the literal is insufficient.

Legacy properties whose Inspector type is `Color` differ from current `ColorGroup` properties. A binary `Color` `PDef` stores its RGB value as an `Int `, while `ColorGroup` normally uses a string literal. Examples of integer-backed legacy colors include `BackColor` on `DesktopTextField`, `DesktopTextArea`, `ReportField`, `ReportLabel`, and `ReportPicture`; `BorderColor` and `FillColor` on `ReportRectangleShape`; `LineColor` on `ReportLineShape`; `SVGColor` on `WebProgressWheel`; and the paired `BackColor`/`BackgroundColor` properties of a legacy `Window`. XML rendering can also depend on owner context: an `IOSLaunchScreen` `BackgroundColor` with the same `Color` metadata and integer value is written as `&amp;h00RRGGBB` when its superclass is `MobileScreen`, but as a decimal integer when its superclass is `iosView`. A converter must use the declared property type and owning class rather than choosing storage or XML spelling from the property name alone.

An empty string may be written with separate start/end tags or XML's self-closing spelling. Those forms are XML-equivalent, although Xojo commonly uses separate tags.

## Exact byte strings and `Hex`

Strings that contain tabs, line breaks, bytes that are not valid UTF-8, or characters forbidden by XML 1.0 are stored as a `Hex` child:

```xml
<ItemSource>
  <Hex bytes="11">537562204F70656E696E67</Hex>
</ItemSource>
```

`bytes` is the decimal decoded-byte count. The body is hexadecimal and must decode to exactly that many bytes. Hexadecimal letter case is not semantic, but preserving the original spelling avoids unnecessary diffs. A `Hex` child is scalar byte content, not a nested record group.

## Rectangles

Rectangle records use attributes rather than character data:

```xml
<EditBounds>
  <Rect left="20" top="40" width="900" height="700" />
</EditBounds>
```

All four attributes are signed decimal integers. `EditBounds` is the semantic wrapper used for the RbBF `rEdt` record. Other rectangle contexts can use a direct `Rect` element.

## Property values

Designer and Inspector property values use a compact form:

```xml
<PropertyVal Name="Title">Example</PropertyVal>
<PropertyVal Name="Visible">True</PropertyVal>
<PropertyVal Name="Top">0</PropertyVal>
```

`Name` is required. A `PropertyVal` corresponds to an RbBF `PDef` group but does not encode whether its `PVal` was an `Int `, `Dbl `, or `Strn`, and does not carry all of that group's metadata. RbBF can also store a property type, Inspector group, visibility, and other internal fields; those fields cannot be reconstructed from the compact XML element unless the object grammar independently supplies them.

Legacy SQLite properties named `Stage` and `AutoConnect` also use `PropertyVal` in XML even though their RbBF records have dedicated tags.

## IDs and hierarchy

`block/@ID` identifies the block. `ObjContainerID` places a project item under a folder, namespace module, or other Navigator parent. Zero denotes the root. Other ID-bearing fields create links among blocks, including default views, menu bars, build steps, controls, and editor state.

Treat every ID as opaque. Compare the low 32-bit pattern, preserve references when reordering blocks, and never renumber a block without updating every reference to it.

## Relationship to RbBF

XML represents the semantic block and record tree but omits RbBF allocation details:

- block allocation sizes and `*` padding;
- group IDs and group-length framing;
- the internal encrypted-password slot present in many project-item blocks; and
- empty obsolete `pItm` placeholder blocks.

The `PDef` to `PropertyVal` collapse is also non-bijective, as described above. Consequently, binary -> XML -> binary is not expected to reproduce the original binary bytes. Nevertheless, an RbBF writer must restore the mandatory `PDef` metadata and other required group records before producing a binary project; `name` plus `PVal` alone is structurally incomplete. Established view-property and framework schemas can provide an IDE-compatible reconstruction even though they cannot prove the exact omitted source bytes.

The following XML fields express defaults but have no established RbBF record:

| XML element | Default value |
| --- | --- |
| `MetaData` | empty string |
| `EditorType` inside `ViewProperty` | empty string |
| `Visible` inside `ViewProperty` | false |
| `PropertyGroup` inside `ViewProperty` | empty string |
| `PropertyValue` inside `ViewProperty` | empty string |

Their default values can disappear in XML -> binary -> XML without changing the represented setting. A nondefault value must not be discarded or guessed.

`ToolItemSymbol`, `ToolItemAllowMulticolorSymbol`, and `ToolbarStyle` map to the RbBF tags `tis `, `tims`, and `tbs `. They are ordinary mapped fields and must not be discarded, including when they hold their default values.

XML declaration quoting, indentation, empty-element spelling, and numeric spelling are lexical details and may change across a round trip. Semantic comparison must decode `Hex`, compare numeric values according to their field types, treat known default-only omissions explicitly, and preserve all other elements and attributes.

## Relationship to the multi-file text format

The XML file contains blocks that become separate manifest items and companion files in Xojo Project format. The text manifest remains authoritative when the text format is the input: only paths named by that manifest belong to the project. Conversely, XML has no companion-file discovery step because all serializable project blocks are already in the document.

`UIState` is IDE state rather than a manifest project item. The text format stores it in a conventionally named, dot-prefixed `.xojo_uistate` sidecar that is not listed in the manifest. For a manifest named `Example.xojo_project`, the sidecar is `.Example.xojo_uistate` in the same directory. A reader may derive and open that one known path without enumerating or treating arbitrary sibling files as project members. When producing text, encode the `UIState` records into that sidecar rather than omitting the block.

External assets remain references rather than embedded payloads. Their blocks store fields such as `FullPath`, `PartialPath`, `FileAlias`, and `SaveInfo`. Compiled icon data represented by `.xojo_resources` in the text format appears as nested `Icon`/`Element`/`ItemData` structures in XML.

## Whitespace and pretty printing

Indentation between child elements is formatting whitespace. Xojo can write a compactly indented form and a more deeply indented pretty-printed form; the project tree is unchanged. Whitespace inside a plain scalar element is data, however, so a formatter must distinguish element-only content from string content. `Hex` should be used for byte strings whose whitespace must be exact.

## Preservation rules

1. Preserve root attributes, block order, element order, unknown elements, and unknown attributes.
2. Preserve IDs as opaque 32-bit patterns and update all references together.
3. Do not treat every empty element as an empty string; known groups may be empty.
4. Validate `Hex/@bytes` against the decoded byte length.
5. Do not collapse an unknown element into `PropertyVal`. When generating RbBF, infer missing `PDef` metadata only from an established schema and reject a property whose mandatory binary shape cannot be reconstructed safely.
6. Treat an unrecognized block type or semantic element as format data that must be preserved, not ignored.
