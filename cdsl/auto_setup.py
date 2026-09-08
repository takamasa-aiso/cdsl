"""Configure update-safe startup integration and the status renderer."""

import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
_RUNTIME_FILES = (
    "cdsl/__init__.py", "cdsl/auto_setup.py", "cdsl/binding.py",
    "cdsl/ccsl_render.py", "cdsl/cli.py", "cdsl/clipboard.py",
    "cdsl/codex_entry.py", "cdsl/collector.py", "cdsl/launcher.py",
    "cdsl/permissions.py", "cdsl/python_runtime.py", "cdsl/renderer.py", "cdsl/startup.py",
    "cdsl/status_command.py", "scripts/cdsl.py", "scripts/paste-image.py",
    "scripts/refresh-statusline.py", "scripts/statusline.py",
)


def _runtime_problems():
    """Check bundled Python sources without importing or executing them."""
    problems = []
    for name in _RUNTIME_FILES:
        path = ROOT / name
        try:
            if not path.is_file():
                raise ValueError
            with path.open("rb") as stream:
                source = stream.read(2 * 1024 * 1024 + 1)
            if not source.strip() or len(source) > 2 * 1024 * 1024:
                raise ValueError
            compile(source, str(path), "exec", dont_inherit=True)
        except (OSError, SyntaxError, ValueError, UnicodeError):
            problems.append(name)
    return problems


def _check_renderer(config: Path):
    """Validate configuration and executable access without running custom commands."""
    from .status_command import load_status_settings

    paths = []
    if config.exists() or config.is_symlink():
        paths.append(config)
    override = os.environ.get("CDSL_CONFIG")
    if override is not None:
        if not override.strip():
            raise ValueError("Set CDSL_CONFIG to the path of a configuration file.")
        paths.append(Path(override).expanduser())
    commands = [[sys.executable, str(ROOT / "scripts/statusline.py")]]
    for path in dict.fromkeys(paths):
        if not path.is_file():
            raise ValueError("The CDSL configuration file is missing or is not a regular file.")
        commands.append(load_status_settings(path)["command"])
    for command in commands:
        executable = shutil.which(command[0])
        if executable is None or not Path(executable).is_file():
            raise ValueError("The renderer executable is missing or is not executable.")


def _tmux_problem():
    """Check the tmux version without starting a server or reading its config."""
    executable = shutil.which("tmux")
    if executable is None:
        return "tmux was not found on PATH."
    try:
        result = subprocess.run([executable, "-V"], capture_output=True, text=True, timeout=2)
        version = re.match(r"tmux (?:next-)?(\d+)\.(\d+)", result.stdout.strip())
        if result.returncode or version is None:
            return "Could not determine the tmux version."
        if tuple(int(part) for part in version.groups()) < (3, 2):
            return "tmux 3.2 or later is required for the session environment options."
    except (OSError, UnicodeError, subprocess.TimeoutExpired):
        return "Could not run tmux -V."
    return None


def inspect_installation(*, home=None, real_codex=None):
    """Collect all installation prerequisites without changing filesystem state."""
    startup_home = home
    home = Path(home) if home is not None else Path.home()
    config = home / ".config/cdsl/config.toml"
    checks = [
        {"name": "Linux / WSL", "ok": sys.platform == "linux"},
        {"name": "Python 3.11 or later", "ok": sys.version_info >= (3, 11)},
    ]
    checks.append({"name": "bash", "ok": shutil.which("bash") is not None})
    tmux_problem = _tmux_problem()
    checks.append({"name": "tmux 3.2 or later", "ok": tmux_problem is None,
                   "detail": tmux_problem or ""})
    checks.append({"name": "git", "ok": shutil.which("git") is not None})
    problems = _runtime_problems()
    checks.append({"name": "CDSL runtime files", "ok": not problems,
                   "detail": "Failed to read or compile: " + ", ".join(problems) if problems else ""})
    startup = None
    try:
        from .startup import plan_startup
        # Reuse the saved executable selection and ownership validation.
        startup = plan_startup(home=startup_home, real_codex=real_codex)
        checks.append({"name": "Official Codex and startup configuration", "ok": True})
    except (OSError, ValueError, ImportError, SyntaxError) as error:
        checks.append({"name": "Official Codex and startup configuration", "ok": False, "detail": str(error)})
    try:
        from .startup import inspect_startup
        startup_inspection = inspect_startup(home=startup_home)
    except (OSError, ValueError, ImportError, SyntaxError) as error:
        startup_inspection = {"clean": False, "artifacts": [], "issues": [str(error)]}
    try:
        _check_renderer(config)
        checks.append({"name": "Renderer configuration and executable", "ok": True})
    except (OSError, ValueError, ImportError, SyntaxError) as error:
        checks.append({"name": "Renderer configuration and executable", "ok": False, "detail": str(error)})
    return {
        "checks": checks,
        "startup": startup,
        "startup_inspection": startup_inspection,
        "status_config": {"path": str(config), "action": "keep" if config.exists() else "create"},
    }


def default_config_text():
    command = [sys.executable, str(ROOT / "scripts" / "statusline.py")]
    return (
        "# The CDSL bridge sends JSON to this program and displays its output.\n"
        "[statusLine]\n"
        f"command = {json.dumps(command, ensure_ascii=False)}\n"
        "timeout_seconds = 2.0\n"
        "refresh_interval = 1.0\n"
    )


def install_auto(*, dry_run=False, home=None, real_codex=None, on_backups=None):
    inspection = inspect_installation(home=home, real_codex=real_codex)
    failures = [check for check in inspection["checks"] if not check["ok"]]
    if failures:
        details = "\n".join("- " + check["name"] + (": " + check["detail"] if check.get("detail") else "")
                            for check in failures)
        raise ValueError("Installation prerequisites are not met:\n" + details
                         + "\nCheck the requirements in README.en.md. No settings have been changed.")
    from .startup import install_startup

    startup_home = home
    home = Path(home) if home is not None else Path.home()
    config = home / ".config" / "cdsl" / "config.toml"
    exists = inspection["status_config"]["action"] == "keep"
    result = {
        "startup": inspection["startup"],
        "status_config": inspection["status_config"],
    }
    if dry_run:
        return result
    created = False
    content = default_config_text().encode("utf-8")
    temporary = None
    try:
        if not exists:
            config.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            descriptor, name = tempfile.mkstemp(prefix=".config-cdsl-", dir=config.parent)
            temporary = Path(name)
            with os.fdopen(descriptor, "wb") as stream:
                os.fchmod(stream.fileno(), 0o600)
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            # Publish the completed file without overwriting a concurrently created config.
            os.link(temporary, config)
            created = True
        result["startup"] = install_startup(
            home=startup_home, real_codex=real_codex, on_backups=on_backups,
        )
    except Exception:
        if created and config.is_file() and config.read_bytes() == content:
            config.unlink()
        raise
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return result


def uninstall_auto(*, dry_run=False, home=None, purge=False, on_backups=None):
    from .startup import uninstall_startup

    # Preserve renderer customizations when removing shell integration.
    return uninstall_startup(home=Path(home) if home is not None else Path.home(),
                             dry_run=dry_run, purge=purge, on_backups=on_backups)
