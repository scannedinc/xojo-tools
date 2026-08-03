# `.xojo_script`

Standalone `.xojo_script` files are raw IDE-script source. They have no `#tag` wrapper, no `Begin` block, no manifest-style header, and no required terminator.

```text
Call ShowDialog("Hello world!", "", "OK", "", "")
print "***DONE***"
```

The expanded corpus includes single-line and large multi-procedure scripts, LF and CRLF line endings, and files both with and without a final newline. Consumers must therefore read through end-of-file rather than require a trailing line ending or normalize line endings unnecessarily. Script source can include comments, compiler directives, IDE APIs such as `PropertyValue` and `BuildApp`, and the IDE's comment-looking `'#include ...` directive. Use UTF-8 conservatively for non-ASCII text unless the target Xojo version establishes another encoding.

These are IDE automation scripts, not application classes and not AppleScript project items (`.scpt`). They are also distinct from an `IDEScriptBuildStep`, whose source is embedded inside the build-automation `.xojo_code` file. See [xojo-code-build-automation.md](xojo-code-build-automation.md).
