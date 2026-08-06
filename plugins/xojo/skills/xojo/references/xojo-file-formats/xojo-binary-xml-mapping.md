# RbBF to Xojo XML name mapping

This appendix maps the four-character block and record tags in a Xojo Binary Project to the semantic names in a Xojo XML Project. It complements [xojo-binary-project.md](xojo-binary-project.md) and [xojo-xml-project.md](xojo-xml-project.md).

Spaces shown inside backticks are significant. For example, `Img `, `Lib `, and `ti  ` are four-byte tags with trailing spaces.

## Block tags

| RbBF | XML block `type` | RbBF | XML block `type` |
| --- | --- | --- | --- |
| `Aicn` | `ApplicationIcon` | `mobv` | `MobileScreen` |
| `BSbu` | `BuildProjectStep` | `pDC2` | `SQLiteLocalConnection` |
| `BScf` | `CopyFilesStep` | `pDTb` | `DesktopToolbar` |
| `BSsc` | `IDEScriptStep` | `pTbr` | `Toolbar` |
| `BSsn` | `SignProjectScriptStep` | `pDWn` | `DesktopWindow` |
| `BSts` | `BuildAutomation` | `pFTy` | `FileTypes` |
| `Bsls` | `BuildStepsList` | `pFol` | `Folder` |
| `IExs` | `ExternalScriptStep` |  |  |
| `Img ` | `MultiImage` | `pLay` | `IOSLayout` |
| `Limg` | `LaunchImages` | `pMed` | `Movie` |
| `NotC` | `NotificationCenter` | `pMnu` | `Menu` |
| `Plst` | `PList` | `pObj` | `Module` |
| `Proj` | `Project` | `pPic` | `Picture` |
| `WrKr` | `Worker` | `pRpt` | `Report` |
| `colr` | `ColorAsset` | `pScn` | `IOSScreen` |
| `ioLS` | `IOSLaunchScreen` | `pScp` | `Script` |
| `iosC` | `iOSContainer` | `pSnd` | `Sound` |
| `mobc` | `MobileContainer` | `pTxt` | `AnyFile` |
| `pUIs` | `UIState` | `xWSs` | `WebSession` |
| `pVew` | `Window` | `xWbC` | `WebContainer` |
| `xWbV` | `WebView` |  |  |

An empty obsolete `pItm` block has no XML block. Unknown nonempty block tags must not be treated as `pItm` or discarded.

## Record tags

