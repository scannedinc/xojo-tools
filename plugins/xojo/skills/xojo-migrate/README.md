# Agent Skill: xojo-migrate

This skill converts Xojo desktop projects from API 1.0 to API 2.0. It runs in [Claude Code](https://claude.com/claude-code).

These pages call the older generation API 1.0. Xojo's own documentation calls it "pre-API 2.0" on the rare occasions it names it. Both terms mean the same thing.

You start the skill yourself. The agent cannot start it for you, because a migration rewrites your whole project. In Claude Code, run `/xojo:xojo-migrate`. In Codex, write `$xojo-migrate` in your message.

To ask what replaced one deprecated symbol, such as `RecordSet.MoveNext`, use the `xojo` skill instead: it holds the documentation and the deprecation indexes, and the agent loads it on its own.

The skill contains three parts:

- A deprecation matrix of more than a thousand symbols, derived from Xojo's documentation.
- Hundreds of conversion rules with find and replace patterns, caveats, and examples.
- Three Python scripts that inventory a project, look up a symbol, and sweep for missed conversions.

The skill is not a codemod. It does not convert a project on one command. The reason is in the next section.

## Why a rename is not enough

Most API 1.0 changes are renames. A few are not. Those few compile without an error and then behave differently.

| Change | What breaks |
| --- | --- |
| `InStr` to `IndexOf` | Not-found changes from `0` to `-1`. A hit at the first character now returns `0`. The old `> 0` test rejects that hit. |
| `Mid` to `Middle` | The index base changes from 1 to 0. `Mid` also clamped a start below 1, so a `For i = 0` loop was legal. Its direct conversion is not. |
| `Date` to `DateTime` | The epoch moves from 1904 to 1970. Every stored `TotalSeconds` value is then 66 years wrong. |
| `CreateBinaryFile` to `BinaryStream.Create` | Failure returned `Nil` before. It raises now. The `If b <> Nil Then` guard becomes dead code, and the exception has no handler. |

The build catches none of these. The confidence tiers, the caveats, and `references/conversion-traps.md` exist for them. The workflow converts semantics before names for the same reason.

## What a migration looks like

Ask Claude to migrate your project. Claude works through nine phases:

1. **Preconditions.** Check the project format, the git tree, and the branch.
2. **IDE converter.** You run **Project ▸ Update Controls to API 2.0** in the IDE. It renames the placed controls.
3. **Inventory.** Run `scan.py` and report what the project contains.
4. **Plan.** Order the categories so that one pass does not undo another.
5. **Fast pass.** Apply the high-confidence rules. Read each match once.
6. **Receiver pass.** Apply the medium and low rules. Resolve each receiver type first.
7. **Manual pass.** Convert `Date`, error handling, and the index traps.
8. **Type renames.** Rename the types that the IDE converter leaves.
9. **Validation.** Run `sweep.py`. Then compile and run the application.

Two behaviors are deliberate. Read them before you start.

**You compile, not Claude.** Xojo has no command-line compiler. Each category ends when you run Analyze Project and report the result. The skill never claims that a conversion works.

**Claude commits one category at a time.** Nothing is committed until you confirm that checkpoint. If a rule matches too much, you revert one commit.

CAUTION: This skill edits your source files. Start from a clean git tree on a migration branch. The recovery plan is `git revert`, and it needs those commits.

## Deliberate leftovers

Some calls stay deprecated on purpose. Xojo has no member access on a literal or on an expression in parentheses. So `InStr("0123456789", c)` cannot become the method form. A local variable at every call site is the only alternative.

The skill leaves those calls and marks each one:

```
#Pragma Warning "API 2.0: InStr with a literal source -- needs a local variable"
```

The mark shows in the IDE on every build. A report shows it once.

## Requirements

- **Xojo 2021r3 or later.** The `Desktop*` classes start in that release.
- **A project in text format.** Use File ▸ Save As and choose "Xojo Project". Binary and XML projects cannot be scanned.
- **The Xojo IDE.** You compile every checkpoint there. You also run **Project ▸ Update Controls to API 2.0** there. That converter is a prerequisite of this skill, not an alternative to it.
- **git**, with a clean tree.
- **python3** on the PATH. The scripts use the standard library only.

The skill covers desktop projects. It marks the iOS, Web, and Android surface as out of scope.

## What each file does

| File | What it does |
| --- | --- |
| `SKILL.md` | Holds the instructions Claude follows. Claude loads this file automatically and reads the others on demand. |
| `LICENSE` | Holds the MIT license and the Xojo attribution notice. |
| `README.md` | This file. Claude does not need it. |

### The `references` directory

| File | What it does |
| --- | --- |
| `coverage.json` | Holds the matrix: one row per symbol, with old name, new name, bucket, status, release, and a note. A row can also record `live_on` and `chains_to`. See the note below. |
| `rules.json` | Holds the rules: patterns, confidence tier, caveats, hand-conversion notes, and worked examples. Each rule carries `applies`, which says whether its pattern pair is safe to run. |
| `conversion-traps.md` | Lists the changes that a rename does not fix. Read it before you touch string, array, date, or error-handling code. |
| `pass-hazards.md` | Explains why a count of zero matches does not mean the work is complete, and why a large count does not mean a lot of work. Read it once, before the first category. |
| `ide-vs-source.md` | Explains what the IDE converter changes and what it leaves. Also explains the difference between deprecated and removed. |
| `applying-rules-by-script.md` | Explains the `$1` backreference dialect and the `applies` gate. Read it only if you run the rules from a script. |

Two fields need a word of their own. `live_on` names the receivers where a deprecated member name is still correct in API 2.0, on dozens of rows. `chains_to` marks a replacement that Xojo then deprecated again, on a few rows.

### The `scripts` directory

| Script | What it does |
| --- | --- |
| `scan.py` | Inventories the project. Reports every deprecated symbol, by bucket. Segments each file first, so the counts show code and not layout metadata, notes, comments, or string literals. That gap is often 3 to 4 times. |
| `sweep.py` | Sweeps for what the rules cannot match. Every member rule needs a dot, so no rule sees `Invalidate` where the code means `Self.Invalidate`. The script also removes the identifiers that your project declares, and prints which names it removed. |
| `lookup.py` | Queries the data: one symbol, one rule, one category, or one confidence tier. |

Run them like this:

```sh
SKILL=/path/to/the/xojo-migrate/skill

python3 $SKILL/scripts/scan.py   /path/to/project
python3 $SKILL/scripts/sweep.py  /path/to/project --context
python3 $SKILL/scripts/lookup.py symbol RecordSet
python3 $SKILL/scripts/lookup.py rule c0r13
python3 $SKILL/scripts/lookup.py tier high cat3
```

Substitute the real location of the skill. With the plugin installed in Claude Code, that is `~/.claude/plugins/cache/xojo-tools/xojo/<version>/skills/xojo-migrate/`.

`scan.py` and `sweep.py` both accept `--format json`.

## Coverage

The matrix holds more than a thousand symbols. The bucket tells you what each symbol costs you:

| Bucket | Count | What it means |
| --- | ---: | --- |
| `Source — member` | ~730 | Deprecated member calls. The name alone does not give the type, so treat these as leads. |
| `Source — global` | ~110 | Deprecated global functions. |
| `Out of scope` | ~90 | The iOS, Web, Android, and PDF surface. |
| `Removed` | ~90 | Does not compile. These are build errors before the conversion starts. |
| `IDE handles` | ~50 | Control renames. The IDE converter does these. |
| `Source — type` | ~50 | Type names that the converter never touches, such as `Date` and `HTTPSocket`. |
| `No replacement` | ~40 | Still compiles. Xojo documents no successor, so the feature needs a redesign. |

The skill holds hundreds of rules in eleven categories. Most are high or medium confidence, and a smaller set is low confidence or manual-only. No rule is approved for a project-wide replace. The tier tells you how hard to look, not whether to look.

## Where the data comes from

The matrix is derived from Xojo's documentation. The sources are the deprecated-symbol indexes and the per-release deprecation tables. Its coverage is therefore a property of those sources. The build also recovers the symbols that Xojo lists by name with no detail page. Several hundred rows on `Window`, `MenuItem`, `TextEdit`, `PopupMenu`, and `Serial` come from that recovery.

The rules, the tiers, the caveats, and the traps are written by hand on top of the matrix. They are the part with an opinion in it. A build step checks every rule against its own examples, so the documented pattern dialect is tested and not asserted.

Some mappings could not be checked against a documentation page. Each of those rows says so in its `note` and asks you to confirm it. Read the note. It is part of the answer.

## Limits

- The skill covers desktop projects only.
- Claude cannot compile or run Xojo. You are the build step.
- A member match does not give the receiver type. A rule can match ninety lines and be correct on twenty of them. One line of source does not hold enough to decide.
- No rule matches across a line continuation. No member rule matches a call without a receiver. Phase 8 requires `sweep.py` for that reason.
- The skill reads text-format projects only.
