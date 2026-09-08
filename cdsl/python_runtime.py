"""Select a supported Python before importing the main CDSL modules."""

import sys

sys.dont_write_bytecode = True

import json
import os
from pathlib import Path
import stat
import subprocess


_HANDOFF_ENV = "CDSL_PYTHON_HANDOFF"
_PYTHON_NAMES = ("python3.14", "python3.13", "python3.12", "python3.11", "python3", "python")
_VERSION_PROBE = "import sys; sys.exit(sys.version_info < (3, 11))"
_INTERPRETER_ENV = (
    "PYTHONHOME", "PYTHONPATH", "PYTHONPLATLIBDIR", "PYTHONEXECUTABLE",
    "__PYVENV_LAUNCHER__", "PYTHONINSPECT",
)


def _fail(message):
    print("cdsl: " + message, file=sys.stderr)
    raise SystemExit(1)


def _saved_python():
    """Read the optional interpreter path without importing newer Python code."""
    home = Path(os.path.abspath(os.path.expanduser(str(Path.home()))))
    path = home / ".local/share/cdsl/startup.json"
    try:
        information = path.lstat()
    except FileNotFoundError:
        return None
    except OSError:
        raise ValueError("Could not read the CDSL startup metadata.") from None
    if not stat.S_ISREG(information.st_mode):
        raise ValueError("The CDSL startup metadata must be a regular file.")
    try:
        with path.open("rb") as stream:
            content = stream.read(64 * 1024 + 1)
        if len(content) > 64 * 1024:
            raise ValueError
        saved = json.loads(content.decode("utf-8"))
    except (OSError, ValueError, UnicodeError):
        raise ValueError("Could not read the CDSL startup metadata.") from None
    if not isinstance(saved, dict) or saved.get("version") != 1 or saved.get("home") != str(home):
        raise ValueError("The CDSL startup metadata does not match this home directory.")
    if "python_executable" not in saved:
        return None
    value = saved["python_executable"]
    if not isinstance(value, str) or "\0" in value or not Path(value).is_absolute():
        raise ValueError("The saved Python executable path is invalid.")
    return Path(value)


def _candidates(saved):
    if saved is not None:
        yield saved
    directories = [Path(directory) for directory in os.environ.get("PATH", os.defpath).split(os.pathsep)
                   if directory and Path(directory).is_absolute()]
    for name in _PYTHON_NAMES:
        for directory in directories:
            yield directory / name


def _linux_executable(path):
    """Reject Windows launchers and non-regular files without executing them."""
    try:
        resolved = path.resolve()
        if not resolved.is_file() or not os.access(path, os.X_OK):
            return False
        with resolved.open("rb") as stream:
            head = stream.read(4)
        if head.startswith(b"\x7fELF"):
            return True
        if head.startswith(b"MZ"):
            return False
        if any(item.suffix.lower() in (".exe", ".cmd", ".bat", ".ps1") for item in (path, resolved)):
            return False
        return True
    except (OSError, RuntimeError):
        return False


def ensure_python(script):
    """Re-exec the same script with Python 3.11+, preserving its arguments."""
    if sys.version_info >= (3, 11):
        # Keep the guard from leaking into later, unrelated Python invocations.
        os.environ.pop(_HANDOFF_ENV, None)
        return
    if os.environ.get(_HANDOFF_ENV):
        _fail("Python handoff did not start a compatible interpreter. Run this script explicitly with Python 3.11 or later.")
    try:
        saved = _saved_python()
        script_path = os.path.abspath(os.fspath(script))
    except (OSError, ValueError, RuntimeError) as error:
        _fail(str(error))
    # The selected interpreter must not reuse the old Python's library paths.
    environment = {key: value for key, value in os.environ.items() if key not in _INTERPRETER_ENV}
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    seen = set()
    for candidate in _candidates(saved):
        try:
            identity = str(candidate.resolve())
        except (OSError, RuntimeError):
            continue
        if identity in seen or not _linux_executable(candidate):
            continue
        seen.add(identity)
        executable = str(candidate)
        try:
            probe = subprocess.run(
                [executable, "-B", "-c", _VERSION_PROBE],
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                timeout=2, check=False, env=environment,
            )
        except (OSError, subprocess.SubprocessError):
            continue
        if probe.returncode != 0:
            continue
        handoff = dict(environment, **{_HANDOFF_ENV: "1"})
        try:
            os.execve(executable, [executable, "-B", script_path, *sys.argv[1:]], handoff)
            return
        except OSError:
            continue
    _fail("Python 3.11 or later is required, but no compatible Linux interpreter was found. Install Python 3.12 or another supported version and retry.")
