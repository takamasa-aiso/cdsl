#!/usr/bin/env python3
"""Configure and diagnose CDSL startup, and run its dedicated tmux processes."""

import sys

# Installation preflight must not create bytecode files before validation.
sys.dont_write_bytecode = True

from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cdsl.python_runtime import ensure_python

ensure_python(__file__)

from cdsl.cli import main

raise SystemExit(main())
