---
name: xojo-migrate
description: >-
  Migrate a Xojo desktop project from API 1.0 (which Xojo's own documentation
  calls "pre-API 2.0") to API 2.0: a rule-driven, confidence-tiered conversion
  of the source code, committed one category at a time, that fixes the index
  bases, sentinels and epoch shift a rename alone leaves wrong. Replaces
  deprecated APIs such as MsgBox, Dim, RecordSet, SQLSelect, Date, InStr, Mid,
  Len, Ubound, ListBox members, GetFolderItem and error-code checks. Covers
  more than a thousand deprecated and removed symbols with hundreds of vetted
  conversion rules. Invoke this skill only when the user asks for it by name:
  it rewrites a whole project across many commits, so never start it on
  inference. When a user wants a migration, tell them to run the skill
  themselves (/xojo:xojo-migrate in Claude Code, $xojo-migrate in Codex) and
  wait for them to do it. Questions about API 1.0 versus API 2.0, whether a
  symbol is deprecated, and what replaced it belong to the xojo skill instead,
  which holds the documentation and the deprecation indexes.
disable-model-invocation: true
---

# Xojo API 1.0 → API 2.0 migration

**The two names for the old API.** This skill calls it API 1.0. Xojo's own documentation almost never names it at all, and where it does the term is "pre-API 2.0". The two mean the same generation, so search for either.

Rule-driven, confidence-tiered conversion of Xojo source code. This skill bundles a deprecation matrix (more than a thousand symbols, generated from Xojo's own deprecation docs and the IDE's deprecation database) and hundreds of reviewed conversion rules with find/replace regexes, caveats, and before/after examples, each one machine-checked against the rule that carries it.

Detection is IDE-first: when the sibling **xojo-ide** skill can reach a running IDE, the worklist comes from Xojo's own Analyze Project, which resolves receivers and types the way no regex can. The bundled scanner remains as the fallback—no IDE reachable, project will not open, or the user asks for it—and as the closing cross-platform check either way (phase 2 explains the split). The conversion rules, caveats and traps apply identically whichever path located the work.

The mindset that matters: **the dangerous bugs here are runtime bugs, not compile errors.** Several API 1.0 functions changed index base (1-based → 0-based), one changed its not-found sentinel (`InStr`'s 0 → `IndexOf`'s -1), and `Date`'s epoch moved 66 years. A rename that compiles can still be wrong. That is why rules carry confidence tiers and why the workflow below fixes *semantics before names*.

## What this is, and what it needs

**Requirements.** Desktop Xojo projects saved in **text format**, built with **Xojo 2021r3 or later** (when the `Desktop*` classes arrived), in a **git repository**, with **python3** on PATH for the bundled scripts. The **Xojo IDE is required**—this skill never compiles anything itself, so every checkpoint is an IDE compile: run through the xojo-ide skill when it can reach a running IDE, performed by the user otherwise. iOS, Web and Android surfaces are out of scope.

**Provenance, and what that means for trusting it.** The deprecation matrix is *derived* from Xojo's own published documentation—the deprecated-symbol indexes and the per-release deprecation tables—and from the deprecation database inside the Xojo IDE, so its coverage is a property of those sources rather than of anyone's memory. The conversion rules, caveats and traps are hand-written on top of it and reviewed against real migrations; they are the opinionated part. Where a mapping could not be verified against a documentation page, the row says so in its `note`. Treat a row's note as part of the answer, not decoration.

Xojo, Inc. is not affiliated with this skill and has not reviewed it, and "Xojo" is their trademark. No Xojo documentation is redistributed here; the **References** section links to it. This skill is MIT-licensed (`LICENSE`, beside this file) and comes with no warranty—it will happily hand you a wrong rename if you skip the receiver checks it keeps insisting on.

## Hard rules

1. **`high` describes the mapping, not the blast radius.** A `high` rule means *the replacement is the verified correct API 2.0 form*: the old name really does become that new name, with no index, sentinel, or epoch change hiding in it. It does **not** mean "safe to Replace All". No rule in this skill is authorized for a blind project-wide replace, because no regex here can tell code from a string literal, a call from a declaration, or one receiver type from another. Read the matched line before you change it. What the tier buys you is *how hard you have to look*: `high` needs a glance, `medium`/`low` need the receiver resolved, `manual` needs a rewrite.
2. **Member renames are type-blind, and this rule outranks rule 1.** `.Append` means `.Add` on an array but `.AddObject` on a Group2D; `.RemoveRow` is deprecated on ListBox but valid API 2.0 on RowSet; `.ColumnType` is deprecated on ListBox and *live* on RowSet. Before renaming any `.Member`—at **any** confidence—find the receiver's declared type and confirm the replacement applies. More than half of the `high` rules are anchored on a literal dot and rename a member; they are high because the mapping is right for the stated receiver, and they still need that receiver checked.
3. **A receiver must be an identifier—never a literal, never a parenthesised expression.** Xojo has no member access on either. Both of these are **syntax errors**, not stylistic choices:

   ```
   "0123456789".IndexOf(char)      ' literal receiver
   ("00" + Hex(red)).Right(2)      ' parenthesised-expression receiver
   ```

   A receiver is an identifier, or a chain of member accesses and calls off one—`s.Trim.Uppercase`, `f.Child("x").Name`, `dict.ExportXML(p).ToString` are all fine. This decides whether a whole class of conversions is *expressible at all*, so it outranks any rule's convenience.

   **What counts is why the parentheses are there, not that they are there.** Parentheses that *group an expression* block member access. Parentheses that belong to a call, a cast, or an index do not, and the result of any of those three is a perfectly good receiver:

   ```
   EncodeBase64(mb, 45).Split(delim)    ' OK -- global function result
   Dictionary(v.ObjectValue).KeyCount   ' OK -- cast result
   values(index).ReplaceLineEndings("") ' OK -- indexed access
   ("00" + Hex(red)).Right(2)           ' SYNTAX ERROR -- grouped expression
   ```

   Xojo's own documentation writes `GetType(d).GetProperties` throughout, so the call-result form is not a gray area. This matters because it is the shape you land on whenever a global→method rule skips a call for its *argument* rather than its receiver, and you then convert it by hand.

   Every global→method rule here captures an identifier receiver and silently skips everything else. For a skipped call there are exactly **two** outcomes: introduce a local variable, or leave the deprecated global in place. Hand-writing the method form is not a third option—it does not compile. `conversion-traps.md` §4 says which to choose and when.
