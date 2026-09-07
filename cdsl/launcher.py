"""Launch Codex and its status display in a dedicated tmux session."""

from __future__ import annotations

import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile
import uuid

STATUS_ROWS = 5


def _tmux(socket: str, *args: str, **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(["tmux", "-L", socket, "-f", "/dev/null", *args],
                          check=False, **kwargs)


def _command(action: str, run_dir: Path, cwd: Path, codex_home: Path,
             args: list[str] | None = None) -> str:
    script = Path(__file__).resolve().parent.parent / "scripts" / "cdsl.py"
    command = [sys.executable, str(script), action, "--run-dir", str(run_dir),
               "--cwd", str(cwd), "--codex-home", str(codex_home)]
    if args is not None:
        command.extend(["--", *args])
    return shlex.join(command)


def configure_clipboard(run_dir: Path) -> bool:
    """Connect Ctrl+v to the Windows image clipboard in the dedicated WSL tmux session."""
    if not os.environ.get("WSL_DISTRO_NAME"):
        return False
    state = json.loads((run_dir / "started.json").read_text(encoding="utf-8"))
    socket, session = state.get("socket"), state.get("session")
    if not isinstance(socket, str) or not socket.startswith("cdsl-"):
        raise ValueError("Could not identify the CDSL tmux server.")
    if not isinstance(session, str) or not session.startswith("cdsl-"):
        raise ValueError("Could not identify the CDSL session.")
    script = Path(__file__).resolve().parent.parent / "scripts" / "paste-image.py"
    if not script.is_file():
        raise ValueError("The image-paste script was not found.")
    command = shlex.join([sys.executable, str(script), "--run-dir", str(run_dir),
                          "--pane", "#{pane_id}"])
    result = _tmux(socket, "bind-key", "-n", "C-v", "run-shell", "-b", command,
                   capture_output=True, text=True, timeout=5)
    if result.returncode:
        raise OSError(result.stderr.strip() or "Failed to configure the image-paste key binding.")
    return True


def finish_run(run_dir: Path, code: int) -> None:
    """Record the exit code and close only the session created by this launch."""
    try:
        (run_dir / "exit-code").write_text(str(code), encoding="ascii")
        state = json.loads((run_dir / "started.json").read_text(encoding="utf-8"))
        socket, session = state["socket"], state["session"]
        if not isinstance(socket, str) or not isinstance(session, str):
            return
        if not socket.startswith("cdsl-") or not session.startswith("cdsl-"):
            return
        if (run_dir / "detached").exists():
            shutil.rmtree(run_dir, ignore_errors=True)
        _tmux(socket, "kill-session", "-t", session, capture_output=True, timeout=5)
    except (OSError, ValueError, KeyError, subprocess.TimeoutExpired):
        pass


def enforce_status_height(run_dir: Path) -> None:
    """Restore this launch's status pane to five rows after tmux recalculates the layout."""
    try:
        if os.get_terminal_size(sys.stdout.fileno()).lines == STATUS_ROWS:
            return
    except (OSError, ValueError):
        pass
    try:
        state = json.loads((run_dir / "started.json").read_text(encoding="utf-8"))
        socket, session = state["socket"], state["session"]
        if not isinstance(socket, str) or not isinstance(session, str):
            return
        if not socket.startswith("cdsl-") or not session.startswith("cdsl-"):
            return
        pane = f"{session}:0.1"
        result = _tmux(socket, "display-message", "-p", "-t", pane,
                       "#{pane_height}:#{window_height}", capture_output=True,
                       text=True, timeout=1)
        if result.returncode:
            return
        height, window_height = (int(value) for value in result.stdout.strip().split(":"))
        # Resize only when there is also room for the main pane and its border.
        if height != STATUS_ROWS and window_height >= STATUS_ROWS + 3:
            _tmux(socket, "resize-pane", "-t", pane, "-y", str(STATUS_ROWS),
                  capture_output=True, timeout=1)
    except (OSError, ValueError, KeyError, subprocess.TimeoutExpired):
        pass


def run(codex_args: list[str], cwd: Path, codex_home: Path) -> int:
    from .codex_entry import remote_requested
    if remote_requested(codex_args):
        print("CDSL supports local Codex CLI sessions. --remote is not supported.", file=sys.stderr)
        return 1
    if not shutil.which("tmux"):
        print("CDSL requires tmux. Install tmux before continuing.", file=sys.stderr)
        return 1
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        print("Start CDSL from an interactive terminal.", file=sys.stderr)
        return 1
    cwd = cwd.resolve()
    codex_home = codex_home.expanduser().resolve()
    run_dir = Path(tempfile.mkdtemp(prefix="cdsl-"))
    run_dir.chmod(0o700)
    suffix = uuid.uuid4().hex[:8]
    identity = str(os.getuid()) if hasattr(os, "getuid") else "user"
    socket = f"cdsl-{identity}-{suffix}"
    session = f"cdsl-{os.getpid()}-{suffix}"
    state = {"socket": socket, "session": session,
             "cwd": str(cwd), "codex_home": str(codex_home)}
    (run_dir / "started.json").write_text(json.dumps(state), encoding="utf-8")
    dimensions = shutil.get_terminal_size((100, 30))
    # Pass this launch's entry to the dedicated server without putting secrets in arguments.
    pane_environment = []
    for key in ("CDSL_REAL_CODEX", "CDSL_WRAPPED", "PATH", "CODEX_HOME"):
        value = str(codex_home) if key == "CODEX_HOME" else os.environ.get(key)
        if value is not None:
            pane_environment.extend(["-e", f"{key}={value}"])
    created = False
    try:
        result = _tmux(socket, "new-session", "-d", "-s", session, *pane_environment,
                       "-c", str(cwd), "-x", str(dimensions.columns),
                       "-y", str(max(dimensions.lines, 12)),
                       _command("_codex", run_dir, cwd, codex_home, codex_args),
                       capture_output=True, text=True, timeout=10)
        if result.returncode:
            raise RuntimeError(result.stderr.strip() or "Could not start tmux.")
        created = True
        for arguments in (
            ("set-option", "-t", session, "status", "off"),
            ("set-window-option", "-t", session, "pane-border-status", "off"),
            ("split-window", "-v", "-d", "-l", str(STATUS_ROWS), "-t", f"{session}:0.0",
             "-c", str(cwd), _command("_watch", run_dir, cwd, codex_home)),
            ("set-hook", "-t", session, "client-resized",
             f"resize-pane -t {session}:0.1 -y {STATUS_ROWS}"),
            ("select-pane", "-t", f"{session}:0.0"),
        ):
            result = _tmux(socket, *arguments, capture_output=True, text=True, timeout=10)
            if result.returncode:
                raise RuntimeError(result.stderr.strip() or "Could not create the tmux status pane.")
        configure_clipboard(run_dir)
        (run_dir / "ready").touch()
        environment = os.environ.copy()
        environment.pop("TMUX", None)
        environment.pop("TMUX_PANE", None)
        result = _tmux(socket, "attach-session", "-t", session, env=environment)
        alive = _tmux(socket, "has-session", "-t", session,
                      capture_output=True, timeout=5).returncode == 0
        if alive:
            (run_dir / "detached").touch()
            reconnect = shlex.join(["tmux", "-L", socket, "attach-session", "-t", session])
            print(f"Codex is still running. Reconnect with: {reconnect}", file=sys.stderr)
            return result.returncode
        try:
            return int((run_dir / "exit-code").read_text(encoding="ascii"))
        except (OSError, ValueError):
            return result.returncode
        finally:
            shutil.rmtree(run_dir, ignore_errors=True)
    except (OSError, RuntimeError, subprocess.TimeoutExpired) as error:
        print(f"Could not start CDSL: {error}", file=sys.stderr)
        if created:
            finish_run(run_dir, 1)
        shutil.rmtree(run_dir, ignore_errors=True)
        return 1
