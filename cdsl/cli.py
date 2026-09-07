"""Install and diagnose CDSL, and run its private tmux processes."""

import argparse
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time

from . import __version__

def default_home():
    return Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))).expanduser()


def terminal_size():
    try:
        # A resized pane can inherit stale COLUMNS/LINES environment values.
        size = os.get_terminal_size(sys.stdout.fileno())
    except (OSError, ValueError):
        size = shutil.get_terminal_size((80, 24))
    return size.columns, size.lines


def display(snapshot):
    from .status_command import render_via_command
    width, _height = terminal_size()
    # The five-row status pane does not represent the main terminal height.
    return render_via_command(
        snapshot, width=max(10, width - 1), height=24,
        color=not bool(os.environ.get("NO_COLOR")),
    )


def watch(args):
    from .collector import SessionReader
    from .binding import resolve_binding, owner_alive
    from .launcher import enforce_status_height
    from .status_command import load_status_settings
    from .permissions import permission_cycle_keys
    reader = None
    previous = None
    stopping = False

    def stop(_signum, _frame):
        nonlocal stopping
        stopping = True

    tty = sys.stdout.isatty()
    if not tty:
        raise ValueError("The status display requires a CDSL terminal.")
    signals = [signal.SIGTERM, signal.SIGINT]
    if hasattr(signal, "SIGHUP"):
        signals.append(signal.SIGHUP)
    handlers = {sig: signal.getsignal(sig) for sig in signals}
    try:
        for sig in handlers:
            signal.signal(sig, stop)
        sys.stdout.write("\x1b[?25l\x1b[?7l")
        while not stopping:
            interval = 1.0
            enforce_status_height(args.run_dir)
            path = resolve_binding(args.run_dir)
            if path is None:
                reader = None
            elif reader is None or reader.path != Path(path):
                reader = SessionReader(Path(path))
            if reader is None:
                text = "  CDSL: Waiting for a Codex session to start."
            else:
                try:
                    interval = load_status_settings()["refresh_interval"]
                    snapshot = reader.snapshot()
                    snapshot["permission_cycle_keys"] = permission_cycle_keys(
                        args.codex_home, args.run_dir, snapshot.get("cwd"),
                    )
                    text = display(snapshot)
                except (OSError, ValueError) as error:
                    text = "  CDSL: " + str(error).replace("\x1b", "").replace("\n", " ")[:200]
            if text != previous:
                # Avoid scrolling the whole pane with a newline on the last row.
                sys.stdout.write("\x1b[H\x1b[2J" + text.rstrip("\n").replace("\n", "\r\n"))
                sys.stdout.flush()
                previous = text
            if (args.run_dir / "exit-code").exists():
                return 0
            if (args.run_dir / "owner.json").exists() and not owner_alive(args.run_dir):
                return 0
            time.sleep(interval)
    finally:
        try:
            sys.stdout.write("\x1b[0m\x1b[?7h\x1b[?25h")
            sys.stdout.flush()
        finally:
            for sig, handler in handlers.items():
                signal.signal(sig, handler)
    return 0


def run_codex(args):
    from .binding import write_owner
    from .launcher import finish_run
    run_dir = args.run_dir
    code = 1
    try:
        deadline = time.monotonic() + 15
        while not (run_dir / "ready").exists():
            if time.monotonic() > deadline:
                raise ValueError("Timed out while starting the CDSL status pane.")
            time.sleep(0.05)
        executable = os.environ.get("CDSL_REAL_CODEX") or shutil.which("codex")
        if not executable:
            raise ValueError("The codex command was not found.")
        env = os.environ.copy()
        env["CODEX_HOME"] = str(args.codex_home)
        env["CDSL_RUN_DIR"] = str(run_dir)
        env["CDSL_WRAPPED"] = "1"
        forwarded = args.codex_args[1:] if args.codex_args[:1] == ["--"] else args.codex_args
        # Hide the native footer while the five-row companion is active.
        # Keep explicit user overrides last so that they take precedence.
        child = subprocess.Popen([executable, "-c", "tui.status_line=[]", *forwarded], cwd=args.cwd, env=env)
        write_owner(run_dir, child.pid)
        # Codex also receives Ctrl+C; keep the companion alive until Codex exits.
        while True:
            try:
                code = child.wait()
                break
            except KeyboardInterrupt:
                continue
    finally:
        finish_run(run_dir, code)
    return code


