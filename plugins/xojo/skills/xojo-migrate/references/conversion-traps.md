# Conversion traps: the changes a rename does not fix

Read this before touching any string, array, date, or error-handling code. Every trap here compiles cleanly after a naive rename and then misbehaves at runtime. A regex or rule that changes a *name* but leaves a now-wrong *index* or *comparison* is worse than doing nothing.

Throughout, API 1.0 is the older generation, which Xojo's own documentation calls "pre-API 2.0".

## 1. Index-base shifts: what shifts, and what doesn't

Some API 1.0 functions are 1-based and their API 2.0 forms are 0-based; others do not change at all. Never assume; check this table.

| Conversion | First element | Shift? |
|---|---|---|
| `Mid -> Middle` | 1 -> 0 | **Yes**: subtract 1 from the start. The length argument is unchanged. |
| `InStr -> IndexOf` | 1-based; 0 if absent | **Yes**: result now 0-based; not-found is now `-1`. |
| `IdxField(n) -> ColumnAt(n)` | 1 -> 0 | **Yes**: subtract 1. |
| `FolderItem.Item(n) -> ChildAt(n)` | 1 -> 0 | **Yes**: subtract 1; better, rewrite the loop bounds to `0 To f.Count - 1`. |
| `FolderItem.TrueItem(n) -> ChildAt(n, False)` | 1 -> 0 | **Yes**: subtract 1, *and* pass `followAlias := False`. `ChildAt` follows aliases by default; `TrueItem` never did. Dropping the second argument silently changes alias handling. |
| `Ubound -> LastIndex` | both 0-based | No: identical value. |
| Array `Insert/Remove -> AddAt/RemoveAt` | both 0-based | No: pass the index unchanged. |
| ListBox row/column members | both 0-based | No. |
| `NthField` field number | 1 -> 1 | No: stays 1-based. |
| `Left / Right`, and `Mid`'s length argument | counts, not indexes | No. |
| `TotalSeconds -> SecondsFrom1970` | 1904 -> 1970 epoch | **Yes**: a 66-year epoch shift (see section 5). |

### The decrement technique

When converting a 1-based call whose start is a variable, wrap the captured argument and append `- 1`, then simplify by hand:

```
Mid(s, p)        ->  s.Middle((p) - 1)
Mid(line, p + 1) ->  line.Middle((p + 1) - 1)   ' simplify by hand -> line.Middle(p)
```

For a literal start, convert the literal directly: `Mid(s, 1)` -> `s.Middle(0)`, `Mid(s, 2)` -> `s.Middle(1)`, and so on.

### `Mid` was forgiving about a start below 1; `Middle` is not

This is what makes the decrement dangerous rather than merely fiddly. API 1.0 `Mid` clamps a start position below 1, so `Mid(s, 0, 1)` returns the *first* character and a loop written `For i = 0 To n ... Mid(s, i, 1)` was working code. Apply the decrement mechanically and the first iteration becomes `s.Middle(-1, 1)`, which is not the same call.

So the decrement is not complete until you have checked **the lower bound of whatever feeds the start argument**:

```
For i = 0 To s.Length - 1          ' 0-based loop over a 1-based function: legal API 1.0
  c = Mid(s, i, 1)                 ' i = 0 clamps to the first character
Next
' Converting the call alone yields s.Middle((i) - 1, 1) -> Middle(-1, 1) at i = 0.
' The loop bound is the thing that has to change, not just the call.
```

Audit every converted `Mid` whose start is a variable rather than a literal: find where that variable originates and confirm it is `>= 1` in API 1.0 terms. A loop that already started at 1 converts cleanly; one that started at 0 was relying on the clamp.

At real-project scale this audit is scriptable, and should be: for each site, walk outward to the enclosing `For` statements, take the bound (or origin) that feeds the start variable, and group the sites by that bound. Three hundred sites collapse to a dozen distinct bounds, "any bound below 1?" becomes a one-screen read, and the only shape left for a human is a bound fed by a parameter, which is answered at its call sites.

## 2. The not-found sentinel (`InStr` -> `IndexOf`)

`InStr` returns `0` when the substring is absent. `IndexOf` returns `-1` when absent, and a hit at the **first character** returns `0`, which the old `> 0` test would wrongly reject. This is the single most dangerous trap in the whole migration because the broken code still compiles and only fails on first-character matches.

Fix every comparison **before** renaming the function:

| API 1.0 test | API 2.0 test |
|---|---|
| `InStr(s, x) > 0` (found) | `s.IndexOf(x) >= 0` (also written `> -1`) |
| `InStr(s, x) = 0` (not found) | `s.IndexOf(x) = -1` (or `< 0`) |
| `InStr(s, x) >= 1` | `s.IndexOf(x) >= 0` |
| `InStr(s, x) = 1` (starts with) | `s.IndexOf(x) = 0` |

