# `.xojo_script`

Standalone `.xojo_script` files are raw IDE-script source. They have no `#tag` wrapper, no `Begin` block, no manifest-style header, and no required terminator.

```text
Call ShowDialog("Hello world!", "", "OK", "", "")
print "***DONE***"
```

Scripts can be single-line or contain multiple procedures, use LF or CRLF line endings, and appear with or without a final newline. Consumers must therefore read through end-of-file rather than require a trailing line ending or normalize line endings unnecessarily. Script source can include comments, compiler directives, IDE APIs such as `PropertyValue` and `BuildApp`, and the IDE's comment-looking `'#include ...` directive. Use UTF-8 conservatively for non-ASCII text unless the target Xojo version establishes another encoding.

These are IDE automation scripts, not application classes and not AppleScript project items (`.scpt`). An `ExternalIDEScriptStep` references one of these files through an opaque alias in the build-automation companion. They are distinct from an `IDEScriptBuildStep`, whose source is embedded inside the build-automation `.xojo_code` file. See [xojo-code-build-automation.md](xojo-code-build-automation.md).