4. **Fix `InStr`/`IdxField` result comparisons and index arithmetic BEFORE renaming the functions.** Renaming first hides the remaining wrong arithmetic. Details in `$SKILL/references/conversion-traps.md`.

   "Before" means *within the same edit*, not in an earlier commit. Splitting them leaves a tree where `InStr(...) >= 0` is API 1.0 code read with an API 2.0 sentinel—always true, compiles, wrong—which **Commit discipline** below forbids. Convert each site atomically, comparison and rename together, and commit the sites as one batch.
5. **Byte-variants before base names**: `LenB/MidB/InStrB/ReplaceB/SplitB` before `Len/Mid/InStr/Replace/Split`, or the base-name pass mangles the byte variants.
6. **Nothing compiles Xojo except the Xojo IDE.** There is no standalone compiler. When the xojo-ide skill can reach a running IDE, run the checkpoints yourself—`analyze` compiles the project's front end and reports errors and warnings with file, method and line. Run each checkpoint as one bracketed session—`analyze --project <path> --discard`, which opens fresh, analyzes, and closes—per **IDE session discipline**: the project never sits open in the IDE while you edit. When it cannot, every phase ends with the user compiling / running Analyze Project and reporting back the error and warning counts. Either way an analyze pass is not a runtime pass: never claim a conversion "works"; say it analyzed clean and awaits the runtime check, which is always the user's—the dangerous bugs here are runtime bugs.
7. **Match rule casing exactly** in replacements (Xojo identifiers are case-insensitive, but canonical casing keeps the code readable and consistent with the docs).
8. **Git is not optional, and one commit is not enough.** Do not begin editing outside a git repository. Commit at every checkpoint, one commit per category, so each batch can be reviewed and reverted on its own. A single commit at the end is a wall of renames nobody can review; a rule that over-matched is then indistinguishable from one that worked. See **Commit discipline** below.

## Preconditions (phase 0)

Before editing anything, confirm with the user:

- **Git repository, clean tree, migration branch.** This is a hard requirement, not a suggestion: several rules can over-match, and the recovery plan is `git revert`, not memory.

  ```
  git -C <project> rev-parse --is-inside-work-tree   # must print exactly: true
  git -C <project> status --porcelain                # must print nothing
  ```

  "Work tree" here means *the checked-out files you edit*, as opposed to the `.git` database, and has nothing to do with the `git worktree` command or with branches. The question being asked is "is there a checkout here I can edit and commit?"

  Check the *output* of the first command, not just its exit status: outside a repository it exits non-zero, but inside a **bare** repository (a `.git` database with no checked-out files, the kind a server hosts) it exits 0 and prints `false`. `true` is the only acceptable answer.

  - **Not a repo?** Offer `git init` plus an initial commit of the current state. Do not proceed until that baseline exists; without it there is nothing to diff the migration against.
  - **Dirty tree?** Stop and ask the user to commit or stash. Their in-progress work must not end up inside a conversion commit.
  - **Then branch:** note the current branch name first (`git branch --show-current`); that is the base you will diff against later. Then `git switch -c api2-migration`. The whole migration is reviewable as one branch and abandonable with one command.
  - **Binary/XML project?** The text-format save (below) is itself the first commit, before any conversion.
- **Text-format project.** Source must be `.xojo_code` / `.xojo_window` etc. If the project is binary (`.xojo_binary_project`) or XML, ask the user to File ▸ Save As... in "Xojo Project" (text) format first. `$SKILL/scripts/scan.py` detects this and prints the instruction.
- **Xojo version.** Desktop* control classes need Xojo 2021r3+. Ask which release they build with.
- **Deprecation warnings on.** They are off by default, stored **per project**, and Analyze Project says nothing about deprecations until they are on. With the IDE reachable, do it yourself, in this order: close the project (`python3 -m xojoctl close --save`), run `python3 $SKILL/scripts/analysis_warnings.py <project-dir> --enable`, reopen. The ordering is mandatory—the IDE rewrites the settings file when the project closes, so a patch made while it is open is silently undone. Otherwise ask the user: Project ▸ Analysis Warnings → check both "Item1 is deprecated" warnings and "Show API 2 Desktop control deprecations". Mechanism and caveats in `$SKILL/references/ide-vs-source.md`.
- **The project is hands-off while the migration runs.** Say this to the user up front: outside the steps the workflow explicitly hands them—the phase 1 converter run, plus the checkpoints and the runtime pass when you cannot reach the IDE—the project is not theirs to touch until the branch is handed back. On the IDE path the workflow opens and closes the project repeatedly (see **IDE session discipline**), so any IDE window it leaves open is transient and about to be closed without saving; edits the user makes in the IDE mid-run are silently discarded by the next cycle, and edits they make on disk land inside conversion commits where they do not belong. If they need to change something mid-migration, they say so; you stop at a clean checkpoint and hand the tree back.

## Commit discipline

**One commit per category.** Arrays, then ListBox, then Database, then Date, and so on, each its own commit, so the reviewer reads "what happened to the arrays" rather than 4,000 renamed lines. Within a category, `high` and `medium`/`low` work can share a commit; across categories, never. Splitting one category into several commits by hazard class is allowed and sometimes better—byte variants, sentinel rewrites and compound-receiver deferrals each read cleanest alone. The rule is a ceiling on commit scope, not a floor.

**Commit only after the checkpoint is confirmed.** The order is always: make the edits → Analyze Project (run it yourself through xojoctl when the IDE is reachable, per hard rule 6; ask the user otherwise) → read the result → commit. Never commit changes whose compile status nobody has checked.

**When the user declines the checkpoints.** Some users will opt out of compiling per category and ask you to run the whole migration through. That is their call to make, and it does not change the commit discipline—it changes what the `Compiles:` trailer says. Record the fact in **every** affected commit, in these words, rather than omitting the trailer:

```
Compiles: NOT VERIFIED -- user opted to skip the per-category IDE checkpoints
```

