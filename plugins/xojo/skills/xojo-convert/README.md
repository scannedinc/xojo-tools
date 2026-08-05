# Agent Skill: xojo-convert

This skill converts a Xojo project between the three Xojo storage formats—Xojo Project (text), Xojo Binary Project, and Xojo XML Project—by hand, without the Xojo IDE.

**It is highly experimental, and its use is not advised.** The reliable way to convert a project is the Xojo IDE: open the project, choose **File ▸ Save As**, and pick the target format. Use this skill only when no IDE can touch the project, and treat the result as unverified until an IDE opens it cleanly.

You start the skill yourself. The agent cannot start it for you. In Claude Code, run `/xojo:xojo-convert` when you install the plugin, or `/xojo-convert` when you copy the skill folder by hand.

## What it does

- Identifies which of the three formats a project uses.
- Converts between the XML and text formats by re-serializing the project item by item, using a reference pair of the same project saved in both formats as the specification.
- Salvages readable source from a binary project when nothing else can open it. Structure and layouts are not recoverable this way.
- Refuses to write the binary format. That container is undocumented, and a malformed file can crash the IDE.

## What to expect

The skill asks for your explicit confirmation before it converts anything, writes the result into a new folder without touching the original, and validates text output with the `xojo-lint` skill. It will tell you that the conversion is unverified until the Xojo IDE opens the result, runs Analyze Project clean, and saves it back.

WARNING: A wrong conversion can produce a project that compiles today and misbehaves later. Keep the original project and use source control. See the repository README for the general warning that applies to all of these tools.

## Install

The plugin install in the repository root README covers this skill.

## License

MIT. See [LICENSE](../../../../LICENSE). Xojo, Inc. does not endorse or review this skill, and this skill has no affiliation with Xojo, Inc.