def configure_codex(args):
    from .auto_setup import install_auto, uninstall_auto
    operation = install_auto if args.command == "install" else uninstall_auto
    options = {"dry_run": args.dry_run}
    if args.command == "install":
        options["real_codex"] = args.real_codex
    result = operation(**options)
    if args.dry_run:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif args.command == "install":
        print("Configured. Open a new terminal and run codex to start the CCSL-style status display.")
    else:
        import shlex
        from .startup import resolve_real_codex

        if result.get("action") == "unchanged":
            print("No managed CDSL shell integration was found.")
        else:
            print("CDSL shell integration removed.")
        print("Run this in your current Bash shell to clear its cached command path:")
        print("  hash -r")
        print("Then run codex if the official executable is on PATH.")
        executable = None
        for candidate in (result.get("real_codex"), None):
            try:
                executable = resolve_real_codex(real_codex=candidate)
                break
            except (OSError, ValueError, RuntimeError):
                continue
        if executable is not None:
            print("You can also start official Codex directly:")
            print("  " + shlex.quote(str(executable)))
        else:
            print("If codex is still unavailable, locate or reinstall the official Codex executable.")
    return 0


def doctor():
    from .auto_setup import inspect_installation

    checks = inspect_installation()["checks"]
    for check in checks:
        detail = ": " + check["detail"] if check.get("detail") else ""
        print(f"{'OK' if check['ok'] else 'NG'}: {check['name']}{detail}")
    if os.environ.get("WSL_DISTRO_NAME"):
        available = shutil.which("powershell.exe") is not None
        print("Optional: Windows image clipboard support " + ("available" if available else "not detected (not required for the status display)"))
    print("Display: five-row tmux status pane / CCSL style and permission mode")
    print("Startup: dedicated CDSL PATH entry / official Codex files remain unchanged")
    print("Data: local JSONL for the active Codex session and Git metadata")
    if not all(check["ok"] for check in checks):
        print("Check the requirements in README.en.md.")
        return 1
    return 0


def parser():
    p = argparse.ArgumentParser(prog="scripts/cdsl.py", description="Configure and diagnose the CDSL display for Codex.")
    p.add_argument("--version", action="version", version=f"cdsl {__version__} (CCSL 1.0.27 renderer)")
    sub = p.add_subparsers(dest="command", required=True)
    for name in ("_codex", "_watch"):
        command = sub.add_parser(name, help="Internal CDSL startup process")
        command.add_argument("--run-dir", type=Path, required=True)
        command.add_argument("--cwd", type=Path, default=Path.cwd())
        command.add_argument("--codex-home", type=Path, default=default_home())
        if name == "_codex":
            command.add_argument("codex_args", nargs=argparse.REMAINDER, help="Pass arguments after -- to Codex")
    sub.add_parser("doctor", help="Check required commands and configuration")
    for name, help_text in (("install", "Enable the automatic status display when Codex starts"), ("uninstall", "Disable the automatic status display when Codex starts")):
        command = sub.add_parser(name, help=help_text)
        command.add_argument("--codex", action="store_true", required=True, help="Target the Codex shell integration")
        command.add_argument("--dry-run", action="store_true", help="Show planned changes without applying them")
        if name == "install":
            command.add_argument("--real-codex", type=Path, help="Path to the official Codex executable")
    return p


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        if args.command in ("install", "uninstall"):
            return configure_codex(args)
        if args.command == "_watch":
            return watch(args)
        if args.command == "_codex":
            return run_codex(args)
        if args.command == "doctor":
            return doctor()
        return 0
    except (ValueError, OSError) as exc:
        print(f"cdsl: {exc}", file=sys.stderr)
        return 1