Silence reads as "checked and fine" to anyone reading `git log` later, which is precisely the claim you are not in a position to make. Say it once to the user up front as well: without the checkpoints, a rule that over-matched will surface at the end against the whole branch instead of against one category, and `git revert` of a single commit stops being a usable recovery.

**The two categories expected to break the build** are Date and error handling: the compile errors *are* the worklist. Do not commit a half-migrated Date category as if it were finished. Either carry the mechanical pass and its manual follow-up into one commit, or commit the mechanical step with the breakage stated plainly in the message body and land the fix in the very next commit.

**Message format.** Match the project's existing convention; read `git log` first. If there is none, use:

```
Xojo API 2.0: <category>, <what changed>

<n> occurrences across <n> files. Rules applied: c2r0, c2r5, ...
Skipped: <what and why>
Still manual: <what remains>

Compiles: analyze <e> errors, <w> warnings via xojoctl / analyze <e> errors, <w> warnings reported by <user> / expected errors, fixed in the next commit
```

Listing the rule ids matters: when a rename turns out wrong three commits later, the id is how you find every other place that rule touched.

**Never push, and never commit outside the migration branch.** Pushing is the user's call. At the end, hand them the branch and the commit list.

## IDE session discipline

**The project is open in the IDE only while the IDE is doing something for you, and closed before you edit anything on disk.** The IDE loads the whole project into memory and never watches the disk: while a project sits open, disk edits are invisible to its analyze, a single IDE-side save silently overwrites them, and the open window reads as an invitation for the user to keep working in an IDE whose in-memory state the workflow is about to discard. Closing before you edit makes all three impossible instead of merely unlikely.

Every IDE interaction is therefore a bracketed session, and edits happen only between sessions:

```
open → analyze → close → edit on disk → open → analyze → close → commit → next category
```

**One command runs the whole bracket.** `xojoctl analyze --project <path> --discard` is the session: it discard-closes a stale open copy of the project, opens it fresh from disk, analyzes, and closes without saving—verified rather than assumed, and exit 4 means the bracket broke and the project is still open, which is not a state to edit in. Use it for every checkpoint. The rules below govern the manual commands (`open`, `analyze`, `close`) when a step must run separately.