| RbBF | XML element | RbBF | XML element |
| --- | --- | --- | --- |
| `AdMS` | `AndroidMinSdkVersion` | `VwBh` | `ViewBehavior` |
| `AdTS` | `AndroidTargetSdkVersion` | `VwPr` | `ViewProperty` |
| `Alas` | `AliasName` | `WHTM` | `WebHTMLHeader` |
| `Arch` | `CopyFileStepArch` | `WUI3` | `WinUIFramework` |
| `Atrb` | `Attributes` | `WbAn` | `WebHostingAppName` |
| `BCMO` | `BuildCarbonMachOName` | `WbDS` | `WebDisconnectString` |
| `BCXF` | `BuildCarbonExecutableFormat` | `WbHI` | `WebHostingIdentifier` |
| `BL86` | `BuildLinuxX86Name` | `WbHd` | `WebHostingDomain` |
| `BMDI` | `BuildWinMDI` | `WbLB` | `WebLaunchBrowser` |
| `BMob` | `BuildMobileName` | `WbLS` | `WebLaunchString` |
| `BWin` | `BuildWinName` | `WcmN` | `BuildWinCompanyName` |
| `Bflg` | `BuildFlags` | `Wdpt` | `WebDebugPort` |
| `BunI` | `BundleIdentifier` | `Web2` | `WebVersion` |
| `CBhv` | `ControlBehavior` | `WebV` | `UseWebView2` |
| `CBix` | `ControlIndex` | `WiFd` | `BuildWinFileDescription` |
| `CIns` | `ConstantInstance` | `WiNm` | `BuildWinInternalName` |
| `CLan` | `CurrentLanguage` | `WinV` | `WindowsVersions` |
| `CPrg` | `GetAccessor` | `WpNm` | `BuildWinProductName` |
| `CPrs` | `SetAccessor` | `Wpcl` | `WebProtocol` |
| `Ci1a` | `HLCItem1Attr` | `Wprt` | `WebPort` |
| `Ci2a` | `HLCItem2Attr` | `WptS` | `WebSecurePort` |
| `CnLk` | `HLCEditable` | `WrnP` | `WarningPreferences` |
| `CnMP` | `HLCScale` | `XMth` | `ExternalMethod` |
| `CnPr` | `HLCPriority` | `aivi` | `AutoIncVersion` |
| `CnPv` | `HLCValue` | `alis` | `FileAlias` |
| `CnRo` | `HLCRelOp` | `bApO` | `IsApplicationObject` |
| `Cni1` | `HLCItem1` | `bCls` | `IsClass` |
| `Cni2` | `HLCItem2` | `bFAS` | `BuildForAppStore` |
| `Cnst` | `Constant` | `bNtr` | `IsInterface` |
| `Comp` | `Compatibility` | `bhlp` | `ItemHelp` |
| `Cont` | `ObjContainerID` | `binE` | `BinaryEnum` |
| `Ctrl` | `Control` | `brkG` | `BreakPointGroup` |
| `DEnc` | `DefaultEncoding` | `cRDW` | `CopyWindowsRedist` |
| `DLan` | `DefaultLanguage` | `ccls` | `ControlClass` |
| `DVew` | `DefaultViewID` | `clr1` | `ColorLight` |
| `DeID` | `DeveloperID` | `clr2` | `ColorDark` |
| `Dest` | `Subdirectory` | `clrR` | `ColorRepresentation` |
| `DgCL` | `DebuggerCommandLine` | `clrp` | `ColorPlatform` |
| `Dmth` | `DelegateDeclaration` | `clrt` | `ColorType` |
| `Dseg` | `DesktopSegmentedButton` | `cnfT` | `ConformsTo` |
| `DstR` | `Destination` | `comM` | `Comment` |
| `Edpt` | `EditingPartID` | `conn` | `ConnectionSet` |
| `EnVv` | `EnvVars` | `data` | `ItemData` |
| `Enco` | `TextEncoding` | `deVi` | `Device` |
| `Enum` | `Enumeration` | `decl` | `ItemDeclaration` |
| `FTRk` | `FileRank` | `defn` | `ItemDef` |
| `FTpt` | `FilePhysicalType` | `devT` | `DeviceType` |
| `GDIp` | `UseGDIPlus` | `dkmd` | `DarkMode` |
| `HCla` | `HCLActive` | `dscR` | `Description` |
| `HCnm` | `HLCName` | `elem` | `Element` |
| `HIns` | `HookInstance` | `enbl` | `Enabled` |
| `HLCn` | `HighLevelConstraint` | `enky` | `EncryptionKey` |
| `Hook` | `Hook` | `fTyp` | `FileType` |
| `IDEv` | `IDEVersion` | `flag` | `ItemFlags` |
| `IOSV` | `iOSMinimumVersion` | `hidp` | `HiDPI` |
| `IPDB` | `IncludePDB` | `iArc` | `IOSArchitecture` |
| `IVer` | `InfoVersion` | `iDDv` | `IOSDebugDevice` |
| `Icon` | `Icon` | `iLck` | `Locked` |
| `ImgR` | `ImageRepresentation` | `iOri` | `IOSLayoutEditorViewOrientation` |
| `ImgS` | `ImageSpecification` | `iOsC` | `IOSCapabilities` |
| `Intr` | `Interfaces` | `iSCI` | `ScreenContentItem` |
| `LVer` | `LongVersion` | `iVTy` | `IOSLayoutEditorViewType` |
| `Lib ` | `LibraryName` | `imPo` | `Imported` |
| `MASc` | `MASCategory` | `indx` | `ItemIndex` |
| `MBPS` | `BuildForPlayStore` | `ioPP` | `ProvisioningProfileName` |
| `MDIc` | `WinMDICaption` | `iopm` | `iOSPrivacyManifest` |
| `MItm` | `MenuItem` | `isBn` | `BuildiOSName` |
| `MKSF` | `KeyStoreFile` | `itHd` | `HeightDouble` |
| `MUIC` | `MacUICompatibilityMode` | `iUIC` | `iOSUICompatibilityMode` |
| `MacC` | `MacCreator` | `itHt` | `Height` |
| `MacV` | `MacMinimumVersion` | `itWd` | `Width` |
| `MaxW` | `WindowMaximized` | `itwD` | `WidthDouble` |
| `McTl` | `macOSEntitlements` | `kCod` | `CodeDescription` |
| `Meth` | `Method` | `kUTI` | `UTIType` |
| `MiAK` | `PCAltModifier` | `Mopt` | `MacOptionModifier` |
| `MiAM` | `AlternateShortcutModifier` | `lang` | `ItemLanguage` |
| `MiMk` | `MenuShortcutModifier` | `ldex` | `LoadExtensions` |
| `MiSK` | `MenuShortcut` | `linA` | `LinuxArchitecture` |
| `MnuH` | `MenuHandler` | `lnNM` | `lineNum` |
| `MoMG` | `MobileManifestGlobals` | `lncs` | `NormalizeControlSizes` |
| `MoMM` | `MobileManifestMetadata` | `mDvT` | `MobileDeviceType` |
| `MoMP` | `MobileManifestPermissions` | `mVis` | `MenuItemVisible` |
| `MoMk` | `MobileGoogleMapsAPIKey` | `maEn` | `MenuAutoEnable` |
| `MoPD` | `MobileProjectDependencies` | `macA` | `MacArchitecture` |
| `MoTA` | `MobileThemeAccentColor` | `mimT` | `MimeType` |
| `MoTC` | `MobileThemeColorName` | `name` | `ItemName` |
| `MoTP` | `MobileThemePrimaryColor` | `ntln` | `NoteLine` |
| `MoTS` | `MobileThemeStatusBarColor` | `oPtL` | `OptimizationLevel` |
| `NWUI` | `NativeWinUISizes` | `objC` | `ObjectiveC` |
| `Name` | `ObjName` | `orie` | `Orientation` |
| `NnRl` | `NonRelease` | `parm` | `ItemParams` |
| `Note` | `Note` | `path` | `FullPath` |
| `PSIV` | `ProjectSavedInVers` | `plFM` | `Platform` |
| `PVal` | `PropertyValue` | `plis` | `PlistEntries` |
| `PrGp` | `PropertyGroup` | `pltf` | `ItemPlatform` |
| `Prop` | `Property` | `ppth` | `PartialPath` |
| `PtID` | `PartID` | `prTp` | `ProjectType` |
| `Regn` | `Region` | `prWA` | `WebApp` |
| `Rels` | `Release` | `rEdt` | `EditBounds` |
| `Rpsc` | `ReportSection` | `resZ` | `Resolution` |
| `SCtx` | `ScriptText` | `segB` | `SegmentedButton` |
| `segC` | `SegmentedControl` | `tbs ` | `ToolbarStyle` |
| `SEId` | `EditorIndex` | `rslt` | `ItemResult` |
| `SELn` | `EditorLocation` | `runA` | `WindowsRunAs` |
| `SEPt` | `EditorPath` | `sPWD` | `AppSpecificPassword` |
| `SEdC` | `EditorCount` | `scut` | `ItemShortcut` |
| `SEdr` | `Editor` | `shrd` | `IsShared` |
| `SEds` | `Editors` | `sorc` | `ItemSource` |
| `SVer` | `ShortVersion` | `spmu` | `ItemSpecialMenu` |
| `Soft` | `SoftLink` | `srcl` | `SourceLine` |
| `StST` | `SelectedTab` | `styl` | `ItemStyle` |
| `StpA` | `StepAppliesTo` | `svin` | `SaveInfo` |
| `Strx` | `Structure` | `text` | `ItemText` |
| `Supr` | `Superclass` | `ti  ` | `ToolItem` |
| `USng` | `Using` | `tims` | `ToolItemAllowMulticolorSymbol` |
| `tis ` | `ToolItemSymbol` |  |  |
| `SwSt` | `StudioWindowState` | `tout` | `Timeout` |
| `SySF` | `SystemFlags` | `tran` | `ItemTransparent` |
| `TVew` | `DefaultTabletViewID` | `tyin` | `ThreadYieldInterval` |
| `Targ` | `Target` | `type` | `ItemType` |
| `UsBF` | `UseBuildsFolder` | `unID` | `UnitID` |
| `Usin` | `GlobalUsingClauses` | `unTY` | `UnitType` |
| `Ver1` | `MajorVersion` | `vbET` | `EditorType` |
| `Ver2` | `MinorVersion` | `wahl` | `WriteAheadLogging` |
| `Ver3` | `SubVersion` | `winA` | `WindowsArchitecture` |
| `Vsbl` | `Visible` |  |  |
| `bkGP` | `BookmarkGroup` |  |  |