Recommended order per occurrence: (1) inventory every `InStr` call; (2) decide how each result is consumed; (3) fix the consumer; (4) only then rename.

**The optional `start` argument shifts too.** `InStr(start, source, find)` is 1-based on both ends: the *result* and the *start position*. So the three-arg form needs two corrections, not one:

```
p = InStr(5, s, "x")        ' start at 1-based char 5, result 1-based
p = s.IndexOf(4, "x")       ' start is now 0-based (5 - 1), result now 0-based
```

The bundled rules (`c0r14`, `c0r16`, and the `InStrB` pair) already emit the `(start) - 1` decrement; simplify it by hand. The trap is doing it *yourself* and forgetting the start, or applying the rule and then decrementing again.

### What does *not* change: case sensitivity

The index base and the sentinel are the whole of the behavioral change. Case matching is unaffected, in both families—worth stating, because the asymmetry between them is exactly where a reader expects a trap:

| API 1.0 | API 2.0 | Case |
|---|---|---|
| `InStr` | `String.IndexOf` | Both **case-insensitive** by default. `IndexOf` takes an optional `ComparisonOptions` to opt into case sensitivity; passing nothing preserves API 1.0 behavior. |
| `InStrB` | `String.IndexOfBytes` | Both **case-sensitive** (byte-level). |

So neither rename changes what matches. Do not "helpfully" add a `ComparisonOptions` argument during conversion: that is a behavior change disguised as a migration.

## 3. The cross-statement double-decrement trap

When an `InStr` result flows into another call you are *also* making 0-based, the two decrements cancel; do **not** apply both:

```
p = InStr(s, ":") : rest = Mid(s, p + 1)     ' API 1.0
p = s.IndexOf(":") : rest = s.Middle(p + 1)  ' API 2.0: p is already 0-based; do NOT also subtract 1
```

Single-line rules cannot see across statements, so after any pass that touches `InStr`/`Mid`/`IdxField`, audit places where one converted result feeds another converted call, and simplify leftover `(...) - 1` wrappers while you are there.

## 4. The method-receiver rule (type-blind member renames)

Two related hazards:

**Global-to-method conversions.** Most global string functions become methods on `String` (`Trim(s)` -> `s.Trim`). The bundled regexes only capture a plain variable or dotted property path as the receiver. That is deliberate, and the reason is a *language* constraint, not a regex limitation:

> **Xojo has no member access on a string literal or on a parenthesized expression.** `"0123456789".IndexOf(c)` and `("00" + Hex(r)).Right(2)` are **syntax errors**. A receiver must be an identifier, or a chain of member accesses and calls off one (`s.Trim.Uppercase`, `f.Child("x").Name`).

So when a rule skips a call because its receiver argument is a literal or a compound expression, there are exactly **two** outcomes. Writing the method form by hand is not one of them—it does not compile:

```
result = Trim("  " + name)        ' skipped by the regex: expression argument

' Option A -- introduce a local, then use the method form:
Var tmp As String = "  " + name
result = tmp.Trim                 ' receiver is a plain identifier

' Option B -- leave the deprecated global in place (still compiles, warns):
result = Trim("  " + name)
```

**Which to choose.** Default to **Option B** during the mechanical passes, and say so in the commit message. Option A is correct code, but each instance adds a variable and a line to a diff that is otherwise pure renames; done at scale it stops being a migration and becomes a refactor the reviewer cannot skim. The threshold that matters is *density*: a handful of locals in a method reads fine, but a character-set idiom like `InStr("0123456789", c)` repeated across dozens of methods will introduce a local in every one of them. Convert those in their own commit, after the renames, or leave them deprecated—marked at the site with a `#Pragma Warning` and listed in the final report. The marker is not optional and the report does not replace it; when a method repeats the same deferral, one marker at the top of that method covering all of its sites is enough. See "Anything left unconverted gets a marker at the site" in `SKILL.md` phase 2.

Prefer **Option A** when the expression is already assigned to something nearby (reuse the existing variable, no new line), or when the deprecated global is in the `Removed` bucket and therefore does not compile anyway.

**Check the name before introducing the local.** The natural name for the new variable is often already taken in exactly the methods that need it—the same concept, named twice: a method testing membership in a character set plausibly already has a counter named for that very concept, and the new local then collides with it. Before declaring, check the method's parameters, every `Dim`/`Var`/`Static`, and every `For` counter. On a real migration the first automated pass silently retargeted an existing counter's increment in three methods; the compiler said nothing, and only reading the diff caught it.

