"""Route interactive Codex launches through the fixed status display."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import sys


_COMMANDS = {
    "agents", "exec", "e", "review", "login", "logout", "mcp", "plugin",
    "mcp-server", "app-server", "remote-control", "completion", "update", "doctor",
    "sandbox", "debug", "apply", "a", "resume", "queue", "archive", "delete",
    "migrate-rollouts", "unarchive", "fork", "cloud", "exec-server", "features", "help",
}
_VALUE_OPTIONS = {
    "--config", "--enable", "--disable", "--remote", "--remote-auth-token-env",
    "--image", "--model", "--local-provider", "--profile", "--sandbox", "--cd",
    "--add-dir", "--ask-for-approval",
}
_FLAGS = {
    "--oss", "--strict-config", "--approve-for-me",
    "--dangerously-bypass-approvals-and-sandbox", "--dangerously-bypass-hook-trust",
    "--search", "--no-alt-screen", "--last", "--all", "--include-non-interactive",
    "--yolo", "--full-auto",
}
_SHORT_VALUES = {"c", "i", "m", "p", "s", "C", "a"}


def _inspect(argv: list[str]) -> tuple[bool, bool]:
    interactive = True
    remote = False
    first_positional_seen = False
    index = 0
    while index < len(argv):
        argument = argv[index]
        if argument == "--":
            # Treat subsequent --help or exec tokens as prompt text.
            break
        if argument.startswith("--"):
            key, equals, _value = argument.partition("=")
            if key == "--remote":
                remote = True
                interactive = False
            if key in ("--help", "--version"):
                interactive = False
            elif key in _VALUE_OPTIONS:
                if not equals:
                    index += 1
                    if index >= len(argv):
                        interactive = False
            elif key not in _FLAGS or equals:
                # Let the original CLI validate unknown options.
                interactive = False
        elif argument.startswith("-") and argument != "-":
            short_index = 1
            while short_index < len(argument):
                key = argument[short_index]
                if key in ("h", "V"):
                    interactive = False
                elif key in _SHORT_VALUES:
                    if short_index == len(argument) - 1:
                        index += 1
                        if index >= len(argv):
                            interactive = False
                    break
                else:
                    interactive = False
                short_index += 1
        elif not first_positional_seen:
            if argument in _COMMANDS and argument not in ("resume", "fork"):
                interactive = False
            first_positional_seen = True
        index += 1
    return interactive, remote


def is_interactive_invocation(argv: list[str]) -> bool:
    """Check whether the arguments request a local interactive UI."""
    return _inspect(argv)[0]


def remote_requested(argv: list[str]) -> bool:
    return _inspect(argv)[1]


def dispatch(argv: list[str], real_codex: str | Path) -> int:
    """Launch interactive sessions with status output; otherwise exec the original CLI."""
    executable = os.fspath(real_codex)
    from .startup import is_cdsl_entry
    if is_cdsl_entry(Path(executable)):
        raise ValueError("CDSL cannot be used as the original Codex executable. Check --real-codex.")
    try:
        same_entry = Path(executable).samefile(sys.argv[0])
    except OSError:
        same_entry = False
    if same_entry:
        raise ValueError("The original Codex executable is the CDSL entry itself. Check --real-codex.")
    # Keep the current symlink so the same entry follows Codex updates.
    wrapped = os.environ.get("CDSL_WRAPPED") == "1"
    use_status = (not wrapped and sys.stdin.isatty() and sys.stdout.isatty()
                  and is_interactive_invocation(argv) and shutil.which("tmux"))
    if not use_status:
        os.execv(executable, [executable, *argv])
        return 0
    os.environ["CDSL_REAL_CODEX"] = executable
    os.environ["CDSL_WRAPPED"] = "1"
    from .launcher import run
    codex_home = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))).expanduser()
    return run(list(argv), Path.cwd(), codex_home)


def main(argv: list[str] | None = None, real_codex: str | Path | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    executable = real_codex or os.environ.get("CDSL_REAL_CODEX")
    if executable is None:
        from .startup import resolve_real_codex
        try:
            executable = resolve_real_codex()
        except ValueError as error:
            print(f"codex: {error}", file=sys.stderr)
            return 127
    try:
        return dispatch(arguments, executable)
    except (OSError, ValueError) as error:
        print(f"codex: Could not start the original Codex CLI: {error}", file=sys.stderr)
        return 127


if __name__ == "__main__":
    raise SystemExit(main())
