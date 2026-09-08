#!/usr/bin/env python3
"""Render only the stdin snapshot as CCSL-style ANSI output."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import math
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from cdsl.renderer import render


def render_request(request: dict) -> str:
    if not isinstance(request, dict) or type(request.get("version")) is not int or request["version"] != 1:
        raise ValueError("Status line protocol version must be 1.")
    session, terminal = request.get("session"), request.get("terminal")
    if not isinstance(session, dict) or not isinstance(terminal, dict):
        raise ValueError("The status line requires session and terminal objects.")
    for key in ("columns", "rows"):
        if type(terminal.get(key)) is not int or terminal[key] <= 0:
            raise ValueError("terminal.columns and terminal.rows must be positive integers.")
    if not isinstance(terminal.get("color"), bool):
        raise ValueError("terminal.color must be true or false.")
    compatibility = terminal.get("compatibility", False)
    if not isinstance(compatibility, bool):
        raise ValueError("terminal.compatibility must be true or false.")
    now = session.get("now")
    try:
        if isinstance(now, str):
            datetime.fromisoformat(now.replace("Z", "+00:00"))
        elif type(now) in (int, float) and math.isfinite(now):
            datetime.fromtimestamp(now, timezone.utc)
        else:
            raise ValueError
    except (ValueError, OverflowError, OSError):
        raise ValueError("session.now must specify the time when the snapshot was collected.") from None
    return render(session, width=terminal["columns"], color=terminal["color"], compatibility=compatibility)


def main() -> int:
    try:
        request = json.loads(sys.stdin.buffer.read().decode("utf-8"))
        result = render_request(request)
    except (ValueError, TypeError, UnicodeDecodeError):
        # Report invalid input without exposing the input JSON or its values.
        sys.stderr.write("cdsl: Invalid status line input. Check version/session/terminal and session.now.\n")
        return 1
    sys.stdout.buffer.write((result + "\n").encode("utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
