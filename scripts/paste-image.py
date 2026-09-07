#!/usr/bin/env python3
"""Attach an image through the CDSL Ctrl+v binding."""

import argparse
from pathlib import Path
import sys

if sys.version_info < (3, 11):
    raise SystemExit(1)

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cdsl.clipboard import paste_image

parser = argparse.ArgumentParser(description="Attach a clipboard image to the CDSL Codex pane.")
parser.add_argument("--run-dir", type=Path, required=True)
parser.add_argument("--pane", required=True)
arguments = parser.parse_args()
raise SystemExit(paste_image(arguments.run_dir, arguments.pane))
