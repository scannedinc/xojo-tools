# RbBF four-character tag reference

Every record and block inside an `RbBF` container is identified by a four-character tag. This is a reference list of tags found in REALbasic, Real Studio and Xojo binary projects, with the name each denotes and the XML element it corresponds to where one exists.

This list and [xojo-binary-xml-mapping.md](xojo-binary-xml-mapping.md) answer different questions and neither supersedes the other. The mapping appendix is the complete tag-to-XML correspondence and covers only tags that have an XML counterpart. This list is narrower in that respect but wider in another: it also names tags that carry IDE editor state or obsolete build settings and therefore have no XML element at all, and it separates a tag's own name from the XML element it maps to, which are not always spelled the same. Where both name a tag's XML element they agree.

Tags are exactly four bytes and are space-padded when the name is shorter, so `Int ` and `Lib ` carry a trailing space. Matching is case-sensitive.

## Reading the table

The **XML element** column gives the element name used for that tag in Xojo XML Project.

- A dash means no XML element corresponds to the tag. Some of these are structural (`Blok`, `Grup`, `Padn`) and belong to the container rather than the project model; others carry IDE editor state that the XML format does not represent.
- *Not emitted* marks tags that a modern IDE discards when it upgrades an older project. They appear in files written by REALbasic and early Real Studio and have no modern equivalent. Chief among these are the Carbon-era build settings — `ACnm`, `ACsv`, `BCar`, `BSiz`, `BMSz`, `BSzS` and `BMSS` — which described a build target that no longer exists.

Several tags name IDE window state rather than project content: `WnSt` holds a group whose children include `OTab` (open tab), `LsLc` (last location), `eSpt` and `LSpt` (editor split positions), `AltE` (alternate editor), and `lstH` / `lstV` (last scroll position). These live in a `pUIs` block and describe how the project was last displayed, not what it contains.

## Caveats

A name in this list describes what a tag is understood to mean, not what any particular file guarantees. Tags are reused and repurposed across format generations, so a tag may carry a different payload in an old file than in a new one.

Two names in this list collide: `BCar` and `BCMO` both describe a Carbon build name. They are distinct tags and a reader should preserve that distinction rather than treating them as synonyms.

Where a tag appears here but has no XML element, the absence should not be read as a guarantee that no element exists — only that none is known.

The set of tags is open. Newer writers emit records that older ones do not, and a reader that treats an unrecognized tag as a fatal error will reject files that are otherwise well formed.

Four records are named but carry no independently established payload semantics: `Meta` (`MetaData`), an empty byte string inside a database-connection block, and `tbs ` (`ToolbarStyle`), `tims` (`ToolItemAllowMulticolorSymbol`) and `tis ` (`ToolItemSymbol`) inside a desktop toolbar block, the first two integers and the third an empty byte string. Their names come from the XML elements they correspond to; their payloads occur only at empty or zero values, so nothing further about them can be inferred from the payload alone. Note that two of these tags are four characters wide only because of a trailing space, which is significant.

