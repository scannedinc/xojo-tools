---
name: xojo
description: >-
  Look up the Xojo language and framework in a local copy of the official
  documentation. Use whenever writing, reviewing, explaining or debugging Xojo
  code, and before using any Xojo class, property, method, event or constant,
  to confirm it exists, get its exact signature, and check whether it is
  deprecated. Also use for questions about what a Xojo API does, what replaced
  a removed one, which controls exist for Desktop, Web, Mobile or Console, or
  how a Xojo feature works. This is also the skill for questions about API 1.0
  (which Xojo's own documentation calls "pre-API 2.0") versus API 2.0: how the
  two differ, whether a symbol is deprecated, which release deprecated it, and
  what replaced it. The indexes record all of that
  per member, and the documentation includes Xojo's own articles on moving to
  API 2.0. Answer such questions here; the xojo-migrate skill converts a
  project and the user runs it themselves. Also use when reading or editing
  Xojo project files (.xojo_project, .xojo_code, .xojo_window), when starting a
  new project, and for Xojo code style: naming case, Var vs Dim, pragmas. Xojo
  is obscure enough that most examples online use the removed API 1.0 rather
  than current API 2.0, so do not answer Xojo questions from memory: look them
  up here. Covers more than two thousand pages and fifteen thousand members,
  with a replacement recorded for thousands of deprecated ones.
disable-model-invocation: false
---

# Xojo documentation

This skill is a local copy of <https://documentation.xojo.com>, converted to Markdown, with tab-separated indexes. It also contains the rules to write Xojo code and to edit Xojo project files.

**Every path below is relative to this skill's folder—the folder that holds this SKILL.md—not to the project you work in.** Run the commands from that folder, or prefix each path with its location.

**Look facts up. Do not recall them.** Most Xojo code in training data predates API 2.0, so a recalled answer is often the removed API 1.0 form. `MsgBox`, `Dim`, `RecordSet`, `ListBox`, `Ubound`, and hundreds more are deprecated. The indexes below give the replacement for each one.

## First use and refresh

The documentation is generated, not committed, so a fresh install has no `references/documentation/` folder. Before the first lookup, and about once a week after that, run this from the skill root:

```sh
find assets/documentation.xojo.com/sync-state.json -mtime -7 2>/dev/null | grep -q . \
  || (python3 scripts/docs.py sync && python3 scripts/docs.py build)
```

The `find` test passes when the last successful sync is less than a week old, and then nothing runs. Otherwise `sync` downloads the documentation archive, or answers with a cheap no-op when the archive has not changed, and `build` converts the mirror. If the network is unavailable and `references/documentation/` exists, continue with the local copy and tell the user it may be stale.

## Start here

The skill has two tab-separated files. Each file has one row per item. Grep the files.

| File | One row per | Columns |
| --- | --- | --- |
| `references/documentation/classes.tsv` | page | `name  kind  flags  deprecated_in  replacement  note  members  path  summary` |
| `references/documentation/members.tsv` | property, method, event, constant | `name  kind  signature  flags  deprecated_in  replacement  note  path` |

On a class row, `kind` is what the page declares, for example `Class`, `Method`, `Keyword`, `DataType`, `Interface`, `Module`, `Operator`, or `Constant`. `kind` is empty for guides and index pages.

## Recipes

Everything a class offers:

```
grep -i '^DesktopTextField\.' references/documentation/members.tsv
```

Only the events of a class, or only the methods:

```
awk -F'\t' '$1 ~ /^DesktopTextField\./ && $2=="event"' references/documentation/members.tsv
```

Is this API current, and if not, what replaced it? Grep both files. A whole deprecated class is a page, and each individually deprecated member is also a page:

```
grep -ih 'ListBox.ActiveCell' references/documentation/*.tsv
```

Which classes have a given member (`awk`, because the stock macOS `grep` has no `-P`):

```
awk -F'\t' 'tolower($1) ~ /^[a-z0-9_]+\.rowcount$/' references/documentation/members.tsv
```

Find a class when you do not know the exact name:

```
grep -i 'listbox' references/documentation/classes.tsv | cut -f1,2,3,5
```

Everything deprecated in one release:

```
awk -F'\t' '$5=="2021r3"' references/documentation/members.tsv
```

## Reading a page

The `path` column points at the file. Each class has two files:

- `<class>.md` — the description, and summary tables of every property, method, and event. Read this file to learn what a class offers.
- `<class>.members.md` — the full description of each member, with sample code. Read this file for one specific member. This file is much larger.

Open the small file first. The members file is several times as large.

Member anchors match the `path` fragment, so `api/…/desktoptextfield.members.md#desktoptextfield.active` lands on that member.

## Citing the public page

`references/documentation/` mirrors the layout of the site, so the `path` column *is* the URL path. To turn a path into a link that a person can open:

1. Remove `.md` or `.members.md`, then append `.html`. Both local files come from one public page. There is no `.members.html`.
2. Percent-encode the path. Only `'` `(` `)` `+` `^` need encoding, on a handful of pages. Every other path is already URL-safe.
3. To rewrite an anchor, lowercase it, then change each run of non-alphanumeric characters into one `-`. **The local `.` becomes a `-`.**

```
api/user_interface/desktop/desktoptextfield.md
  → https://documentation.xojo.com/api/user_interface/desktop/desktoptextfield.html

api/user_interface/desktop/desktoptextfield.members.md#desktoptextfield.active
  → https://documentation.xojo.com/api/user_interface/desktop/desktoptextfield.html#desktoptextfield-active

api/language/operators/mathematical/+.md
  → https://documentation.xojo.com/api/language/operators/mathematical/%2B.html
```

Encodings: `'` `%27`, `(` `%28`, `)` `%29`, `+` `%2B`, `^` `%5E`.

**Apply the rule. Do not look the URL up in `assets/…/requests.tsv`.** That file records the URL in percent-encoded form, but the local filename is decoded. So a grep for the local path misses every page that needs encoding, and those are the only pages worth a lookup. The grep returns nothing, not an error. The file also carries no anchors.

If you want the authoritative answer instead of the rule, use `objects.inv`. That file records the exact URI that Sphinx generated for every page. The file is zlib-compressed, so read it with:

```
python3 -c "
import zlib,sys
d=open(sys.argv[1],'rb').read()
rows=zlib.decompress(d.split(b'zlib.\n',1)[1]).decode().splitlines()
q=sys.argv[2].removesuffix('.members.md').removesuffix('.md')
for r in rows:
    p=r.split(' ',4)
    if p[0]==q and p[1]=='std:doc': print('https://documentation.xojo.com/'+p[3])
" assets/documentation.xojo.com/objects.inv \
  'api/language/operators/mathematical/+'
```

## Deprecation

`flags` contains `deprecated` for each item removed from API 2.0. When `flags` contains `deprecated`, `deprecated_in` gives the release, and `replacement` gives the current API:

```
ListBox.ListCount       →  DesktopListBox.RowCount        (2019r2)
DesktopListBox.AddRows  →  DesktopListBox.AddAllRows      (2023r3)
MsgBox                  →  MessageBox or MessageDialog    (2019r2)
RecordSet               →  RowSet                         (2019r2)
```

A few hundred deprecated members have no recorded replacement. Either the docs state that there is no replacement, or the deprecation notice does not name one. In that case, read the page of the member. The prose usually explains the alternative.

A few rows are maintained by hand in `scripts/deprecation-overrides.tsv`, because the documentation cannot state them deterministically:

- replacements the docs get wrong: the `Window` function's page suggests `Application.Window`, which is itself deprecated
- calls the current docs no longer describe, like the removed `FolderItem.CreateBinaryFile` family
- the hazard notes in the `note` column: the INDEX BASE, EPOCH, and ERROR MODEL warnings
- advice on a symbol that is not deprecated at all: `Redim` still compiles and carries no `deprecated` flag, but its row points at `ResizeTo`, which the docs prefer

`build` merges them into both indexes, so the same greps find them. (`Val`, `Str`, `Format`, `Hex`, `CStr`, `Asc`, and `Chr` are **not** deprecated, even though most of them have API 2.0 siblings; only the byte variants `AscB` and `ChrB` are.)

## Renaming is not enough: some indexes changed

**This is the most dangerous part of the move from API 1.0 to API 2.0.** Several replacements changed their counting base, their not-found value, their epoch, or their failure behavior at the same time as the rename. If you substitute the new name and keep the old logic, the code compiles cleanly but produces silent bugs.

| API 1.0 | API 2.0 | What changed |
| --- | --- | --- |
| `Mid(s, start, len)` | `s.Middle(start, len)` | The first character is **1** in `Mid` and **0** in `Middle`. Subtract 1 from `start`. `Mid` also clamped a start below 1, so `Mid(s, 0)` was legal and its direct conversion is not: audit loops that start at 0. |
| `InStr(s, find)` | `s.IndexOf(find)` | `InStr` returns a **one-based** position and **0** when not found. `IndexOf` returns a **zero-based** position and **-1** when not found. Change the `> 0` test to `>= 0`. Adjust the returned value everywhere the code uses it as a position. |
| `MidB`, `InStrB` | `MiddleBytes`, `IndexOfBytes` | Same shifts as above. |
| `Date.TotalSeconds` | `DateTime.SecondsFrom1970` | The epoch moves from **1904** to **1970**. A stored `TotalSeconds` value read as `SecondsFrom1970` is 66 years wrong, so rebase every stored value. |
| `f.CreateBinaryFile(type)` | `BinaryStream.Create(f)` | Failure returned **`Nil`** before and raises an **`IOException`** now. The `<> Nil` guard becomes dead code, and the exception has no handler. The other file open and create calls changed the same way. |

The docs confirm these changes: the `Mid` page says "the first character is numbered 1", `String.Middle` says "numbered 0", `Date.TotalSeconds` counts from 1904 while `DateTime.SecondsFrom1970` counts from 1970, and the `BinaryStream.Create` page says an `IOException` will be raised.

The `note` column spells out these hazards for every item that carries one:

```
grep -h 'INDEX BASE\|EPOCH\|ERROR MODEL' references/documentation/*.tsv
awk -F'\t' '$6!=""' references/documentation/classes.tsv     # every class note
awk -F'\t' '$7!=""' references/documentation/members.tsv     # every member note
```

**Before you apply a replacement, open the page of the new API. Compare the parameter meanings to the old API.** A replacement name is often not a straight rename. `ListBox.Cell` became `DesktopListBox.CellTextAt`, and several `CellBorder*` properties collapsed into one `PaintCellBackground` event.

## Projects and file formats

Xojo has three project formats: Xojo Project, Xojo Binary Project, and Xojo XML Project. Only the Xojo Project format works well with source control and with an agent, because it is text. This skill supports only that format: the `.xojo_project` manifest plus companion files with extensions such as `.xojo_code`, `.xojo_window`, and `.xojo_menu`. This skill does not support the Xojo Binary Project format (`.xojo_binary_project`) or the Xojo XML Project format (`.xojo_xml_project`); ask the user to save a copy in Xojo Project format instead.

**Before you read or edit any `.xojo_*` file, read the format reference for that file.** `references/xojo-file-formats/index.md` names the right document for each extension and states the safety rules for generators and editors. Start with `shared-text-grammar.md` for the `#tag` and `Begin`/`End` syntax that most formats share. The official overview is `references/documentation/getting_started/using_the_ide/project_file_information.md`.

Xojo has five project types: Desktop, Console, Web, iOS, and Android. Assume a desktop project unless the user or the project indicates a different type. Blank starter projects of all five types are in `references/projects/`.

## Writing code

These defaults hold unless the user instructs otherwise:

- **Use API 2.0.** API 2.0 is the current standard, so do not call it by name. Say "API 2.0" explicitly only when you discuss legacy code. Read `references/documentation/topics/api_design/moving_to_api_2.0.md` for what changed. If you see API 1.0 code in a project, warn the user to migrate the code to API 2.0, and tell them to run the migration skill themselves when they want that done (`/xojo:xojo-migrate` in Claude Code, `$xojo-migrate` in Codex): it only starts when they ask for it.
- **Name the old API "API 1.0".** That is this plugin's term, and it is the one to write. Xojo's own documentation rarely names that generation, and calls it "pre-API 2.0" when it does; use Xojo's term when you quote them or when a reader needs to find the same thing in their docs. The two mean one generation, so treat them as the same term when you search. Never call it "legacy": that word carries a judgment this plugin does not make.
- **In Web projects, use only Web 2.0 features.**
- **Use `Var`, not `Dim`.**
- **Follow the naming guidelines.** Read and follow `references/documentation/topics/api_design/api_design_and_naming_guidelines.md`. Class names and class members are PascalCase (upper camel case). Parameter names are camelCase (lower camel case), as in `safeInfo As String`.
- **Name local variables in camelCase.** Use lowercase for a common abbreviation: `json`, `sql`, `url`. Use a single lowercase letter for an obvious, tightly scoped purpose: `g As Graphics`, or `x` and `y` for coordinates. Use snake_case only when the name mirrors an external name, for example a field from a JSON API.
- **Write a call with no arguments without parentheses**: `Me.Refresh`, not `Me.Refresh()`. **Write a call that passes arguments with parentheses**: `list.AddRow("Apple")`. Xojo makes the parentheses optional in both cases, so this is a deliberate style choice, not a syntax rule.
- **When you edit an existing project, match its code**, unless the user instructs otherwise. Match:
  - the API usage of the project
  - the variable case
  - the choice of `Var` or `Dim`
  - the parenthesization of calls
  - the other style choices

  The API 1.0 warning above still applies. Deliver the warning, but do not rewrite the code of the project uninvited.
- Declare several variables of the same type on one line (`Var apples, bananas As Integer`), not on sequential lines.
- When a variable exists only to hold a function result that no code reads afterward, the compiler warns about the variable. Either add `#Pragma Unused VariableName`, or remove the assignment and use the `Call` keyword instead.
- With `ExecuteSQL` and `SelectSQL`, bind values through the `values()` ParamArray parameter, not through the PreparedStatement classes.
- A method whose last parameter uses `Assigns` can have several parameters before that parameter.
- Identifiers are not case-sensitive: `myVariable`, `MyVariable`, and `MYVARIABLE` are the same variable.
- `#Pragma BreakOnExceptions` accepts the values `True`, `False`, and `Default`.

## Editing project files

The Xojo IDE writes and reads `.xojo_code`, `.xojo_window`, and the other files in a project. These files were never meant for people or for third-party software to read.

- Follow the file format strictly, as documented in `references/xojo-file-formats/`. Do not add XML-style comments. Do not add any style or structure that the format does not define.
- Preserve unknown tags, keys, and values. Never invent or renumber project item IDs; other files reference them.
- Comments with `//` inside method bodies are acceptable. Use them for clarity. Xojo has no multi-line comment.
- Do not reference raw file line numbers. The developer views this code in the IDE, where the numbering of the text file has no meaning. Count within the method instead: "lines 5-7 of the MyFunction function".
- An open IDE does not see disk edits. The IDE keeps the whole project in memory and does not watch the disk, so edits you make while the user has the project open are invisible to it, and an IDE-side save destroys them. The sibling `xojo-ide` skill makes the IDE pick them up: `xojoctl reload --discard` on any release (on IDEs older than Xojo 2026r3 it closes and reopens for you). Reload after every batch of disk edits, also so the user sees your changes as you work.

## Validating project changes

After creating or editing a project in Xojo Project format, validate it with the `xojo-lint` skill, which ships beside this one. Its `xojo_lint.py` script checks the structure of every `.xojo_*` file and conservatively repairs safe serialization details. Load that skill for the commands and the diagnostic codes. Never format a project the user has designated read-only.

## Scope

This skill covers the current documented API and everything that Xojo marks deprecated. This skill does not cover:

- the IDE itself
- licensing
- third-party plugins

The build excludes Spanish translations, drafts, and legal pages.