**A member call may have no receiver at all.** This is the other half of the receiver rule, and it is the one that gets missed. In Xojo, calling your own instance's member needs no receiver: `Invalidate` and `Self.Invalidate` are the same call, and older code writes the first.

```
#tag Event
  Sub Activated() Handles Activated
    invalidate            ' a DesktopWindow calling its own member

Sub Style(Assigns n As Integer)
  if (mStyle <> n) then
    mStyle = n
    invalidate(false)     ' a Canvas subclass, with an argument
```

Every member rule in this skill is anchored on a literal dot, so **none of them can see this form**—150 of the 264 rules. On one project a `.Invalidate` rule matched roughly one occurrence in seven. Two consequences:

1. **A rule reporting zero matches is not evidence of completion.** It may be structurally unable to match the shape your project uses. This is why phase 8 requires `scripts/sweep.py`, which searches bare names and reports receiverless member calls as its headline section.
2. **The receiverless form is *harder* to resolve, not easier.** There is no receiver token on the line, so the type comes from the enclosing class—the file's `Inherits` line, or the `Begin <Class>` header of the window the code lives in. Still deterministic, just not local.

**Member renames are type-blind.** The same member name can be deprecated on several classes with *different* replacements, or deprecated on one class and valid API 2.0 on another. Before renaming any `.Member`, find the receiver's declared type (`Var x As ...`, parameter declarations, the control's class) and confirm which replacement applies. The recurring offenders:

| Member | Receiver -> correct replacement |
|---|---|
| `.Append` | array -> `.Add`; `JSONItem` -> `.Add`; `Group2D` -> `.AddObject`; `FigureShape` -> `.AddCurve`; `TextOutputStream.Append` (shared) -> `.Open` |
| `.Insert` | array -> `.AddAt`; `Group2D` -> `.AddObjectAt`; `FigureShape` -> `.AddCurveAt`; `JSONItem` -> `.AddAt` |
| `.Remove` | array -> `.RemoveAt`; `Group2D` -> `.RemoveObjectAt`; `FigureShape` -> `.RemoveCurveAt` |
| `.RemoveRow` | ListBox -> `.RemoveRowAt`; but `RowSet.RemoveRow` is **valid API 2.0** (it replaces `RecordSet.DeleteRecord`); never sweep this rename project-wide, and never after the RecordSet pass has introduced `RowSet.RemoveRow`. |
| `.AddRow` | array -> `.Add`; ListBox/DesktopListBox `.AddRow` is valid API 2.0. **RowSet has no `AddRow`**: inserting a row is `db.AddRow(tableName, row As DatabaseRow)` on the *Database*, which is what `InsertRecord` becomes. A `.AddRow` whose receiver is a RowSet is a mistake, not already-converted code. |
| `.ColumnType` | ListBox -> `.ColumnTypeAt`; but `RowSet.ColumnType(index)` is **valid API 2.0** and has no `...At` form; renaming it is a compile error. |

## 5. Date -> DateTime: not a rename

`DateTime` differs from `Date` in three ways at once, so this category is almost entirely manual:

1. **Immutable.** No setting `.Year`/`.Month`/`.Day` on an existing instance. Mutation code becomes "construct a new DateTime from the changed parts" (`New DateTime(year, month, day, ...)`) or arithmetic via `DateInterval` (`d = d + New DateInterval(0, 1, 0)` adds a month).
2. **Different construction.** `New Date` (now) -> `DateTime.Now`. Building a date from parts uses the multi-argument constructor, optionally with a `TimeZone`. `ParseDate(s, d)` -> **`DateTime.FromString(s, Locale.Current)`** inside a `Try/Catch` (it throws on bad input instead of returning False).

   **The locale argument is not optional in practice.** `ParseDate` parsed the user's regional format. `DateTime.FromString` *without* a locale accepts only SQLDate (`YYYY-MM-DD`) and SQLDateTime, so Xojo's own `ParseDate` sample, `ParseDate("12/31/2013", d)`, becomes a call that raises a Parse Error on every invocation. The `Try/Catch` you just added then swallows it as "bad input" and a working date-entry field silently rejects every valid date. Pass `Locale.Current` to preserve the old behavior, or a specific locale if the string format is fixed.
3. **Different epoch.** `Date.TotalSeconds` counts from 1904; `DateTime.SecondsFrom1970` counts from 1970, a 66-year difference. Any stored or transmitted TotalSeconds value (files, databases, preferences) must be re-based, not just renamed. Search for stored uses before converting.

