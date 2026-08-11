# Agent Skill: xojo-lint

A checker and formatter for Xojo projects saved in text format. It validates the structure of every `.xojo_*` file and repairs safe serialization details, so an agent or a hook can catch a broken project file before the Xojo IDE sees it. It has the same basic split as Ruff: `check` reports problems, `format` rewrites what is safe to rewrite.

It needs Python 3.9 or later and nothing else.

```console
$ python3 scripts/xojo_lint.py check --all path/to/project
$ python3 scripts/xojo_lint.py format --check path/to/project
$ python3 scripts/xojo_lint.py format path/to/project
```

## What `check` finds

The checker validates UTF-8 text containers, `#tag` and designer `Begin`/`End` structure, project manifest rows and item relationships, companion paths, resource chunk boundaries, UI-state records, and library archives. It reports three severities:

- **error** — the file breaks its format. Errors always make the run fail.
- **warning** — the file is unusual but usable, for example a UTF-8 byte order mark the IDE never writes. Warnings make the run fail only with `--warnings-as-errors`.
- **notice** — a nit that never makes the run fail, for example a missing line break at the end of a file. Hide notices with `--no-notices`.

Output uses the editor-friendly `path:line:column: severity CODE message` form. Diagnostic codes are grouped by container: `XJC` common text, `XJT` tagged regions, `XJB` designer blocks, `XJP` project manifests, `XJR` resources, `XJU` UI state, `XJL` libraries, and `XJF` formatting.

Unknown properties, keys, and tag kinds are accepted, so a newer IDE can extend the formats without this tool calling that corruption. A project version newer than the tool's knowledge gets a warning, not a failure. Xojo Binary Project and Xojo XML Project files are not parsed: the tool skips them, and names them only with `--warn-unknown`.

## What `format` changes

The formatter is deliberately conservative. It normalizes serializer tag case and nesting, preserves Xojo's special `#Tag Instance` spelling, repairs missing minimum source indentation, removes whitespace around manifest keys, and adds a missing line break at the end of a file (skip that with `--final-newline preserve`). It does not reorder properties and does not rewrite Xojo expressions, identifiers, comments, or string literals. Byte order marks and line endings are preserved unless you override them. Invalid files are never rewritten.

## As a pre-commit hook

`check` and `format --check` are quiet on success and exit nonzero when something needs attention, so they drop into a git hook directly. `scripts/pre-commit.sample` is a ready-to-use hook that lints the staged `.xojo_*` files:

```sh
cp scripts/pre-commit.sample /path/to/project/.git/hooks/pre-commit
chmod +x /path/to/project/.git/hooks/pre-commit
```

The `XOJO_LINT` default at the top of the hook finds `xojo_lint.py` where Claude Code installs the plugin. For any other install, Codex included, set the variable to the real path of the script.

## Tests

```console
$ python3 scripts/test_xojo_lint.py
```
