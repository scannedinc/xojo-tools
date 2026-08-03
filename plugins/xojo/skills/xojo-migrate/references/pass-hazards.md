# Pass hazards: what the rules cannot see, and what they over-match

Three things that decide whether a category pass is finished, pulled out of `SKILL.md` so the workflow there stays readable. Read this once before the first category pass; it does not change per category.

The through-line: **a rule's match count tells you almost nothing on its own.** It can be far too high, because member patterns are type-blind and match receivers the rule was never aimed at. It can be far too low, because whole call shapes are invisible to every pattern here. And it can be wrong for a third reason—the matches may be code an *earlier* pass of your own created.

## 1. Zero matches is not completion

There are three such forms, and none of them is "skipped with a caveat"—the patterns never consider them at all, so **a rule reporting zero remaining matches is not evidence that the symbol is converted**:

1. **Receiverless member calls.** `Invalidate` means `Self.Invalidate`, and 150 of the 264 rules are anchored on a literal dot.
2. **Paren-less statement calls.** `msgbox "text"`, `ShowURL "http://..."`. Most rules now handle these; any rule still carrying `(?=\s*\()` does not.
3. **Line continuations.** No rule here matches across a line break—the patterns are single-line—and Xojo continues a statement with a trailing `_`:

```
result = ReplaceAll( source, _             ' the rule's find never reaches this
                     "old", "new" )
MsgBox "Could not open " + _
       f.Name
```


See phase 8 in `SKILL.md`: `scripts/sweep.py` is the pass that sees all three, and it is required before the migration can be called finished.

### Your own receiver census inherits this blind spot

The usual way to resolve a type-blind member rule is to grep the project for `<receiver>.<Member>` and tally who the receivers are. Written the obvious way, that grep is dot-anchored too:

```
\b[A-Za-z_][A-Za-z0-9_.]*\.Count       ' cannot match a receiver ending in ')'
```

It cannot see `Dictionary(storage.ObjectValue).Count`, `values(i).Count`, or any other cast, call, or indexed receiver—all of which are legal Xojo (see hard rule 3). A census built on that pattern will report "no Dictionary receivers in this project" and be confidently wrong, and because a census feels like verification, the wrong answer then gets written into a commit message. This happened on a real migration, in the checking step rather than the converting step.

Allow a receiver to end in `)`, and remember that a census answers *who declares this name*, not *who receives it*. A project that declares its own `Border` property does not thereby make every `.Border` in the file that property; several were `CurveShape.Border` on the run where this was missed. Open the sites.

## 2. A large match count is not a large amount of work

**Expect most matches in this tier to be wrong.** That is not pessimism, it is the measured shape of a real desktop migration. Matches against matches that were actually correct to apply:

| Rule | Matched | Correct to apply | The rest were |
|---|---|---|---|
| `c3r31` `.LastIndex → .LastAddedRowIndex` | hundreds | a handful | array `LastIndex` — mostly created by the *preceding* array commit |
| `c9r3` `.FillRect → .FillRectangle` | hundreds | a handful | a user class with its own `FillRect` |
| `c9r6` `.ForeColor → .DrawingColor` | dozens | about a fifth | the same user class's own `ForeColor` |
| `c10r15` `.Value(i) → .ValueAt(i)` | dozens | **none** | Dictionary, DesktopCheckBox, user class |
| `c2r13` `.AddRow → .Add` | dozens | **none** | DesktopPopupMenu / DesktopListBox — live API 2 |
| `c10r1` `.Count → .KeyCount` | dozens | one | user class, FolderItem, DesktopToolbar |
| `c2r3` `.Remove(i) → .RemoveAt(i)` | a dozen or so | **none** | Dictionary, DesktopMenuItem, DesktopToolbar |

Read the ratios, not the numbers: a rule matching ninety lines and converting twenty is the system **working**. Report the ratio to the user rather than the match count, and never treat a large match count as a large amount of work—the two are barely related. Note the top row: a rule can be mostly false-positive *because of what an earlier category did*, which is the ordering hazard from step 3 showing up in the numbers.

One user class defining `ForeColor`, `FillRect` and `DrawString` accounted for three of these rows on its own. When a rule's matches cluster in one file, resolve the receiver once for that file rather than per line.

## 3. One pass creates what the next pass matches

#### One pass creates what the next pass matches

The recurring shape: rule A *produces* a name that rule B's regex then matches, even though B's receiver is a different class. Because A ran first, B is no longer looking at the code the inventory described—it is looking at your own output. Three known instances, all of which the category order in step 5 either handles or (for the second) actively causes:

- **ListBox `.RemoveRow → .RemoveRowAt` (c3r6) before RecordSet `.DeleteRecord → .RemoveRow` (c4r23).** The second rule *creates* `RowSet.RemoveRow`, which is correct API 2; run it first and the ListBox rule rewrites it to a `RemoveRowAt` that RowSet does not have. The category order already does this; do not reorder those two.
- **Arrays `Ubound(x) → x.LastIndex` (cat2) vs ListBox `.LastIndex → .LastAddedRowIndex` (c3r31).** This one the documented order gets *wrong*. cat2 runs first and can create hundreds of fresh array `.LastIndex` reads; c3r31 is a bare `\.LastIndex\b` sweep, so on the very next category it rewrites array reads that are already correct API 2. Array `.LastIndex` is live, so nothing catches it at compile time. **Either run c3r31 before the array pass, or resolve the receiver on every one of its matches**—and running it first only shrinks the population to `.LastIndex` reads that were in the file already, it does not make them all ListBoxes. Resolve receivers either way; c3r31 is `medium` for exactly this reason.
- **ListBox `.DeleteAllRows → .RemoveAllRows` (c3r7) vs array `.RemoveAllRows → .RemoveAll` (c2r16).** Same shape in the other direction: c3r7 creates `RemoveAllRows` on popup menus and list boxes, where it is correct, and a later array sweep matches it.

The general check, at the end of every category: **for each rule you just applied, ask whether its *replacement* text is something a later category's `find` will match.** If it is, that later rule's matches are no longer a to-do list—they are partly your own work, and every one needs its receiver resolved.

