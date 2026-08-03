# JSON output

Pass `--json` to any command. `xojoctl` then writes exactly one JSON document to stdout. It does this always, including when the connection fails, when the command times out, and when you mistype a flag. A consuming script never has to ask whether it got JSON or an error.

All progress text and advisory notes go to stderr. Your parser only ever sees the document.

`--help` and `--version` are the exceptions. They are requests for text, not commands against the IDE, so they print text and exit 0 even alongside `--json`.

```sh
xojoctl analyze --json | jq '.diagnostics[] | select(.severity=="error")'
```

## The document

```json
{
  "schema_version": 1,
  "ok": false,
  "outcome": "project_errors",
  "exit_code": 1,
  "summary": "1 error, 2 warnings",
  "counts": { "errors": 1, "warnings": 2, "script_errors": 0, "open_errors": 0 },
  "diagnostics": [
    {
      "id": "d1",
      "severity": "warning",
      "kind": "project",
      "type": "Code",
      "message": "Left is deprecated.  You should use String.Left instead",
      "location": "Window1.Opening",
      "position": "Window1.Opening, line 1",
      "line": 1,
      "line_source": "position",
      "source": "left(\"asdfsa\", 1",
      "source_is_span": true,
      "origin": "buildError.warnings[0]",
      "raw": { }
    }
  ],
  "notes": [ ],
  "error": null,
  "raw": { "messages": [ ], "dropped": 0, "truncated": false }
}
```

## Stability

`schema_version` increases only when something breaks. New fields, new `notes[].code` values and new `outcome` values arrive without an increase.

Branch on `ok` and `exit_code`. Treat an `outcome` you do not recognize, together with `ok: false`, as a failure.

Everything under `raw` is outside this promise. It is whatever the IDE said, kept exactly, so nothing is lost if Xojo changes its shapes between versions. Pass `--no-raw` to leave it out.

## Three fields that need explaining

The IDE's own shapes are awkward, so `xojoctl` normalizes them.

- **`location` is always a string, or null.** The IDE sends a string inside `buildError` but a `{column, line}` object inside `scriptError`. Any column is moved into `column`.
- **`line` comes from the human `position` string.** It is null when `xojoctl` cannot establish it. It is never 0 and never a guess. `line_source` records where the number came from.
- **`source_is_span` marks `source` as the exact region the IDE highlights.** That region can be incomplete on purpose. Note the unclosed parenthesis in the example above. Use it to draw a caret. Do not parse it.

## What `error` means

`error` stays null when your project has errors. `error` means `xojoctl` failed to get an answer at all. Project diagnostics **are** an answer.

## Exit codes

| Code | Meaning |
|---|---|
| 0 | Success, including warnings with no errors |
| 1 | The project failed. Errors were reported, or warnings under `-W`, or a `missingFiles` configuration problem, or an empty response that did nothing |
| 2 | Could not connect, or the connection or protocol failed part way through |
| 3 | Timed out waiting for a reply |
| 4 | The result is incomplete. The reply could not be interpreted, or a build's completion went unconfirmed |
| 5 | The IDE rejected the script `xojoctl` sent. This is a bug in `xojoctl` |
| 6 | No project is open. The IDE answered, but there is nothing to act on |
| 64 | You used a flag or value the tool does not accept |

Warnings alone exit 0. Pass `-W` or `--warnings-as-errors` to make them exit 1.

Dropped messages never change the exit code. They appear as a `result_incomplete` note and as `raw.truncated: true`, so a weakened verdict is flagged instead of passing silently.
