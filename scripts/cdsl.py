#!/usr/bin/env python3
"""Configure and diagnose CDSL startup, and run its dedicated tmux processes."""

import sys

# Installation preflight must not create bytecode files before validation.
sys.dont_write_bytecode = True

from pathlib import Path

if sys.version_info < (3, 11):
    print("cdsl: Python 3.11 or later is required.", file=sys.stderr)
    raise SystemExit(1)

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cdsl.cli import main

raise SystemExit(main())
