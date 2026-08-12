# The category playbook

The per-category pipeline recipe. One contract governs it: **derive nothing this file already states; judge everything it marks as yours.** On the migration that produced this file, the agent spent roughly a quarter of the run re-deriving pass orders, pipeline choices and checkpoint sequences that never vary between projects—this file is that derivation, done once. The judgment calls are listed first because they do not shrink.

## What stays your judgment

The tools locate, classify and count. They do not read code for you:

- Every rule's `caveat` and `manual` note, before its first application in a run (phase 4's three questions stand unchanged).
- Receiver resolution wherever the census cannot settle it: SUPPRESSED names, `live_on` collisions, worklist AMBIGUOUS groups, everything in phase 5.
- The `InStr` consumer decisions—how each result is *used* (comparison, arithmetic, stored position). c0r17–c0r19 locate the shapes; the rewrite is reading code.
- Mid bound-audit verdicts the audit sends to hand review: parameter-fed starts, `For Each`, non-literal bounds.
- Introduce-a-local versus leave-deprecated for each illegal receiver (conversion-traps.md §4), and the name-collision check before any introduced local.
- Confirming the double-decrement cancel on drained position-arithmetic sites, and reading other platforms' `#If` branches in phase 8.
- Anything the checkpoint differ flags: a NEW error, an unexplained symbol delta, a novel pass-creates-what-the-next-matches shape.

## The migration workspace

Checkpoints and queues need a home that can never dirty the tree or land in a commit. Use a directory inside `.git`—git ignores its own directory's extra files, and it survives the session:

```
MIG=<project>/.git/xojo-migrate
mkdir -p "$MIG"
```

It holds two things. **Checkpoint documents**: every bracketed analyze is saved as `$MIG/cp-NN-<slug>.json` (`cp-00-baseline.json` first), because the differ needs the previous one and the final report diffs cp-00 against the last. **The queues file**, `$MIG/queues.md`, with two lists that are different objects:

```
## PARKED — waiting on a later pass; no marker yet, by design
- ParserModule.Compute FileA.xojo_code:210 -- InStr half of a position pair; blocked on: Mid pass

## DEFERRED — permanent; the #Pragma marker is already at the site
- OtherWin.Refresh FileB.xojo_code:88 -- compound receiver, left as deprecated global; marker: yes
```

A DEFERRED entry gets its `#Pragma Warning` **in the same edit** as its queue line—never later. A PARKED entry names the pass it waits on and gets no marker (it is not deferred; it is scheduled); it leaves the queue only by becoming Converted or Deferred-with-marker at the drain step (below). On the migration that produced this file, two parked sites fell out of every tracked state and the closing report claimed two more deferrals than sites carried markers; the queue file plus the boundary oracle is what makes that slip impossible.

## The pipeline decision rule

Per category—sometimes per rule—choose between two pipelines. The choice is a census, not a feeling:

1. **Census the member names** the category renames: `python3 $SKILL/scripts/sweep.py <project-dir> --only Append,Insert,Remove,Ubound --format json` and read `.suppressed`—a name absent from it is declared nowhere in the project.
2. **Canary the census once per run** before trusting it: sweep one name you know the project declares and confirm it appears suppressed. (The check that later catches a collision must first be seen catching a known one—the field lesson was an introduced local that silently shadowed the existing counter consuming its result, in three methods at once.)
3. **Check `live_on` collisions** for each rule: a member can be deprecated on one class and live API 2.0 on another (`.Remove` on Dictionary, `.RemoveRow` on RowSet—pass-hazards.md §1 records the inversion where all 15 regex matches were the live kind). `lookup.py symbol <Name>` prints the rows; if the project uses a `live_on` receiver at all, the regex path is out for that rule.

**Census clean and no `live_on` receiver in use → the regex path**: `apply_rules.py` with the category's ordered rule ids, dry first, then `--apply`; its per-rule summary is pasted into the commit body. **Either check dirty → the receiver-sensitive path**: the locate filter's file:line list drives `targeted_rename.py` for the settled groups, and phase 5's declaration reading handles the rest. Global-function rules default to the regex path; the identifier-rewriting globals of conversion-traps.md §9 get the census first like members. When in doubt, the receiver-sensitive path is never wrong—only slower.

## Ordering laws

Each is one line here because its full story is told elsewhere; the point of this list is that no project changes it:

- **Byte-variants before base names** (hard rule 5): `LenB/MidB/InStrB/LeftB/RightB` (c0r2/3/5/7/12, c0r20/21) before their base names, or the base pass mangles them.
- **Paren-removers before argument-matchers**: rules that erase parentheses (c0r0 `Len(x)` → `x.Length`) run before rules whose find must match inside argument lists—`Left(s, Len(x))` becomes matchable only after `Len` loses its parens. Measured effect: a couple dozen extra mechanical sites on one project from this ordering alone.
- **Sentinel fixes in the same edit as the rename** (hard rule 4): c0r17–c0r19 govern every `InStr` site's comparison before c0r13–c0r16 rename it.
- **Position-arithmetic pairs convert together**: a `Mid` and an `InStr` feeding each other in one expression cancel their `-1`s (conversion-traps.md §3). Convert the pair in the Mid pass; PARK the `InStr` half until then, never convert it alone.
- **Class change before member rename** where the member's destination lives on a different class: `StringShape → TextShape` must land before `TextFont → FontName` means anything.
- **Compound-receiver deferrals get marker and queue line in the pass that skips them**, not at the end.

## Pass E: the error burn-down

When the baseline has build errors (the normal post-converter state), they come first (phase 3), and the burn-down is compiler-grouped and map-driven:

