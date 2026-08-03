"""Entry point: `python3 -m xojoctl`, or `python3 path/to/xojoctl`."""

import os
import sys

if __package__ in (None, ""):
    # Run as `python3 path/to/xojoctl`: the interpreter executes __main__.py
    # with no parent package, so relative imports fail. Put the folder that
    # CONTAINS the package on sys.path and import it properly.
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from xojoctl.cli import main
else:
    from .cli import main

if __name__ == "__main__":
    sys.exit(main())