- **This costs nothing.** With the commands this workflow uses, making an open IDE see disk edits is already a close and a reopen (the xojo-ide skill's editing-and-reload reference), so the close/open pair is being paid at every checkpoint regardless. The discipline only moves the close to *before* the edits, so no moment exists in which an open IDE and newer disk files disagree—a reasoning even `xojoctl reload` does not change (this workflow deliberately does not use it): a reload happens after the edits, and the hazard is the open window during them.
- **A session may begin with the project already open.** The checkpoint command handles it: a stale open copy of the target is discard-closed and the project reopened fresh, so phase 0's reopen and the user's phase 1 converter run (once saved) hand off cleanly. What the discipline forbids is *editing* while the project sits open, not finding it open.
- **End an analyze session with `close --discard`.** The session made nothing worth saving, and the disk—where git is—is the migration's only source of truth; a `--save` here would let the IDE write its in-memory copy over it. The one deliberate `--save` in this workflow is phase 0's analysis-warnings step, which needs the IDE to write the settings record as the project closes.
- **Confirm the frontmost project first.** Xojo is single-instance and `xojoctl` acts on the frontmost open project. If anything else may be open in the IDE, run `projects` before `analyze` or `close`—an unchecked session can report on, or close, a project that is not yours.

**Report the counts, every time.** Each analyze returns an error count and a warning count; report both to the user at every session, beside the previous session's numbers—"analyze: 0 errors, 210 warnings (was 260: the ListBox category cleared 50)". The falling warning count is the migration's only live progress meter, and a checkpoint where it does not fall—or where errors appear outside the two categories expected to break the build—is a stop-and-look signal, not a footnote. Two caveats keep the numbers honest: analyze counts every warning type the project's settings enable, not only deprecations, so the finish line is *zero deprecation warnings* (phase 8), not zero warnings; and when the IDE is unreachable and the user runs Analyze Project, ask for both counts and track them the same way.

## Workflow

Read `$SKILL/references/ide-vs-source.md` before phase 1, and `$SKILL/references/conversion-traps.md` before phases 3–6. Its §8 (string literals) and §9 (declarations) are what phase 4's per-match glance is checking for.

### 1. IDE converter first

Ask the user to run **Project ▸ Update Controls to API 2.0** in the IDE, then commit the result as the **first commit on the migration branch**. Have them save in the IDE and confirm the converter's diff is on disk (`git status` shows it) before any bracketed session runs—the checkpoint command discard-closes an open copy of the project first, which would destroy an unsaved converter run. It is a large, entirely IDE-generated diff; keeping it separate is what makes every later commit readable as your work rather than the converter's. If they can't or won't, note it; type renames move to phase 7.

### 2. Inventory

Set `SKILL` to the installed skill directory first (see **Data access** below); the scripts live there, not in the user's project.

Two ways to build the worklist, and the preference between them is not a coin flip. Use the IDE's analyzer whenever the xojo-ide skill can reach a running IDE; use the bundled scanner when it cannot, when the project will not open or analyze, or when the user asks for the scanner. They fail in different directions. The analyzer resolves receivers and types—`.ListCount` on a ListBox is a finding, `.ListCount` on the user's own class is silence, and receiverless calls, paren-less statement calls and continued lines are all visible to it, because it is the compiler. The scanner reads text and is type-blind. But the analyzer only compiles the platform the IDE is running on, so `#If TargetWindows` bodies are invisible to it on macOS; the scanner is the only inventory those branches get. An IDE-driven migration therefore still ends with one scanner pass (phase 8).

#### 2a. IDE analyze (preferred)

With the deprecation warnings on (phase 0), run one bracketed IDE session (**IDE session discipline**):

```
python3 -m xojoctl analyze --project /path/to/Project.xojo_project --discard --json | python3 $SKILL/scripts/worklist.py
```

Report the analyze counts now: they are the baseline every later checkpoint's numbers fall from.

**Compile errors are input, not failure.** A freshly converted project routinely fails to build—the phase-1 converter renames control types and leaves member calls behind—so `analyze` exiting 1 with `outcome: project_errors` is the normal phase-2a state, and `worklist.py` accepts it: those errors are the `Removed` bucket and the converter's leftovers locating themselves. What `worklist.py` refuses is a document whose analysis never ran—a failed connection, a timeout, no project open—which carries an error object and an empty diagnostics list. Its refusal message is the one to act on: nothing has been learned about this project's deprecations, so fix the IDE connection and re-run, or take the scanner path in 2b. Also refuse to proceed whenever the document's `session.closed` is `false`, whatever the exit code—the analysis ran but the project is still open in the IDE (a clean analyze reports it as exit 4; a failing one keeps its own exit code), and editing now is how disk edits get overwritten. Close it (`close --discard`) first. What you must not do is record a failed analyze as "no deprecations found".

Each deprecation warning is a compiler-verified work site with method, line and the replacement named in the message ("Left is deprecated. You should use String.Left instead"). No receiver check is needed to trust the *finding*—the compiler resolved the receiver to produce it. Errors in the same output are the `Removed` bucket locating itself. One mechanical fact about those line numbers: they count within the named method's body, not within the file, so driving edits from a diagnostic means mapping owner + method + line to a file line yourself.

**Do not work from the raw warnings.** The IDE's message reads like a complete instruction, and for a handful of symbols the rename it proposes is the part that compiles and is still wrong: `InStr`'s not-found sentinel moves from 0 to -1, several functions change index base, and `Date.TotalSeconds` → `SecondsFrom1970` shifts the epoch by 66 years. The IDE never mentions any of it. `worklist.py` joins every warning to the matrix and leads with the sites that need more than a rename, in four groups: **hand conversion required**, **read the caveat before renaming**, **mechanical rename**, and **the IDE converter handles this** (control type renames, phase 1). It reports rule ids for `lookup.py rule <id>`; it decides nothing, and where the join is ambiguous it says so instead of picking.

Two properties of the real messages are worth knowing, because they bound what the join can do. Member deprecations arrive with **no receiver**—"ListCount is deprecated. You should use RowCount instead"—so the replacement is what disambiguates `ListBox.ListCount` from `PopupMenu.ListCount`; when it cannot, the report says AMBIGUOUS and you confirm the receiver yourself. And a symbol the matrix does not cover is listed separately rather than dropped: the IDE found a deprecation the bundled data missed, which is worth knowing.

Then plan and execute phases 3–7 unchanged. The analyzer found the line; it did not make the rename safe.

Run the scanner as well when the up-front plan needs the shape of the job—its per-bucket counts (`Removed`, `No replacement`, and so on) remain the fastest overview to present before the first category.

#### 2b. The bundled scanner (fallback, and the closing cross-platform check)

```
python3 $SKILL/scripts/scan.py /path/to/project            # human-readable
python3 $SKILL/scripts/scan.py /path/to/project --format json
```

**Present the in-code count, not the raw hit count.** `scan.py` reports `N in code (M raw)`: the first number excludes layout metadata, `#tag Note` blocks, comments and string literals, while the second counts every textual match. Only the first is a worklist. The gap is routinely 3–4x—a window's `Left = 110` and `Text = "OK"` layout properties alone can produce hundreds of matches for `Left` and `Text`—and leading with the raw number sets an expectation for the whole job that the real work will not match. Quote the raw number only to explain why a symbol looks alarming and isn't.

**Never convert a symbol that is not compiled.** A deprecation is a property of code the compiler reads. A `#tag Note`, a comment and a string literal are not that, so a deprecated name inside one is not a deprecation and converting it fixes nothing. This is easy to get wrong from the *other* direction: `scan.py` already excludes these regions, so the temptation arises when a plain text search, a grep, or your own reading turns one up and it looks like a symbol the scanner missed. It did not miss it.

`#tag Note` blocks are the trap, because their content is often whole slabs of real, syntactically valid old code that someone parked there instead of deleting:

```
#tag Note, Name = Old drawing code
  #elseif TargetWin32 ///////////////////////////
  ...400 lines of archived code...
#tag EndNote
```

Editing that changes a comment, adds noise to a diff that is supposed to be pure renames, and reports as a fix that fixes nothing. Leave it. If a note's archived code is worth migrating it is worth deleting instead, and that is the user's call, not part of this migration.

Even the in-code number is an upper bound: member matches are type-blind, so a symbol whose receivers all turn out to be user classes or live API 2.0 controls can go to zero. Say "up to M sites to review", never "M conversions".

Present symbols per bucket, with those counts. The seven buckets, and what each one means for the plan:

| Bucket | Meaning |
|---|---|
| `Removed` | **Does not compile.** Gone from the framework. These are build errors that exist before conversion starts; lead with them. |
| `Source — global` / `member` / `type` | The conversion work. Member matches are type-blind leads, not a to-do list. |
| `IDE handles` | Control/class renames the IDE converter does (phase 1), plus their event renames. |
| `No replacement` | Still compiles, but Xojo documents no API 2.0 replacement; needs redesign, not renaming. |
| `Out of scope` | iOS / Web / Android / PDF surface. |

Lead with `Removed`, then `No replacement`: those two are the ones that change what the project can even do, and neither is fixed by any rule.

**Anything left unconverted gets a marker at the site.** This is a hard rule of the workflow, not a nicety, and it applies to *every* deferral—not just the `No replacement` bucket. Deprecated calls still compile, so nothing will ever remind anyone they were deliberate. Leave the API 1.0 call in place and mark it with Xojo's own directive, which surfaces in the IDE's Issues pane on every build:

```
#Pragma Warning "API 2.0: JSONItem.DecimalFormat has no documented replacement -- unresolved"
#Pragma Warning "API 2.0: InStr with a literal source -- needs a local variable"
#Pragma Warning "API 2.0: DrawPolygon -- DrawPath takes a path object, not this coordinate array"
```

A line in a commit message is not a durable record: three months later the question is "this is still API 1.0, why?", and the commit body is not where anyone looks. A `#Pragma Warning` answers it at the call site, every build. Use `#Pragma Error` instead only if the user wants the build to stop until it is resolved.

**One marker per method is enough when a method repeats the same deferral.** A validation loop calling `InStr("0123456789", c)` dozens of times across dozens of methods does not need one identical marker per call; it needs the reader to find out once, wherever they enter the method. Put a single marker at the top of the method and say how many sites it covers:

```
#Pragma Warning "API 2.0: 3x InStr with a literal source -- each needs a local variable"
```

The rule being enforced is *the deferral is discoverable from the code*, not *the marker count equals the site count*. What is never enough is recording it only in the final report: the report is not in the IDE and not in the file. Where `conversion-traps.md` §4 says to "list them in the final report", that is in addition to the marker, never instead of it.

**Parked is not a fourth state.** Cross-category dependencies create sites that are "not due yet"—an `InStr` comparison waiting for the Mid commit's arithmetic, say. Give such a site its marker (or a written worklist entry) the moment you pass over it, and reconcile in phase 8: every deferral the report claims must trace to a marker at—or covering—its site. On one real migration two parked sites fell out of every tracked state and surfaced only in a closing dry-run—the report claimed two more deferrals than sites carried markers.

The three deferral categories that recur, all of which need this: compound receivers left as deprecated globals (hard rule 3), calls whose replacement takes a different *kind* of argument (`DrawPolygon`/`FillPolygon` → `DrawPath`/`FillPath`), and anything awaiting a design decision from the user.

**Not everything old is deprecated.** Some globals that look like obvious API 1.0 holdovers are still current, and the matrix's silence about them is the answer, not a gap: `Asc`, `Chr`, `Val`, `Str`, `Format`, `Hex`, `Abs`, `Min`, `Max`, `Round`, `CStr`. Do not convert them, and do not go hunting for a replacement when a user asks. Note the trap in the pair, though—the **byte variants `AscB` and `ChrB` *are* deprecated** (→ `String.AscByte` / `String.ChrByte`) even though their base names are fine. If `lookup.py symbol <Name>` returns nothing, the matrix does not cover the symbol; confirm against the xojo skill's deprecation indexes before declaring it current.

### 3. Plan the pass order

From the inventory, build the worklist honoring the ordering pitfalls:

1. Byte-variants before base names (hard rule 5).
2. Narrow patterns before sweeps: `As RecordSet → As RowSet` before any bare `RecordSet` rename.
3. `InStr`/`IdxField` comparison and index fixes before the renames (hard rule 4).
4. Method-form rules before global-form where both exist.
5. Category order roughly: strings → arrays → ListBox → Database → Date → error handling → globals → files → graphics → misc.

#### When the baseline has build errors, the errors come first

A freshly converted project usually does not compile (phase 2a: compile errors are input), and a tree that does not compile can confirm nothing—every category checkpoint would run against a broken build. So when the baseline analyze reports errors, burn the error surface down to zero first, in its own commits: the errors are compiler-located work, mostly member renames the phase-1 converter leaves behind plus the `Removed` bucket. Running those control-member categories first also sidesteps the arrays→`.LastIndex` interaction in `pass-hazards.md` §3 instead of creating it. The step-5 category order resumes once analyze reports zero errors.

#### One pass creates what the next pass matches

A rule can *produce* a name that a later category's regex then matches, so that category's hits are partly your own output rather than the inventory's. The documented order causes one instance of this (arrays → ListBox `.LastIndex`) and handles two others. **Read `$SKILL/references/pass-hazards.md` §3 before running the ListBox or array categories**—it names all three and gives the end-of-category check that catches a new one.

**This ordering is also the commit plan.** Each category in step 5 becomes one commit, in that order. Show the user the list up front ("roughly 9 commits, in this order, and here is what each will contain") so they know what they are agreeing to review. Categories with no hits are dropped from the plan; say which, so a missing commit does not read as a missed step.

#### What the analyzer already settled, and what it did not

Phases 4 and 5 ask three questions per match that exist because a regex cannot answer them. On the **IDE path** the compiler has already answered them, and knowing which is which prevents two opposite mistakes—re-deriving what is known, and trusting what is not.

**Settled, for every site the analyzer reported.** It is real code: the analyzer compiles, so a match inside a comment or a string literal cannot appear (phase 4's first question). The receiver is that type, and the member really is deprecated on it: the compiler resolved the receiver in order to raise the warning at all (phase 5's whole job). And phase 5's warning that most matches in the tier are wrong describes *regex* matching—an analyzer finding does not carry that false-positive rate, so do not dismiss one as scanner noise.

**Not settled, and still yours.** Whether the replacement the IDE named is the API 2 destination: it is sometimes another member of the deprecated class, which compiles and gets flagged again next pass, so `worklist.py` prints the conflict and `ide-vs-source.md` documents the shape. Whether the rename is *semantically* safe: index bases, `InStr`'s sentinel and `Date`'s epoch are invisible to the compiler, and the rule's caveat governs exactly as it would for a scanner hit. Which matrix row a bare member warning belongs to, when the replacement does not settle it—that is what an AMBIGUOUS group means, and it wants the receiver confirmed by hand. And anything outside the analyzed platform: `#If` branches for other targets were never looked at (phase 8).

Stated as one line: **the analyzer is authoritative about where a deprecation is—among the symbols its deprecation database knows—and merely helpful about what to replace it with.** The scanner path settles none of this and phases 4 and 5 apply to it unchanged.

### 4. Fast pass (`high` rules): one glance per match

For each `high` rule with hits, fetch it (`$SKILL/scripts/lookup.py rule <id>`) and walk its matches. Per match, three questions, all answerable from the one line you are looking at:

1. **Is it code?** Skip matches inside string literals and comments. No rule here can see the difference; you can.
2. **Does the rule's `caveat` name a hazard?** The caveats call out the two that recur: a *live API 2.0 collision* (the same member name is valid on another class) and a *declaration hazard* (the rule rewrites the identifier, so it would rewrite the user's own `Sub Speak(...)` too). A declaration hazard makes **each match ambiguous, not the rule inapplicable**—never skip the whole rule because the project defines the name, or you drop its true positives along with its false ones.
3. **Does the rule's `manual` note apply?** Compound-argument calls the regex deliberately skips must be hand-converted or explicitly deferred.