Formatting also changes, and the two directions use different calls; do not route formatting through the parser:

| API 1.0 | API 2.0 |
|---|---|
| `d.ShortDate` (format a date) | `d.ToString(DateTime.FormatStyles.Short, DateTime.FormatStyles.None)` |
| `d.LongDate` | `d.ToString(DateTime.FormatStyles.Long, DateTime.FormatStyles.None)` |
| `d.ShortTime` | `d.ToString(DateTime.FormatStyles.None, DateTime.FormatStyles.Short)` |
| `d.LongTime` | `d.ToString(DateTime.FormatStyles.None, DateTime.FormatStyles.Long)` |
| `ParseDate(s, d)` (parse a string) | `DateTime.FromString(s, Locale.Current)` |

`ToString` formats and takes a style pair (date style, time style); `FromString` parses and takes a locale. Mapping a `ShortDate` read onto `FromString` is a common mis-conversion and fails at runtime, not compile time.

## 6. Error codes -> exceptions

API 2.0 replaces error-flag checks with exceptions. The regex rules in the error-handling category only *locate* occurrences; the rewrite is structural:

```
' API 1.0
Dim rs As RecordSet = db.SQLSelect("SELECT ...")
If db.Error Then
  MsgBox db.ErrorMessage
End If

' API 2.0
Try
  Var rs As RowSet = db.SelectSQL("SELECT ...")
Catch e As DatabaseException
  MessageBox(e.Message)
End Try
```

Notes:

- `db.Error` / `db.ErrorCode` / `db.ErrorMessage` checks -> `Catch e As DatabaseException` with `e.ErrorNumber` / `e.Message`. Remove the old checks entirely; leaving them is dead code that hides the fact conversion happened.
- Scope: a variable declared inside `Try` is not visible after `End Try`; declare it before the `Try` if used later.
- Socket and stream classes: `Error` **events** change signature (they now receive an exception parameter); update the event definitions, not just handler bodies.
- Expect compile errors during this pass. That is normal and useful: the compiler is pinpointing the remaining manual work.

### 6a. The silent half: calls that returned `Nil` instead of setting a flag

Section 6 covers the *explicit* form, where the code checks `db.Error` and you can see the check. The more common form has no check to find:

> **An API 1.0 call that signaled failure by its return value, and an API 2.0 call that signals failure by raising, are not a rename.** Renaming compiles, and then does two wrong things at once.

```
' API 1.0 -- returns Nil on failure
Dim b As BinaryStream = f.CreateBinaryFile("")
If b <> Nil Then
  b.Write data
End If

' API 2.0 -- RAISES IOException on failure
Try
  Var b As BinaryStream = BinaryStream.Create(f, True)
  b.Write data
Catch e As IOException
  ' handle it -- this path did not exist before
End Try
```

Carry the old shape across and both halves break: the `If b <> Nil Then` guard becomes **dead code** (the call either succeeded or already threw), *and* the exception is **unhandled**, so a failure that used to be a quiet no-op now takes down the app. The guard being dead is what makes this hard to spot in review—the code looks defensive and reads as fine.

The pattern covers more than one call. Check each of these for a `Nil` guard:

| API 1.0 (returns Nil / False on failure) | API 2.0 (raises) |
|---|---|
| `FolderItem.CreateBinaryFile` | `BinaryStream.Create(f, overwrite)` — `IOException` |
| `FolderItem.CreateTextFile` | `TextOutputStream.Create(f)` — `IOException` |
| `FolderItem.Delete` (sets `LastErrorCode`) | `FolderItem.Remove` — `IOException` (rule `c6r1`) |
| `FolderItem.OpenAsBinaryFile` | `BinaryStream.Open(f, write)` — `IOException` |
| anything followed by a `LastErrorCode` check | the matching `Try` / `Catch` |

So the conversion is three edits, not one: rename the call, **delete the now-dead `Nil`/error check**, and wrap in `Try`/`Catch`. Leaving the check is not harmless conservatism—it is dead code asserting a safety that is gone.

## 7. FolderItem construction (`GetFolderItem` and friends)

The `Get*FolderItem` globals become constructors, shared methods, or dialogs:

| API 1.0 | API 2.0 |
|---|---|
| `GetFolderItem(path)` | `New FolderItem(path, pathMode, followAlias)` |
| `GetTrueFolderItem(path)` | `New FolderItem(path, pathMode, False)`, the same constructor, with `followAlias` explicitly `False` |
| `GetTemporaryFolderItem` | `FolderItem.TemporaryFile` |
| `GetOpenFolderItem(...)` | `FolderItem.ShowOpenFileDialog` |
| `GetSaveFolderItem(...)` | `FolderItem.ShowSaveFileDialog` |
| `Volume(n)` | `FolderItem.DriveAt(n)` |