1. The locate filter over `cp-00-baseline.json` gives every **error** a file:line (errors are enriched too).
2. Group errors by message shape. The bulk is usually one shape—"Type DesktopX has no member named Y"—where the compiler has already resolved the receiver type, so **no census is needed**. One `lookup.py symbol Y` per (type, member) group supplies the replacement; write one rename-map entry per group. This is the judgment step, once per group, not per site.
3. `targeted_rename.py` applies the map to exactly the flagged lines.
4. At the boundary, reconcile **renames-per-map-entry against errors-cleared-per-symbol**—the renamer's JSON and the differ's cleared list, column for column. A mismatch names the exact symbol to open. On the field run the two columns matched exactly, and that match was called the strongest completeness evidence available.
5. Commit per message family; repeat until analyze reports zero errors; resume the category order.

**Routing rule**: only straight member replacements go through the map. `Removed`-bucket symbols and structural errors (Date arithmetic, error handling) stay manual with their rules—the renamer must never be stretched past a rename.

## The categories

Sub-pass structure and pipeline defaults; the ordered rule lists come from `lookup.py category catN` and the tiers within them from `lookup.py tier`. Hazard references are cross-references, not restatements.

| Category | Pipeline default | Structure and traps |
|---|---|---|
| **cat0 strings** | mixed—see the six sub-passes below | The index-shift category; hard rules 4 and 5 both live here |
| **cat1 transform/convert** | regex after census (§9 globals) | `StrComp` sites need `ComparisonOptions.Binary` stated—`String.Compare` defaults case-insensitive; case-insensitive grep only |
| **cat2 arrays** | regex after census (`Append/Insert/Remove/Ubound`) | pass-hazards.md §1 (`.Remove` paren-less forms; Dictionary/Collection are live) and §3 (`.LastIndex` interplay with cat3) |
| **cat3 ListBox/Popup/Combo** | receiver-sensitive (control members; user classes shadow names) | Largest rule set; run before cat2 when the burn-down already forced control members (§3 sidestep). Creates `.RemoveAllRows` that c2r16 would rematch |
| **cat4 database** | receiver-sensitive | RowSet keeps several old member names live; `live_on` first |
| **cat5 Date** | manual pass (phase 6) | Expected to break the build; epoch shift gets its own commit |
| **cat6 error handling** | manual pass (phase 6) | Expected to break the build |
| **cat7 globals/namespaces** | regex after census | `TextColor`/system colors: implicit-`Me` sites; census the color names |
| **cat8 files (FolderItem)** | receiver-sensitive via locate + rename map | `GetSaveInfo` pairs with `FromSaveInfo` on the read side (traps §7) |
| **cat9 graphics/2D** | receiver-sensitive via locate + rename map | The canonical shadowing case: user drawing classes declare their own `DrawRect`/`DrawString`; also `StringShape → TextShape` class-before-member |
| **cat10 Dictionary/JSON/streams** | receiver-sensitive | `.Remove`-family members are live on half their plausible receivers |

**cat0's six sub-passes, each its own commit** (the split is by hazard class, and re-deriving it wastes a run's time):

1. **Byte variants** — c0r2/3/5/7/12, c0r20/21 (regex path; the census names are rare).
2. **Non-shifting base names** — `Len`, `Left`, `Right`, `NthField`, `CountFields` (c0r0/1/4/6/22/24), paren-removers first. None of these shifts an index; `NthField` stays 1-based in API 2.0 and must **not** be decremented.
3. **Compound receivers** — `global_to_method.py` with a spec for the same functions: nested-call arguments convert; illegal receivers get marker + DEFERRED line now.
4. **`InStr`, identifier sources** — sentinel fix and rename in one edit per site (c0r17–c0r19 first, then c0r13–c0r16). PARK any site whose result feeds `Mid` arithmetic.
5. **`InStr`, literal sources** — each needs a local (traps §4) or a deferral; the collision check before every introduced name.
6. **`Mid`** — `mid_to_middle.py`: audit, read the risky and hand-review lists, then `--apply`; **drain the PARKED position-arithmetic sites from sub-pass 4 at this boundary**.

## The drain step

At the boundary that closes a blocking pass, filter `queues.md` for PARKED entries naming that pass and drain them before the commit: convert each (the blocker is gone), or demote it to DEFERRED with its marker placed in that same edit. A small drain rides in the category's commit; a large one is its own commit immediately after. The boundary's oracle run (SKILL.md, **The category boundary**) is the check that nothing stayed parked past its drain: a would-convert site with no PARKED line, or a PARKED line whose pass has closed, is a forgotten site either way.

## Worked example: cat0 sub-pass 2 end to end

Abridged from a real run; commands verbatim, output trimmed.

```
$ python3 $SKILL/scripts/sweep.py "$PROJDIR" --only Len,Left,Right,NthField,CountFields --format json
  ... "suppressed": {} ...            # no user class declares any of the five
$ python3 $SKILL/scripts/apply_rules.py "$PROJDIR" --rules c0r0,c0r1,c0r4,c0r6,c0r22,c0r24
   65  c0r0  Len(s) global form → s.Length (property)
   35  c0r4  Left(s, count) global form → s.Left(count)   [4 suppressed in non-code]
  ...
  total: 152 across 12 file(s)  (dry run, nothing written)
```

Dry counts sane against the worklist, no suppressed surprises—apply:

```
$ python3 $SKILL/scripts/apply_rules.py "$PROJDIR" --rules c0r0,c0r1,c0r4,c0r6,c0r22,c0r24 --apply
```

Then the boundary, verbatim from SKILL.md (analyze into `cp-03-cat0-base.json`, differ against `cp-02-...`, oracle), and the commit with the applier's per-rule table pasted into the body. The oracle's would-convert list at this boundary should name exactly the compound receivers sub-pass 3 will take next—if it names anything else, that is a forgotten site found early, which is the whole point.
