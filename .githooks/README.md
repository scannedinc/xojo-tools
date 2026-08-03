# Git hooks

Run this once per clone to enable the hooks in this directory:

```sh
git config core.hooksPath .githooks
```

`pre-commit` blocks a commit when a staged file contains an email address (addresses on the reserved example domains are allowed), when the identical copies of `helptext.py` differ, or when a staged `.json` file does not parse.