| Tag | Name | XML element |
|---|---|---|
| `ACnm` | ProjMgrUser | — |
| `ACsv` | ProjMgrServer | — |
| `Alas` | AliasName | `AliasName` |
| `AltE` | AlternateEditorID | — |
| `BCMO` | BuildCarbonMachOName | `BuildCarbonMachOName` |
| `BCXF` | BuildCarbonExecutableFormat | `BuildCarbonExecutableFormat` |
| `BCar` | BuildCarbonName | — |
| `BL86` | BuildLinuxX86Name | `BuildLinuxX86Name` |
| `BMDI` | BuildWinMDI | `BuildWinMDI` |
| `BMSS` | BuildMinSizeAsString | — |
| `BMSz` | BuildMinSize | — |
| `BMac` | BuildMacName | — |
| `BSiz` | BuildSize | — |
| `BSzS` | BuildSizeAsString | — |
| `BWin` | BuildWinName | `BuildWinName` |
| `BbDd` | BindDestBindData | — |
| `BbSd` | BindSourceBindData | — |
| `Bflg` | BuildFlags | `BuildFlags` |
| `Bind` | Binding | — |
| `Blok` | block | — |
| `BnDd` | BindDestData | — |
| `BnDs` | BindDest | — |
| `BnSd` | BindSourceData | — |
| `BnSr` | BindSource | — |
| `BunI` | BundleIdentifier | `BundleIdentifier` |
| `CBhv` | ControlBehavior | `ControlBehavior` |
| `CBix` | ControlIndex | `ControlIndex` |
| `CIns` | ConstantInstance | `ConstantInstance` |
| `CLan` | CurrentLanguage | `CurrentLanguage` |
| `CPal` | ColorPalette | — |
| `CPif` | InheritsFrom | `InheritedFrom` |
| `CPrg` | GetAccessor | `GetAccessor` |
| `CPrs` | SetAccessor | `SetAccessor` |
| `Cnst` | Constant | `Constant` |
| `Comp` | Compatibility | `Compatibility` |
| `Cont` | ObjContainerID | `ObjContainerID` |
| `Ctrl` | Control | `Control` |
| `DEnc` | DefaultEncoding | `DefaultEncoding` |
| `DLan` | DefaultLanguage | `DefaultLanguage` |
| `DVew` | DefaultViewID | `DefaultViewID` |
| `Enco` | TextEncoding | `TextEncoding` |
| `Enum` | Enumeration | `Enumeration` |
| `FDef` | FormDefn | — |
| `HIns` | HookInstance | `HookInstance` |
| `Hook` | Hook | `Hook` |
| `IVer` | InfoVersion | `InfoVersion` |
| `Icon` | Icon | `Icon` |
| `Intr` | Interfaces | `Interfaces` |
| `LSpt` | EditSplit | — |
| `LVer` | LongVersion | `LongVersion` |
| `LsLc` | LastLocation | — |
| `MDIc` | WinMDICaption | `WinMDICaption` |
| `MItm` | MenuItem | `MenuItem` |
| `MacC` | MacCreator | `MacCreator` |
| `Meta` | MetaData | `MetaData` |
| `Meth` | Method | `Method` |
| `MiAK` | PCAltModifier | `PCAltModifier` |
| `MiAM` | AlternateShortcutModifier | `AlternateShortcutModifier` |
| `MiKK` | MacControlModifier | `MacControlModifier` |
| `MiMk` | MenuShortcutModifier | `MenuShortcutModifier` |
| `MiSK` | MenuShortcut | `MenuShortcut` |
| `MnuH` | MenuHandler | `MenuHandler` |
| `Mopt` | MacOptionModifier | `MacOptionModifier` |
| `Name` | ObjName | `ObjName` |
| `NnRl` | NonRelease | `NonRelease` |
| `Note` | Note | `Note` |
| `OTab` | OpenTab | — |
| `PDef` | PropertyVal | — |
| `PSIV` | ProjectSavedInVers | `ProjectSavedInVers` |
| `PVal` | PropertyValue | `PropertyValue` |
| `PrGp` | PropertyGroup | `PropertyGroup` |
| `Proj` | Project | `Project` |
| `Prop` | Property | `Property` |
| `RbBF` | RBProject | — |
| `Regn` | Region | `Region` |
| `Rels` | Release | `Release` |
| `SVer` | ShortVersion | `ShortVersion` |
| `Size` | ObjSize | — |
| `Strx` | Structure | `Structure` |
| `Supr` | Superclass | `Superclass` |
| `SySF` | SystemFlags | `SystemFlags` |
| `Ver1` | MajorVersion | `MajorVersion` |
| `Ver2` | MinorVersion | `MinorVersion` |
| `Ver3` | SubVersion | `SubVersion` |
| `Vsbl` | Visible | `Visible` |
| `VwBh` | ViewBehavior | `ViewBehavior` |
| `VwPr` | ViewProperty | `ViewProperty` |
| `WcmN` | WcmN | `BuildWinCompanyName` |
| `WiNm` | WiNm | `BuildWinInternalName` |
| `WnSt` | WindowState | — |
| `WpNm` | WpNm | `BuildWinProductName` |
| `aivi` | AutoIncVersion | `AutoIncVersion` |
| `alis` | FileAlias | `FileAlias` |
| `bApO` | IsApplicationObject | `IsApplicationObject` |
| `bCls` | IsClass | `IsClass` |
| `bNtr` | IsInterface | `IsInterface` |
| `bPEl` | BrowserPositionElement | — |
| `bPGp` | BrowserPositionGroup | — |
| `bhlp` | ItemHelp | `ItemHelp` |
| `ccls` | ControlClass | `ControlClass` |
| `ciID` | ciID | — |
| `data` | ItemData | `ItemData` |
| `decl` | ItemDeclaration | `ItemDeclaration` |
| `defn` | ItemDef | `ItemDef` |
| `desc` | ItemDescription | — |
| `dhlp` | ItemDisabledHelp | — |
| `eSpt` | EditSplit | — |
| `elem` | Element | `Element` |
| `fTyp` | FileType | `FileType` |
| `flag` | ItemFlags | `ItemFlags` |
| `indx` | ItemIndex | `ItemIndex` |
| `lang` | ItemLanguage | `ItemLanguage` |
| `lstH` | LastPositionH | — |
| `lstV` | LastPositionV | — |
| `maEn` | MenuAutoEnable | `MenuAutoEnable` |
| `mask` | Mask | — |
| `modd` | LatestChange | — |
| `name` | ItemName | `ItemName` |
| `ndsc` | EndSelCol | — |
| `ndsr` | EndSelRow | — |
| `ntln` | NoteLine | `NoteLine` |
| `pCur` | Cursor | — |
| `pDBs` | Database | — |
| `pEEx` | ExtEncCode | — |
| `pExt` | ExternalCode | `ExternalCode` |
| `pFTy` | FileTypes | `FileTypes` |
| `pFol` | Folder | `Folder` |
| `pMed` | Movie | `Movie` |
| `pMnu` | Menu | `Menu` |
| `pObj` | Module | `Module` |
| `pPic` | Picture | `Picture` |
| `pRes` | Resources | — |
| `pScp` | Script | `Script` |
| `pTxt` | AnyFile | `AnyFile` |
| `pUIs` | UIState | `UIState` |
| `pVew` | Window | `Window` |
| `parm` | ItemParams | `ItemParams` |
| `path` | FullPath | `FullPath` |
| `pltf` | ItemPlatform | `ItemPlatform` |
| `ppth` | PartialPath | `PartialPath` |
| `prTp` | ProjectType | `ProjectType` |
| `rEdt` | EditBounds | `EditBounds` |
| `rslt` | ItemResult | `ItemResult` |
| `scKy` | ScreenKey | — |
| `scut` | ItemShortcut | `ItemShortcut` |
| `shrd` | IsShared | `IsShared` |
| `sorc` | ItemSource | `ItemSource` |
| `spmu` | ItemSpecialMenu | `ItemSpecialMenu` |
| `srbp` | SourceLineBreakpoint | — |
| `srcl` | SourceLine | `SourceLine` |
| `stsc` | StartSelCol | — |
| `stsr` | StartSelRow | — |
| `styl` | ItemStyle | `ItemStyle` |
| `tbs ` | ToolbarStyle | `ToolbarStyle` |
| `text` | ItemText | `ItemText` |
| `tims` | ToolItemAllowMulticolorSymbol | `ToolItemAllowMulticolorSymbol` |
| `tis ` | ToolItemSymbol | `ToolItemSymbol` |
| `tran` | ItemTransparent | `ItemTransparent` |
| `type` | ItemType | `ItemType` |
| `vbET` | EditorType | `EditorType` |