The trap: **path-mode defaults and relative paths.** `GetFolderItem` with a relative path resolves it relative to the running application, and its second argument used integer path-type constants; `New FolderItem(path)` defaults to `FolderItem.PathModes.Native` and behavior for a non-absolute path is not a guaranteed match. For each call, look at what the path actually is:

- Absolute native path -> `New FolderItem(path)` is a straight swap.
- Relative name like `"data.txt"` -> decide what the code *meant*, usually a file beside the app: `App.ExecutableFile.Parent.Child("data.txt")` or a `SpecialFolder` location. Do not blind-convert; confirm with the user.
- URL/shell path constants -> the matching `FolderItem.PathModes` enum value. The whole family, because this is an integer-constant-to-enum move and the constants travel with every call you convert:

  | API 1.0 constant | API 2.0 |
  |---|---|
  | `FolderItem.PathTypeNative` | `FolderItem.PathModes.Native` |
  | `FolderItem.PathTypeShell` | `FolderItem.PathModes.Shell` |
  | `FolderItem.PathTypeURL` | `FolderItem.PathModes.URL` |
  | `FolderItem.PathTypeAbsolute` | **nothing** — see below |

  `PathTypeAbsolute` is the trap, and it is both the API 1.0 **default** and therefore the one most code passes. `PathModes` has `Native`, `Shell` and `URL` only: there is no `Absolute`, because the HFS `AbsolutePath` it selected is itself Removed. Do not map it to `PathModes.Native` reflexively—on macOS those are different paths. Decide per call site what the path actually was.

**Stored save-info data is none of the above.** The classic persistence idiom saves `GetSaveInfo` bytes (often base64-encoded) and reads them back with `GetRelative`—or, off-book but common, by feeding the decoded bytes to `GetFolderItem`. Save-info data is opaque alias data, not a path of any mode, so when a constructor argument traces back to stored data the API 2.0 reader is `FolderItem.FromSaveInfo` (shared; returns Nil when the data cannot be resolved), never `New FolderItem(data, PathModes.Native)`. The wrong version compiles and fails only at runtime, on the user's saved documents.

Also note `FolderItem.LastErrorCode` checks become `Try/Catch ... As IOException` (same structural pattern as section 6).

## 8. Matches inside strings and comments

Neither the scanner nor any regex distinguishes code from string literals and comments. `"Press Mid button"` in a literal will match a `Mid` pattern. Always look at the line before editing; skip literals/comments unless the text itself should change (rare).

A comment match is cosmetic. **A string-literal match can be a live bug**, because some of these tokens are also the syntax of another language embedded in the string:

| Literal | Rule that matches | Damage |
|---|---|---|
| `"SELECT * FROM a LEFT JOIN (SELECT ...)"` | `Join(` → `String.FromArray(` | Becomes `LEFT String.FromArray(SELECT ...)`. **Compiles**, then fails at runtime as a SQL syntax error, in exactly the database code this skill spends a whole category converting. |
| `"color: rgb(255,0,0)"` | `RGB(` → `Color.RGB(` | Becomes `"color: Color.RGB(255,0,0)"`, shipping broken CSS to an HTMLViewer. Note `rgba(` does *not* match, so a stylesheet ends up half-rewritten and harder to spot. |
| `"Set the Date field"` | `Date` → `DateTime` | Cosmetic, but it churns the diff and hides the real changes. |

The pattern to watch for: a rule whose old name is a common word in **SQL, CSS, HTML, or a shell command** that your project builds as a string.

## 9. Matches inside declarations

Six global rules rewrite the identifier itself rather than a member access: `ShowURL`, `Speak`, `Volume`, `VolumeCount`, `ScreenCount`, `IsDarkMode`. Their lookbehind stops `obj.Speak(`, but nothing stops a *declaration*, and in a text-format Xojo project a method's declaration and its call sites are in the same file you are editing:

```
Sub Speak(phrase As String)          ' becomes  Sub System.Speak(phrase As String)
Private VolumeCount As Integer       ' becomes  Private FolderItem.DriveCount As Integer
Var Volume(15) As Double             ' becomes  Var FolderItem.DriveAt(15) As Double
```

All syntax errors. Two extra wrinkles: Xojo indexes arrays with parentheses, so `Volume(chan) = 0.75` matches the `Volume(` rule as if it were a call; and a project with its own pre-2020 `IsDarkMode` helper will silently start calling the framework's instead, which compiles and may even behave differently.

Before applying any of these six, check whether the project defines a method, property, or array of that name.