If all three are clear, apply it. This is a fast pass, not a blind one; most matches clear in a second.

**A global-form rule and its method-form sibling are two separate steps.** Most string and array functions survive in both forms, and each form is its own rule: `Len(s)` is c0r0 and `s.Len` is c0r1; `Mid(s, n)` is c0r8–c0r10 and `s.Mid(n)` is c0r11. The global rules are anchored `(?<![\w.])`, whose whole job is to *exclude* the dot form, so applying them cannot touch it. Fifteen member names are in this state, including `.Len`, `.Mid`, `.InStr`, `.UBound`, `.LTrim` and the byte variants.

Work the rules a symbol at a time, not a form at a time: `scan.py` lists every rule for a symbol on one line (`len ... rules: c0r0(high), c0r1(high)`), so clear that line before moving on. Skipping the sibling is invisible—the global rule reports zero remaining and the dot form is still there.

> **Phases 4 and 5 run per category, not project-wide.** Take one category from the step-5 order, do its `high` pass, then its `medium`/`low` pass, then checkpoint and commit, then move to the next. Running all the `high` rules across every category first would spread each category's changes over two commits and defeat the point of batching them.

**Then sweep for what the rules structurally cannot see.** Three call shapes are invisible to every pattern here—receiverless member calls, paren-less statement calls, and calls split over a line continuation—so **a rule reporting zero remaining matches is not evidence the symbol is converted**. `$SKILL/references/pass-hazards.md` §1 has the detail.

