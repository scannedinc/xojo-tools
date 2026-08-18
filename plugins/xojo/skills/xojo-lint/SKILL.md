---
name: xojo-lint
description: >-
  Validate, lint, and conservatively format the files of a Xojo project in
  text format (.xojo_project, .xojo_code, .xojo_window, and the other .xojo_*
  extensions). Use after creating or editing any Xojo project file, when the
  user asks to lint, check, validate, format, or clean up a Xojo project, and
  when the user wants a pre-commit check for a Xojo project.
disable-model-invocation: false
---

# Xojo Lint

`scripts/xojo_lint.py` validates and formats Xojo project files. It needs only Python 3.9 or later and the standard library. Run it from the folder of this skill, or give the full path to the script.

## Commands

After you create or edit files in a Xojo project, run both checks:

```sh
python3 scripts/xojo_lint.py check --all PATH
python3 scripts/xojo_lint.py format --check PATH
```

Both commands are silent and exit 0 when the project is clean. `PATH` is a project folder or one file; it defaults to the current directory.

If `format --check` reports files, inspect the changes, then apply them:

```sh
python3 scripts/xojo_lint.py format --diff PATH
python3 scripts/xojo_lint.py format PATH
```

The formatter only changes serialization details it can identify safely: tag case and nesting, whitespace around manifest keys, missing minimum indentation inside source tags, and a missing line break at the end of a file -- except in `.xojo_script`, which Xojo writes both ways, so use `--final-newline add` to force one there. It does not reorder properties and does not rewrite Xojo expressions, identifiers, comments, or string literals, including the trailing whitespace of a manifest value. Never format a project the user has designated read-only.

## Reading the output

Each diagnostic is one line: `path:line:column: severity CODE message`. There are three severities:

- **error** — the file breaks its format. Errors always fail the run.
- **warning** — the file is unusual but usable. Warnings fail the run only with `--warnings-as-errors`.
- **notice** — a nit, for example a missing final line break. Notices never fail the run. Hide them with `--no-notices`.

`check --all` enables all optional checks, currently `--warn-unknown` for unknown `.xojo_*` containers and tag kinds plus `--check-paths` for external image and data assets. It does not enable `--warnings-as-errors`; add that separately when warnings must fail the run.

Unknown properties, keys, and tag kinds are accepted for forward compatibility: a newer IDE can extend the formats, and this tool must not call that corruption.

Diagnostic codes are grouped by container: `XJC` common text checks, `XJT` tagged regions, `XJB` designer blocks, `XJP` project manifests, `XJR` resources, `XJU` UI state, `XJL` libraries, and `XJF` formatting.

## Scope

The tool understands the text-format extensions (`.xojo_project`, `.xojo_code`, `.xojo_window`, `.xojo_menu`, `.xojo_toolbar`, `.xojo_report`, `.xojo_image`, `.xojo_color`, `.xojo_filetypeset`, `.xojo_database_connection`, `.xojo_script`) and the binary companions (`.xojo_library`, `.xojo_resources`, `.xojo_uistate`). Xojo Binary Project and Xojo XML Project files are opaque to this tool: it skips them, and reports them only with `--warn-unknown`.

## As a pre-commit hook

`scripts/pre-commit.sample` is a ready-to-use git hook for a Xojo project. It lints the staged `.xojo_*` files and blocks the commit on errors, warnings, or files the formatter would change. To install it into a project, copy it to `.git/hooks/pre-commit` and make it executable. Its `XOJO_LINT` default finds `xojo_lint.py` where Claude Code installs the plugin; for any other install, Codex included, export `XOJO_LINT` as the real path of the script or set it at the top of the hook.

## Tests

```sh
python3 scripts/test_xojo_lint.py
```
