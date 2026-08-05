---
name: xojo-convert
description: >-
  Convert a Xojo project between its three storage formats, by hand and
  without the Xojo IDE: Xojo Project (text), Xojo Binary Project
  (.xojo_binary_project), and Xojo XML Project (.xojo_xml_project). For turning
  a binary or XML project into text format for source control or agent work, or
  recovering source from a project the other Xojo skills cannot read, when the
  IDE's own File > Save As is not an option. Experimental: always offer the IDE
  route first. Invoke this skill only when the user asks for it by name: it
  rewrites a project file by hand, so never start it on inference. When a user
  needs a format conversion the IDE cannot do, tell them to run the skill
  themselves (/xojo:xojo-convert in Claude Code) and wait for them to do it.
disable-model-invocation: true
---

# Xojo project format conversion

This skill converts a Xojo project between its three storage formats without the Xojo IDE. The conversion is manual: you read the source format and write the target format, item by item.

**This skill is experimental, and using it is not advised when any alternative exists.** The Xojo IDE converts between all three formats reliably: open the project, choose **File ▸ Save As**, and pick the target format. That route is the product's own serializer. This skill exists for the remaining case: no usable IDE, and a project stuck in a format the user cannot work with.

Before you convert anything, tell the user both of these things and get their explicit confirmation:

1. The IDE's **File ▸ Save As** does this conversion reliably, and this skill does not.
2. This conversion is experimental. The result can be wrong in ways that only surface later.

## Safety rules

WARNING: A wrong conversion can corrupt a project in ways that compile today and fail later. Never touch the original project:

- Write the converted project into a **new folder**. Never overwrite or edit the source project's files.
- Require source control or a backup of the original before you start.
- Never claim the conversion succeeded. The only success signal is the Xojo IDE opening the result, Analyze Project running clean, and the IDE saving it back without loss. Say so in your report.

## Identify the format

| Format | On disk |
| --- | --- |
| Xojo Project (text) | A `.xojo_project` manifest of readable `Key=Value` lines, plus companion files (`.xojo_code`, `.xojo_window`, and the other `.xojo_*` extensions) |
| Xojo XML Project | One `.xojo_xml_project` file that starts with an XML declaration |
| Xojo Binary Project | One `.xojo_binary_project` file that is not readable as text |

## What is feasible

| Conversion | Feasibility |
| --- | --- |
| XML → text | Feasible with care. Both formats are text, and both serialize the same project model. |
| Text → XML | Feasible with care, and rarely useful: the reasons to convert (source control, agents, diffs) all point toward text. |
| Binary → text or XML | Salvage only. Read what you can; expect to lose structure. |
| Anything → binary | Do not attempt. The container is undocumented, and there is no way to validate the bytes without the IDE. A malformed file can crash the IDE. |

## The method: convert against a reference pair

All three formats serialize the same project model, so a conversion is a re-serialization, not a translation. Do not guess the mapping between formats. Derive it:

1. **Get a reference pair**: one small project saved in both the source and the target format. If the user, a teammate, or any machine with a Xojo IDE can produce one, that pair is the specification. The blank starter projects in the `xojo` skill's `references/projects/` folder supply the text side for every project type.
2. **Map item by item.** Match each project item in the source to its counterpart in the pair, and carry the property names, values, and IDs across verbatim. Both formats spell most property names the same way.
3. **Preserve what you do not understand.** Unknown keys, flags, and numeric values travel unchanged. Never invent, renumber, or drop project item IDs; other items reference them.
4. **Convert the whole project.** A text project that is missing one companion file from the manifest will not open.

The target grammar for text projects is documented in the `xojo` skill under `references/xojo-file-formats/`; read `index.md` there before writing any `.xojo_*` file, and follow its safety rules for generators. That reference lists its own known gaps in `missing-examples.md`. There is no equivalent local reference for the XML or binary formats, which is why the reference pair is required.

## Validate the result

For a produced text project, in this order:

1. `check --all` and `format --check` from the `xojo-lint` skill must pass.
2. The Xojo IDE must open the project, run Analyze Project clean, and save it without complaint. Use the `xojo-ide` skill when an IDE is reachable. Until this step happens, report the conversion as unvalidated.

For a produced XML project there is no local validator; the IDE is the only check.

## Salvaging a binary project

When the user has only a `.xojo_binary_project` file and no IDE, treat the job as source recovery, not conversion. Method source and property declarations are often stored as readable text runs inside the file, so a text extraction (for example `strings`) recovers much of the code. Window layouts, item relationships, and settings are not reliably recoverable this way. Present what you extract as fragments for the user to rebuild from, and say clearly that the project structure is lost.