So after each category, sweep the *bare names* that category converted and reconcile the count against the matches you actually handled:

```
python3 $SKILL/scripts/sweep.py <project-dir> --only Invalidate,MsgBox,ReplaceAll --context
```

The leftovers are the receiverless calls, the continued calls, and anything a lookahead declined. This is a per-category step, not an end-of-run one: done at the end, you can no longer tell which pass should have caught them.

**Category checkpoint, then commit:** run Analyze Project—`python3 -m xojoctl analyze --project <path> --discard` (**IDE session discipline**) when the IDE is reachable, the user otherwise—report the error and warning counts against the previous checkpoint's, then commit that category alone. The Date and error-handling categories are *expected* to produce compile errors; the compiler is locating the manual work, so handle those two per **Commit discipline** rather than committing a broken tree as if it were done.

### 5. Receiver pass (`medium` / `low`)

Still inside the same category. These need something phase 4 does not: the *declared type of the receiver*, which is not on the line you are editing. For each hit, look up `Var`/`Dim ... As`, the parameter list, or the control's class; check the rule's `caveat`; then apply or skip. Log skips for the final report; the skip list goes in the commit message body, where it stays attached to the diff it explains.

A member is only in this tier because a plausible receiver takes a different replacement or needs none at all: `.RemoveRow` on a RowSet, `.ColumnType` on a RowSet, `.MoveNext` on an Iterator, `.Remove` on a Dictionary. Finding the declaration is the work; the rename is trivial once you have it.

**Expect most matches in this tier to be wrong, and check the ratio rather than the count.** On one real project `c3r31` matched hundreds of lines and a handful were correct to apply; `c10r15` matched dozens and none were. A rule matching ninety lines and converting twenty is the system working. See `$SKILL/references/pass-hazards.md` §2 for the measured table, and for why matches cluster in single files.

**Reading a declaration: one line can declare several types.** Xojo allows multiple clauses per `Dim`/`Var`, each with its own `As`:

```
Dim p As Picture, g As Graphics
Var i, j As Integer, name As String
```

Take the clause, not the line. Matching the first `As <Type>` on the line types `g` as `Picture` and then silently mis-converts or skips every `Graphics` call on it. Note also the second form: `i` and `j` share the single `As Integer` that follows them, so a clause's type can belong to a comma-separated *group* of names. Where the receiver is a control rather than a local, the declaration is not in the code at all—it is the `Begin <Class> <Name>` block in the window's layout metadata.

### 6. Manual pass

The structural migrations. **One commit each.** These are the changes most likely to be wrong in a way no compiler catches, so they are the ones a reviewer most needs to see in isolation. Each has a section in `$SKILL/references/conversion-traps.md`:

- `InStr` sentinel comparisons (`>0 → >=0`, `=0 → =-1`) if any remain.
- Index-decrement audit: simplify `(...) - 1`, hunt cross-statement double-decrements.
- `Date → DateTime`: immutability, constructors, `TotalSeconds` → `SecondsFrom1970` epoch shift (stored values must be re-based!), `ParseDate` → `DateTime.FromString`.
- Error codes → `Try/Catch` exceptions; socket/stream `Error` event signatures.

The epoch shift deserves its own commit whatever its size: it silently rewrites the meaning of stored data, and a reviewer needs to see exactly which reads and writes moved.

### 7. Type renames

Two different jobs land here; do not conflate them.

**7a. The `IDE handles` bucket: nothing to do here, by design.** Those control/class renames and every event rename that rides along with them are the IDE converter's job (phase 1), and running it is a **prerequisite of this skill**, not a preference. Do not reimplement it by hand:

- A control's type appears in *both* code and layout metadata, so a hand rename has to change two representations in step or the project will not open correctly.
- Event names change with the type and differ per control—a button's `Action` became `Pressed`, a checkbox's `ValueChanged`, a menu item's `MenuItemSelected`. `DesktopButton` has no `Action` event, so renaming a type and leaving its handler is a compile error.
- You already need the Xojo IDE: hard rule 6 means every checkpoint is compiled there. Anyone who can satisfy that can run **Project ▸ Update Controls to API 2.0**. And the `Desktop*` classes only exist in 2021r3+, so a project that cannot run the converter cannot reach the target API either.

If the converter genuinely has not been run, **stop and resolve that** rather than converting types by hand.

**The one thing to do here runs the other way: leave `.Action` alone.** A *menu handler*—`Function DoStuff() As Boolean Handles DoStuff.Action` in `App`, a window, or a container—**keeps `.Action`**, and the converter deliberately leaves all of them untouched. Only an `Action` event implemented on a `DesktopMenuItem` subclass becomes `MenuItemSelected`. Renaming the handlers unbinds every menu command in the application, and it compiles. Do rename any event definitions you added to a subclass *yourself*—the converter does not know about those. See `$SKILL/references/ide-vs-source.md` for how to read what the converter did and did not touch.

