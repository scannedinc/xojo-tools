# Xojo Tools

A plugin for [Claude Code](https://claude.com/claude-code) and [Codex](https://openai.com/codex/) that helps AI agents work with [Xojo](https://www.xojo.com/) projects.

## Agent Skills

The plugin contains five Agent Skills:

| Skill | What it does |
| --- | --- |
| [`xojo`](plugins/xojo/skills/xojo/) | Turns the official Xojo documentation into a local, searchable Markdown tree with symbol indexes. One `grep` finds any class, property, method, or event, so the agent looks facts up instead of recalling them. Also teaches the agent the Xojo project file formats and the house rules for writing Xojo code. |
| [`xojo-ide`](plugins/xojo/skills/xojo-ide/) | Drives a running Xojo IDE from the command line with the bundled `xojoctl` tool: open, analyze, build, run, and script, with JSON output for automation. |
| [`xojo-lint`](plugins/xojo/skills/xojo-lint/) | Validates Xojo project files in text format and repairs safe serialization details. Made for use in editors, agents, and pre-commit hooks. |
| [`xojo-migrate`](plugins/xojo/skills/xojo-migrate/) | Converts Xojo source code from API 1.0 to API 2.0 with vetted, confidence-tiered conversion rules, and knows which changes a rename does not fix. |
| [`xojo-convert`](plugins/xojo/skills/xojo-convert/) | Converts a project between the Xojo Project, Xojo Binary Project, and Xojo XML Project formats by hand when no IDE is available. Highly experimental and not advised; the IDE's own **File ▸ Save As** is the reliable converter. |

The agent uses `xojo`, `xojo-ide`, and `xojo-lint` on its own. You start `xojo-migrate` and `xojo-convert` yourself, because each one rewrites a whole project. In Claude Code, run `/xojo:xojo-migrate` or `/xojo:xojo-convert`; the `xojo:` prefix is the plugin name.

## Install

For Claude Code, add this repository as a marketplace, then install the plugin:

```text
/plugin marketplace add travisjhicks/xojo-tools
/plugin install xojo@xojo-tools
```

For Codex, add the repository as a marketplace, then add the plugin:

```sh
codex plugin marketplace add travisjhicks/xojo-tools
codex plugin add xojo@xojo-tools
```

Start a new Codex thread after installation so the plugin loads.

## Requirements

- Python 3.9 or later, available as `python3`. The bundled scripts use only the Python standard library, so there is nothing else to install.
- The `xojo-ide` skill also needs a running Xojo IDE on the same machine.
- The `xojo-migrate` skill also needs `git` and the Xojo IDE.

## Use source control

**WARNING: These skills and their scripts create, change, and delete files in your projects. A wrong edit can destroy your work, and this software comes with no warranty. Use it at your own risk.** Use the tools only on files that a git repository, another source-control system, or a snapshot backup can restore. Commit or snapshot your work before you let an agent change it.

## Not a Xojo, Inc. product

Xojo, Inc. did not produce, review, or endorse this plugin, and this plugin has no affiliation with Xojo, Inc. "Xojo" is a trademark of Xojo, Inc. The name appears here only to identify the software that these tools work with. The repository redistributes no Xojo documentation.

## License

MIT. See [LICENSE](LICENSE).