## Contextual and non-bijective records

The following records do not have a simple one-record/one-element mapping:

| RbBF record | XML representation |
| --- | --- |
| `PDef` | `<PropertyVal Name="...">value</PropertyVal>`; internal property metadata is omitted |
| `rEdt` (`Rect`) | `<EditBounds><Rect left="..." top="..." width="..." height="..." /></EditBounds>` |
| `Stag` | `<PropertyVal Name="Stage">...</PropertyVal>` in a legacy SQLite connection |
| `auto` | `<PropertyVal Name="AutoConnect">True|False</PropertyVal>` in a legacy SQLite connection |
| `pasw` | Omitted internal encrypted-password slot |
| `PrGp`, `type`, `visi` inside `PDef` | Omitted with the other internal property metadata |

`Icon` can be an integer selector or a group depending on its parent. `Rpsc`, `data`, `name`, and `type` also occur with more than one RbBF value type. The binary value-type field and XML parent context are authoritative; the tag name alone is insufficient for those records.

Observed `pasw` records are empty. The established XML conversion omits only that empty form and restores an empty slot when reconstructing a project-item block. A nonempty `pasw` is safely framed but has no established XML representation; strict conversion must reject it, while an explicitly lossy conversion may omit it only after reporting the exact record.

## Group-valued records

