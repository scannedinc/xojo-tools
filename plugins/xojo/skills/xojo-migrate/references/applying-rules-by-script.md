# Applying rules with something other than the Xojo IDE

You need this only if you are driving the rules from a script, `sed`, or an editor's find/replace. The normal workflow applies them in the Xojo IDE's Find panel, which is the dialect they are written for, and then none of this matters.

Three ways to get it wrong, all of which damage the user's source rather than failing loudly: not translating the backreference dialect, running a substitution with a rule that has no substitution to make, and running a rule over the whole file instead of over its code.

## Run the rules over code, not over the file

A `.xojo_code` or `.xojo_window` file is mostly not code. Layout metadata in `Begin <Class>` … `End` blocks, `#tag Note` prose, `#tag ViewBehavior` property tables, comments and string literals all sit in the same file as the methods, and a bare regex cannot tell them apart. On one real project the rule for the `TextColor` system color matched dozens of lines, and **all but a handful were `TextColor = &c00000000` control properties inside `Begin` blocks**. The ratio of metadata to code ran better than ten to one.

`scan.py` reports both numbers for exactly this reason (`4 in code (66 raw)`), but that segmentation lives in the scanner and a rule cannot inherit it. A driver must do the same thing before matching. Reuse `code_only()` from `scripts/scan.py`—it blanks non-code regions while preserving length and line count, so match offsets still map back to the original line:

```python
import sys, importlib.util
spec = importlib.util.spec_from_file_location("scan", SKILL / "scripts/scan.py")
scan = importlib.util.module_from_spec(spec); spec.loader.exec_module(scan)

masked = scan.code_only(path.read_text())     # same length as the original
for m in rx.finditer(masked):
    ...                                        # offsets are valid in both
```

At minimum, skip lines inside `Begin`…`End` blocks, lines inside a `#tag Note` or `#tag ViewBehavior`, and comment-only lines. Editing a `Begin` block corrupts the IDE's stored layout; it is not a harmless false positive.

## The regex dialect

Every `find`/`replace` in this skill is written for the **Xojo IDE's Find panel** with "Use RegEx" checked. That means:

- **Backreferences are `$1`, `$2`** — not `\1`. 54 of the 264 rules use them.
- **Case-insensitivity is a checkbox, not part of the pattern.** Xojo identifiers are case-insensitive, so the patterns assume an external ignore-case flag. Only one rule (`c6r7`) carries an inline `(?i)`.
- Matching is single-line; no pattern spans a line break.

**If you apply a rule with anything other than the IDE**—a script, `sed`, an editor's find/replace—you must translate. In Python: `re.sub` needs `\1`-style backreferences and `re.IGNORECASE`:

```python
python_replace = re.sub(r"\$(\d)", r"\\\1", rule["replace"])
re.compile(rule["find"], re.IGNORECASE).sub(python_replace, text)
```

Skipping that translation writes a literal `$1` into the user's source: `Len(name)` becomes `$1.Length`. Every rule shipped here is machine-checked against its own bundled examples using exactly this translation, so the dialect above is tested rather than asserted.

### Filter on `applies` before you iterate

**Never drive a loop over every rule's `find`.** Rules whose `conf` is `manual-only` are *locate-only*: they carry a `find` to help you spot the shape, and their `replace` is empty because there is no mechanical conversion. Applied by a driver that does not check, they do damage no error message explains:

- An **empty `find`** matches at every character offset.
- An **empty `replace` on a live `find` deletes text.** `c3r54` ships `find: "\.Text\b"` with no replacement, so a blind pass turns `nameField.Text = nameField.Text.Left(5)` into `nameField = nameField.Left(5)`. `c9r11` (`\.Pixel\s*\(`) is the same shape. Both compile in some contexts, which is the worst case.

Every rule therefore carries a boolean **`applies`**: true when `find` and `replace` are a usable substitution pair, false for locate-only rules. Gate on it, and prefer it over testing the strings:

```python
for rule in rules:
    if not rule["applies"]:
        continue            # locate-only: read the `manual` note, convert by hand
    ...
```

