#!/usr/bin/env python3
"""Reload only the current status pane while keeping Codex running."""

import sys

sys.dont_write_bytecode = True

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from cdsl.python_runtime import ensure_python

ensure_python(__file__)

import json
import os
import re

from cdsl.launcher import _command, _tmux


def watcher_matches(arguments, run_dir):
    expected = os.fsencode(str(ROOT / "scripts" / "cdsl.py"))
    try:
        index = arguments.index(expected)
    except ValueError:
        return False
    return arguments[index + 1:index + 4] == [
        b"_watch", b"--run-dir", os.fsencode(str(run_dir)),
    ]


def main():
    runtime = os.environ.get("CDSL_RUN_DIR")
    if not runtime:
        raise ValueError("Could not identify the CDSL session for this terminal.")
    run_dir = Path(runtime)
    state = json.loads((run_dir / "started.json").read_text())
    socket, session = state.get("socket"), state.get("session")
    for name in (socket, session):
        if not isinstance(name, str) or not re.fullmatch(r"cdsl-[A-Za-z0-9_-]+", name):
            raise ValueError("Could not identify the CDSL status pane.")
    result = _tmux(socket, "display-message", "-p", "-t", f"{session}:0.1",
                   "#{pane_id}\t#{pane_pid}", capture_output=True, text=True, timeout=3)
    if result.returncode:
        raise OSError("The status pane was not found.")
    pane, pid = result.stdout.strip().split("\t")
    if not re.fullmatch(r"%[0-9]+", pane) or not pid.isdigit():
        raise ValueError("The status process identity is invalid.")
    arguments = (Path("/proc") / pid / "cmdline").read_bytes().split(b"\0")
    if not watcher_matches(arguments, run_dir):
        raise ValueError("Refusing to restart a process that cannot be verified as the CDSL status renderer.")
    command = _command("_watch", run_dir, Path(state["cwd"]), Path(state["codex_home"]))
    result = _tmux(socket, "respawn-pane", "-k", "-t", pane, "-c", state["cwd"], command,
                   capture_output=True, text=True, timeout=5)
    if result.returncode:
        raise OSError(result.stderr.strip() or "Could not reload the status display.")
    print("Status display reloaded.")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError) as error:
        print(f"cdsl: {error}", file=sys.stderr)
        raise SystemExit(1)