These tags are established as groups in their ordinary contexts:

```text
CBhv CIns CPrg CPrs Cnst Ctrl Dmth Dseg Enum HIns HLCn Hook ImgR ImgS
MItm Meth MnuH Note PDef Prop SEdr SEds Strx SwSt USng VwBh VwPr WrnP XMth
bkGP brkG clrR conn elem fTyp iSCI segB segC sorc "ti  "
```

An element with children is also group-valued unless its sole child is `Hex`, which represents scalar bytes. Empty known groups remain groups even without child elements.

## Scalar value types

XML does not carry a generic scalar-type attribute, so the semantic tag and parent context determine the RbBF value type.

`itHd` (`HeightDouble`) and `itwD` (`WidthDouble`) use `Dbl `. The `rEdt` special case uses `Rect`. The following tags use `Strn` in their ordinary scalar contexts:

```text
AdMS AdTS Alas Atrb BCMO BL86 BMob BWin BunI CnPv Cni1 Cni2 Comp DeID
Dest DgCL EnVv FTpt HCnm IOSV IVer Intr LVer "Lib " MASc MDIc MKSF MacC
MacV McTl MiSK MoMG MoMM MoMP MoMk MoPD MoTA MoTC MoTP MoTS Name NnRl
PSIV PrGp Regn Rels SCtx SELn SEPt SVer Supr Ver1 Ver2 Ver3 WHTM WbAn WbDS
WbHI WbHd WbLS WcmN WiFd WiNm WinV WpNm alis bhlp ccls clr1 clr2 cnfT comM decl
defn dscR enky iDDv iOsC ioPP iopm isBn kCod kUTI mimT ntln parm path
plis ppth rslt sPWD scut srcl svin text "tis " unID unTY vbET
```

Mapped scalar tags not listed as `Dbl `, `Rect`, `Strn`, or contextual below use `Int `.

The contextual scalar rules are:

- `Icon` is a group under Project and FileType records; a scalar `Icon` is `Int `.
- `data` and `name` are `Int ` inside `WarningPreferences` and `Strn` elsewhere.
- `type` is `Int ` when its content is a valid decimal integer and `Strn` otherwise.
- a scalar `Rpsc` (`ReportSection`) is `Strn`; a nested one is a group.
- `PVal` occurs as `Int `, `Dbl `, and `Strn`. The compact XML `PropertyVal` representation does not encode that type explicitly, and the exact original type is not always recoverable from the property name and lexical value.

If a field contradicts its established scalar type, preserve the original typed RbBF record rather than coercing it solely from its XML-looking text.
