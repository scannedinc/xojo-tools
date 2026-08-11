# Agent Skill: xojo

This skill gives an AI agent a local, searchable copy of the official [Xojo documentation](https://documentation.xojo.com). The agent greps two index files to find any class, property, method, event, or deprecation, then reads only the one Markdown page it needs. The skill also documents the Xojo project file formats and the rules for writing Xojo code.

## Layout

| Folder | Contents |
| --- | --- |
| `assets/documentation.xojo.com/` | The downloaded mirror. `sync` writes here. |
| `references/documentation/` | The documentation as Markdown, plus the `classes.tsv` and `members.tsv` indexes. `build` writes here. |
| `references/xojo-file-formats/` | A reference for each `.xojo_*` file format in a text project. |
| `references/projects/` | Blank starter projects for each project type. |
| `scripts/` | The tools that download, convert, and check. |

## Getting the documentation

The mirror and the generated Markdown are not committed, because both are generated and together they are large. The agent bootstraps them on first use and refreshes them about once a week; `SKILL.md` carries those instructions. To do it by hand:

```sh
python3 scripts/docs.py sync     # download the documentation -> assets/
python3 scripts/docs.py build    # convert it                 -> references/
```

`sync` downloads the archive that Xojo publishes for each documentation build (about 180 MB) and imports the pieces it needs. On later runs it replays the archive's `ETag` and `Last-Modified` as a conditional request, so a re-sync is a few small requests and a no-op until the archive changes upstream. A successful sync records its time and release in `assets/documentation.xojo.com/sync-state.json`, which is what the weekly check reads.

`build` converts the mirror into Markdown and the two indexes. It runs locally and takes a few seconds.

The scripts use only the Python standard library and run on Python 3.9 or later.

### `sync` flags

| Flag | Meaning |
| --- | --- |
| `PATH` (positional) | Where to download. Default: `assets/documentation.xojo.com/` |
| `--live-site` | After the archive, also fetch every page from the live site with conditional requests. This finds pages that changed after the archive was built, and it is slow: several minutes. |
| `--force-archive` | Download and import the archive even when it is unchanged |
| `--archive-release YEARrN` | Import a specific release, for example `2026r1` |
| `--timeout SECONDS` | Per-request timeout |
| `--delay SECONDS` | With `--live-site`: minimum wait between page requests |
| `--retries N` | With `--live-site`: retries per page on network errors, 429, and 5xx |
| `--abort-after N` | With `--live-site`: stop after `N` pages in a row fail every retry |

When the archive host is unreachable and no usable mirror exists yet, `sync` bootstraps from the live site instead. Every response's validators land in `requests.tsv` beside the mirror, so an interrupted or failed sync resumes where it stopped. Exit codes: `0` clean, `1` finished with failures, `2` aborted, `130` interrupted.

### `build` flags

| Flag | Meaning |
| --- | --- |
| `PATH` (positional) | Where to write. Default: `references/documentation/` |
| `--source PATH` | The mirror to read. Default: `assets/documentation.xojo.com/` |
| `--include-all` | Also convert the pages excluded by default |

`build` skips a handful of pages that add no reference material: Spanish translations of existing English pages, license boilerplate, drafts, and the site's own service pages. No API page is affected.

## The indexes

`classes.tsv` has one row per documentation page: name, kind, flags, deprecation release, replacement, note, member count, path, and a one-line summary. `members.tsv` has one row per property, method, event, and constant: name, kind, signature, flags, deprecation release, replacement, note, and path. Both are tab-separated so one `grep` finds any symbol without parsing; `SKILL.md` teaches the agent the exact recipes.

Every page becomes two Markdown files: a small one with the description and summary tables, and a large `*.members.md` one with the full description of every member. The tree mirrors the site's own layout, so a local path maps to a public URL.

`requests.tsv` is the sync manifest, not a lookup table. It records each response's `ETag` and `Last-Modified`, keyed by the percent-encoded URL, and lives inside the mirror so it travels and resets with the mirror it describes.

## Progress

The slow stages draw an in-place progress bar on a terminal. Through a pipe, which is how an agent runs these scripts, there is no bar: the same code prints one plain line for every few percent of progress, so the output stays short and readable. Set `XOJO_DOCS_COLOR=always` to keep color through a pipe, or `NO_COLOR` to remove it everywhere.

## Checking Xojo source for deprecated APIs

`scripts/check-deprecated.py` reads the indexes and reports the API 1.0 symbols a source file still uses, with what replaced each one:

```console
$ python3 scripts/check-deprecated.py ~/Projects/MyApp/Window1.xojo_code
Window1.xojo_code: 4 deprecated API(s)
  project targets 2026r2
  line 12: ListBox.ListCount -> DesktopListBox.RowCount  [2019r2]
  line 13: InStr -> String.IndexOf  [2019r2]
      INDEX BASE AND SENTINEL CHANGED. InStr returns a one-based position and 0
      when not found; IndexOf returns a zero-based position and -1 when not found.
```

It reads `OrigIDEVersion` from the enclosing `.xojo_project` to learn which release the project targets, and it marks anything deprecated after that release. To avoid false positives, it drops constant, note, and enum blocks whole, strips string literals and comments, and only matches a symbol where the syntax makes it an API reference.

The script works with any coding agent that supports Agent Skills. The `--hook` mode is for Claude Code, whose hooks feature runs a command after each edit: the script reads the hook payload on stdin and checks the edited file. Agents without that feature, Codex included, use the command-line form above. Add the hook to a Xojo project's `.claude/settings.json`:

```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Write|Edit",
        "hooks": [
          {
            "type": "command",
            "command": "python3 /path/to/the/xojo/skill/scripts/check-deprecated.py --hook"
          }
        ]
      }
    ]
  }
}
```

Substitute the real location of the skill. With the plugin installed in Claude Code, that is `~/.claude/plugins/cache/xojo-tools/xojo/<version>/skills/xojo/`.

A hook fires on its event whether or not the skill is loaded. This one exits immediately on any file that is not Xojo source, so it is cheap when it does not apply.
