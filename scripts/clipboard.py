#!/usr/bin/env python3
"""Connect the dedicated tmux session to the Windows clipboard."""

import argparse
from pathlib import Path
import sys

if sys.version_info < (3, 11):
    raise SystemExit(1)

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cdsl.clipboard import copy_text, paste_clipboard

parser = argparse.ArgumentParser(description="Copy or paste a CDSL clipboard selection.")
subparsers = parser.add_subparsers(dest="action", required=True)
subparsers.add_parser("copy")
paste = subparsers.add_parser("paste")
paste.add_argument("--run-dir", type=Path, required=True)
paste.add_argument("--pane", required=True)
arguments = parser.parse_args()
raise SystemExit(copy_text() if arguments.action == "copy" else paste_clipboard(arguments.run_dir, arguments.pane))