**7b. The `Source — type` bucket:** always, converter or not. These are the type names the IDE converter never touches because they are not placed controls: `Date → DateTime`, `HTTPSocket → URLConnection`, `SegmentedControl → SegmentedButton`, `Serial → SerialConnection`, `OpenDialog → OpenFileDialog`, the database types, and so on. Most have rules; the ones that don't are straight renames from the matrix (`lookup.py symbol <Name>`). `SegmentedControl` and `Serial` are the two that cannot be converted by changing `Super` alone; they need per-class attention.

Commit 7a and 7b separately. A type rename touches both code and layout metadata, so its diff looks nothing like the member renames that came before and should not be mixed in with them.

### 8. Validation and report

Run **Analyze Project** until it is clean of deprecations—`analyze --project <path> --discard` sessions (**IDE session discipline**) when the IDE is reachable, through the user otherwise, reporting the counts on every pass—and ask the user for a full runtime pass (the traps are runtime bugs; no analyze result speaks to them). On a cross-platform project, also state plainly that the other platforms' `#If` branches were converted by text passes no compiler has checked, and ask the user to run Analyze/build per target.

**Both scripts run here, whichever path built the inventory, and neither is optional.** They fail in opposite directions, which is why one cannot stand in for the other.

A clean analyze does not retire either of them, because the analyzer's authority has three holes. *Platform:* inside another platform's `#If` branch, nothing has looked yet—and that untouched region contains both of the shapes these scripts split between them: `scan.py` finds the ordinary dot-anchored and global hits there (both scripts tag such hits as inside `#if Target*`), `sweep.py` finds the receiverless and paren-less calls that no rule can match anywhere. On one real migration, more than half the `.Directory` sites sat inside `#If TargetWindows` after the IDE reported the symbol cleared to zero. *Database:* a symbol missing from the IDE's own deprecation data never warns at all—`CDbl` is deprecated in the documentation and the matrix, and dozens of compiled sites drew zero warnings—so the scanners are the only inventory such symbols get. *Vocabulary:* constructs that are not member or global calls, such as the `TargetCocoa` compiler constant, produce no deprecation warning by nature. Skipping the sweep on an IDE-driven migration therefore leaves the one class of site that neither the analyzer nor `scan.py` can see. Treat any in-code hit inside a platform branch as unfinished work, not scanner noise.

```
python3 $SKILL/scripts/scan.py  <project-dir>
python3 $SKILL/scripts/sweep.py <project-dir> --context
```

**Re-run `scan.py` and account for every remaining in-code hit**, comparing against the phase-2 inventory. Expect the type-blind member patterns to re-flag *correct* API 2.0 code (`.AddRow` on a ListBox, `.RemoveRow` on a RowSet, `.LastIndex` on an array); the goal is that global and type hits reach zero and every member hit is explained, not a literally empty scan. Do not skip this because you believe the categories are done. On the one migration that was checked afterwards by compiling, a re-scan of the handed-over tree listed **every** real leftover—a mix of string members, a system color and a container member—each with its replacement and its rule ids already attached. Every one had been passed over during the category work, and the run was declared finished without this step.

**Then run the bare-name sweep**, because `scan.py` alone cannot close the migration: it asks the rules what is left, and **the rules cannot see two whole forms**. A receiverless member call (`Invalidate` for `Self.Invalidate`) matches no dot-anchored pattern, and a paren-less statement call matches no `(?=\s*\()` pattern. A rule that structurally cannot match a form still reports zero remaining, and zero reads as done.

The sweep is cruder and stricter on purpose: for every symbol it searches the bare name, ignoring dots and parentheses, and filters out identifiers the project itself declares. Its two sections:

- **Receiverless member calls** — the blind spot. Account for **every hit in writing**: converted, deliberately left deprecated (with its `#Pragma Warning`), or an unrelated identifier. The receiver is the enclosing class, so take its type from the file's `Inherits` line or its `Begin <Class>` header.
- **SUPPRESSED** — names the project declares itself, whose framework occurrences are therefore hidden too. This is the filter's one weakness and it is printed rather than hidden. Review these by hand; a project-defined name makes each match *ambiguous*, not the symbol absent (see `conversion-traps.md` §9).

Writing the accounting down is what makes the deferral list honest—it is the same list the `#Pragma Warning` markers and the final report have to agree with.

**Final report.** Lead with `git log --oneline <base>..api2-migration`, using the branch name recorded in phase 0: the commit series *is* the report, one line per category, in the order the work happened.

Then report the leftovers as **three separate states**, never merged into "still manual"—they need different things from the reader, and merging them is how a deliberate decision gets re-litigated as an oversight:

| State | Meaning | Marker |
|---|---|---|
| **Converted** | Done and compiling. | — |
| **Deliberately left deprecated** | A decision, not a miss: compiles, warns, works. Compound receivers left as globals, calls awaiting a design decision. Give the reason. | `#Pragma Warning` at each site |
| **Unresolved** | No known replacement, or the replacement needs a redesign. May or may not compile. | `#Pragma Warning` / `#Pragma Error` |

Then the checklist:

- [ ] Work is on a migration branch, one commit per category
- [ ] IDE converter run; project compiles on renamed controls
- [ ] All high-confidence rules applied, recompiled per category
- [ ] All medium/low matches individually reviewed
- [ ] Index traps audited; no double-decrement; `(...) - 1` simplified
- [ ] `InStr` comparisons converted
- [ ] Date → DateTime constructions, mutations, epoch, formatting, parsing
- [ ] Error handling in Try/Catch; Error event signatures updated
- [ ] `Nil`-returning calls that now raise: guard deleted, `Try`/`Catch` added (grep for `Nil` near `BinaryStream.Create`, `TextOutputStream.Create`, `.Remove`, `.CreateFolder`—a surviving guard marks a missed conversion)
- [ ] `scan.py` re-run; every remaining in-code hit accounted for in writing
- [ ] Every symbol's method-form rule applied, not just its global-form rule
- [ ] `sweep.py` run; every receiverless hit accounted for in writing
- [ ] `sweep.py`'s SUPPRESSED names reviewed by hand
- [ ] Every deliberate deferral carries a `#Pragma Warning` at the site
- [ ] Other-platform `#If` branches named as compiler-unverified; per-target Analyze/build requested
- [ ] Analyze Project clean of deprecations; full app run-through done
- [ ] No commit left in a known-broken state

