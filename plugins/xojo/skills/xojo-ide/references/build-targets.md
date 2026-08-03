# Build targets

`xojoctl targets` lists the targets `BuildApp` accepts. The command works offline and never contacts the IDE.

```console
$ xojoctl targets --host
PLATFORM  ARCH                     NAME              VALUE
macOS     Intel 64-bit             darwin-amd64      16
macOS     ARM 64-bit               darwin-arm64      24
macOS     Universal (Intel & ARM)  darwin-universal  9
```

Pass `--host` to see only the targets your machine can build. Drop it to see all of them. Give a name, number, or platform as an argument to filter further.

You can pass either form to `build`:

```sh
xojoctl build --target darwin-arm64
xojoctl build --target 24
```

## Where the numbers come from

Every value, platform, bit width, and architecture is transcribed from [Xojo's documented `BuildApp` targets](https://documentation.xojo.com/topics/build_automation/ide_scripting/building_commands.html#ide-scripting-building-commands-buildapp). That page is the only source.

The `name` spellings, such as `darwin-arm64`, are this tool's own. Each target has exactly one name; run `xojoctl targets` to see it.

There is no build target 7, even though Xojo's own documentation uses `BuildApp(7,False)` as its example. It returns `{}`: no path, no error, no build.

## Sort order

`--sort platform` is the default. It orders macOS, Windows, Linux, iOS, Android, then Web. Within a platform it puts Intel before ARM, single architecture before Universal, 32-bit before 64-bit, and real hardware before simulators.

`--sort value` and `--sort name` are also available.