Hand the branch to the user; do not merge or push. If a category turns out wrong later, `git revert` that one commit, which is the whole reason the work was batched this way.

## Applying rules outside the Xojo IDE

Every `find`/`replace` here is written for the **Xojo IDE's Find panel** with "Use RegEx" checked: `$1`-style backreferences, case-insensitivity as an external flag, single-line matching. If you apply a rule with anything else—a script, `sed`, an editor—you must translate the dialect, and you must skip the locate-only rules whose `applies` is false, or you will delete the text they match. Both are in `$SKILL/references/applying-rules-by-script.md`.

## Data access

The scripts are stdlib-only python3 and locate their own bundled data, but they are *in the skill directory*, and your working directory is the user's Xojo project. Relative paths like `scripts/scan.py` will not resolve. Set a variable once and use it for every invocation and every reference file:

```
SKILL=/path/to/the/xojo-migrate/skill     # wherever this SKILL.md lives
```

```
python3 $SKILL/scripts/scan.py <project-dir> [--format json]  # inventory a project (phase 2)
python3 $SKILL/scripts/sweep.py <project-dir> [--context]     # final bare-name sweep (phase 8)
python3 $SKILL/scripts/lookup.py symbol <name>   # coverage entries + full rules for a symbol
python3 $SKILL/scripts/lookup.py rule <id>       # one rule, apply-ready (regex, caveats, examples)
python3 $SKILL/scripts/lookup.py category [catN] # the 11 categories / one category's rules
python3 $SKILL/scripts/lookup.py tier <t> [catN] # rules by confidence: high|medium|low|manual
python3 $SKILL/scripts/analysis_warnings.py <project> [--enable]  # report / enable the per-project deprecation warnings (phase 0)
python3 $SKILL/scripts/worklist.py [analyze.json] [--format json]  # join `xojoctl analyze --json` to the rules (phase 2a); reads stdin
```

`xojoctl` is not this skill's script: it belongs to the sibling **xojo-ide** skill (`$SKILL/../xojo-ide` in this plugin), whose own SKILL.md covers connecting to the IDE. The commands this workflow uses are `analyze --project <path> --discard [--json]` (the whole bracketed checkpoint in one command), plus `open`, `close` (`--save` only in phase 0's warnings step) and `projects` for the manual steps; run them from that skill's `scripts` directory (`python3 -m xojoctl ...`), in the sessions **IDE session discipline** prescribes. When that skill or a running IDE is unavailable, the whole workflow still runs through the user and the scanner path—the IDE preference is a preference, not a dependency.

`scan.py` and `sweep.py` answer different questions and both are required. `scan.py` opens the migration: what is here, per bucket, as a plan. `sweep.py` closes it: what did every rule structurally fail to see. Its main section is **receiverless member calls**—`Invalidate` where the code means `Self.Invalidate`—which no dot-anchored rule can match, and which therefore never appear as a remaining match anywhere else.

**python3 is a requirement, not a convenience.** The scripts are stdlib-only, but `scan.py` and `sweep.py` have no hand equivalent—segmenting a Xojo file into code and metadata, and censusing a project's declared identifiers, are not things to do by eye. If python3 is genuinely unavailable, say so and stop rather than half-running the workflow.

The two datasets are readable directly if you need to check one symbol without running anything: `coverage.json` is a JSON array of rows (`old`, `new`, `cat`, `status`, `since`, `note`, and where relevant `live_on` / `chains_to` / `src`), and `rules.json` holds full rule detail. A row carrying `"src": "xojo-ide-db"` was filled from the Xojo IDE's own deprecation database rather than from a documentation page, and its replacement was verified against the documentation's member index before import—see `ide-vs-source.md`, which also covers why the IDE's own suggestion is sometimes not the API 2 destination. **Do not read either whole**—they are large. Grep for the symbol, or use `lookup.py`, which is what it is for.

## References

Bundled with the skill:

- `$SKILL/references/conversion-traps.md` — read before touching string/array/ Date/error code. Index shifts, sentinels, double-decrement, receiver rule.
- `$SKILL/references/applying-rules-by-script.md` — the `$1` backreference dialect and the `applies` gate. Only needed if you drive the rules from a script rather than the IDE's Find panel.
- `$SKILL/references/pass-hazards.md` — read once before the first category pass. Why a rule's zero is not completion, why its large match count is not work, and how one pass creates what the next pass matches.
- `$SKILL/references/ide-vs-source.md` — what the IDE converter does and does not touch, how to read its silence, deprecated-vs-removed, and enabling the analyzer's deprecation warnings programmatically.
- `$SKILL/references/coverage.json` / `$SKILL/references/rules.json` — the datasets behind the scripts.

Fetched from Xojo when you need them. **The bundled matrix is the primary reference for what is deprecated during a migration, and the xojo skill's indexes are the cross-check**; these are for understanding an API you are converting *to*, or for anything the matrix does not cover:

- <https://documentation.xojo.com/topics/api_design/moving_to_api_2.0.html> — Xojo's own "Moving To API 2.0" overview. Background for API 2.0 idioms (`Var`, iterators, enumerations). Read it once at the start if the codebase is unfamiliar; it is not a per-symbol reference.
- <https://documentation.xojo.com/llms.txt> — an index of links to every documentation page, in a form built for agents. Use it to find the canonical page for a class, then fetch that page. This is the fastest way to answer "what does `DesktopSlider` actually expose in API 2.0?"

There is also a `llms-full.txt` at that host, which is the entire corpus inlined. **Do not fetch it during a migration**—it will consume the context the migration needs. It is useful only if downloaded and grepped locally.

Prefer a specific page over a search. `lookup.py symbol <Name>` first, the canonical doc page second, a web search last.

## Writing converted code

Follow Xojo API 2.0 idiom in anything you write: `Var` not `Dim`, exceptions not error codes, 0-based `...At` methods, `For Each` iterators where natural. Do not modernize beyond the rules uninvited (e.g. don't restructure working logic, rename user identifiers, or reformat untouched lines); conversions should produce reviewable diffs.
