"""Launch CDSL through a dedicated PATH entry without changing the official Codex entry."""

from __future__ import annotations

import ast
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shlex
import stat
import sys
import tempfile
import uuid
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
BEGIN = b"# >>> CDSL startup >>>"
END = b"# <<< CDSL startup <<<"
_LOGIN_RC_NAMES = (".bash_profile", ".bash_login", ".profile")
_RC_NAMES = (".bashrc", *_LOGIN_RC_NAMES)
_ENTRY_MARKER = b"# CDSL managed entry"


def _hash(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _paths(home: Path | None) -> dict[str, Path]:
    home = Path(os.path.abspath(os.path.expanduser(str(Path.home() if home is None else home))))
    private = home / ".local/share/cdsl"
    if ":" in str(private):
        raise ValueError("Home directories containing the PATH separator are not supported.")
    return {
        "home": home,
        "shim": private / "bin/codex",
        "hook": home / ".config/cdsl/shell.sh",
        "state": private / "startup.json",
        "backups": private / "backups",
        "real_codex": home / ".codex/packages/standalone/current/bin/codex",
        **{name: home / name for name in _RC_NAMES},
    }


def is_cdsl_entry(path: Path, home: Path | None = None) -> bool:
    """Reject the CDSL entry and its copies when selecting the original Codex executable."""
    paths = _paths(home)
    try:
        resolved = path.resolve()
        if resolved in {paths["shim"].resolve(), (ROOT / "scripts/cdsl.py").resolve(),
                        (ROOT / "cdsl/codex_entry.py").resolve()}:
            return True
        with path.open("rb") as stream:
            head = stream.read(8192)
        return _ENTRY_MARKER in head or b"from cdsl.codex_entry import main" in head
    except (OSError, RuntimeError):
        return False


def is_windows_codex(path: Path) -> bool:
    """Recognize Windows executables and npm shims without running a candidate."""
    try:
        resolved = path.resolve()
        if not resolved.is_file():
            return False
        with resolved.open("rb") as stream:
            head = stream.read(8192)
        # Linux binaries may live on a Windows-mounted filesystem or use any name.
        if head.startswith(b"\x7fELF"):
            return False
        if head.startswith(b"MZ") or any(
            entry.suffix.lower() in {".exe", ".cmd", ".bat", ".ps1"}
            for entry in (path, resolved)
        ):
            return True
        shell_shim = head.startswith((b"#!/bin/sh", b"#!/bin/bash", b"#!/usr/bin/env sh", b"#!/usr/bin/env bash"))
        npm_codex = b"node_modules/@openai/codex" in head.replace(b"\\", b"/")
        # Windows npm creates a POSIX shim next to .cmd and .ps1 launchers.
        # Do not classify shared npm JavaScript by its win32/.exe branches.
        return shell_shim and npm_codex and any(
            entry.with_suffix(suffix).is_file()
            for entry in (path, resolved)
            for suffix in (".cmd", ".ps1")
        )
    except (OSError, RuntimeError):
        return False


def resolve_real_codex(home: Path | None = None, real_codex: str | Path | None = None) -> Path:
    """Choose a stable entry without resolving symlinks to a specific installed version."""
    paths = _paths(home)
    if real_codex is not None:
        path = Path(os.path.expanduser(os.fspath(real_codex)))
        if not path.is_absolute():
            raise ValueError("--real-codex must be an absolute path to the official Codex executable.")
        if is_cdsl_entry(path, paths["home"]):
            raise ValueError("CDSL cannot be selected as the original Codex executable. Specify the official Codex path.")
        if not path.is_file() or not os.access(path, os.X_OK):
            raise ValueError(f"Could not verify the official Codex executable: {path}")
        if is_windows_codex(path):
            raise ValueError("Windows Codex cannot be used for Linux/WSL. Select a Linux Codex executable with --real-codex.")
        return path
    candidates = []
    if home is None and os.environ.get("CODEX_HOME"):
        candidates.append(Path(os.path.abspath(os.path.expanduser(os.environ["CODEX_HOME"])))
                          / "packages/standalone/current/bin/codex")
    candidates.append(paths["real_codex"])
    for directory in os.environ.get("PATH", os.defpath).split(os.pathsep):
        # Do not persist executables found through empty or relative PATH entries.
        if directory and Path(directory).is_absolute():
            candidates.append(Path(directory) / "codex")
    for path in candidates:
        if (path.is_file() and os.access(path, os.X_OK)
                and not is_cdsl_entry(path, paths["home"]) and not is_windows_codex(path)):
            return path
    raise ValueError("Could not find Linux Codex. Install it inside Linux/WSL, or specify its absolute path with --real-codex. Windows installations are ignored.")


def _selected_rc_names(paths: dict[str, Path]) -> tuple[str, str]:
    # Bash reads only the first existing login file; updating .profile alone is insufficient.
    login = next((name for name in _LOGIN_RC_NAMES
                  if paths[name].exists() or paths[name].is_symlink()), ".profile")
    return ".bashrc", login


def _safe_parents(path: Path) -> None:
    for parent in path.parents:
        try:
            mode = parent.lstat().st_mode
        except FileNotFoundError:
            continue
        if not stat.S_ISDIR(mode):
            raise ValueError(f"Refusing to use a symbolic link or non-directory parent: {parent}")


def _entry(path: Path) -> dict[str, Any]:
    _safe_parents(path)
    try:
        information = path.lstat()
    except FileNotFoundError:
        return {"kind": "missing"}
    if not stat.S_ISREG(information.st_mode):
        raise ValueError(f"Refusing to modify a non-regular file: {path}")
    return {"kind": "file", "content": path.read_bytes(), "mode": stat.S_IMODE(information.st_mode)}


def _file(content: bytes, mode: int) -> dict[str, Any]:
    return {"kind": "file", "content": content, "mode": mode}


def _state(paths: dict[str, Path]) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    entry = _entry(paths["state"])
    if entry["kind"] == "missing":
        return None, entry
    try:
        saved = json.loads(entry["content"])
    except (ValueError, UnicodeDecodeError):
        raise ValueError("Could not read the CDSL startup restoration metadata.") from None
    if not isinstance(saved, dict) or saved.get("version") != 1 or saved.get("home") != str(paths["home"]):
        raise ValueError("The CDSL startup metadata does not match this home directory.")
    if not isinstance(saved.get("files"), dict) or not isinstance(saved.get("rc"), dict):
        raise ValueError("The CDSL startup restoration metadata is incomplete.")
    for name in ("shim", "hook"):
        if not isinstance(saved["files"].get(name), str):
            raise ValueError("The CDSL startup entry hash metadata is incomplete.")
    if ".bashrc" not in saved["rc"] or not set(saved["rc"]).issubset(_RC_NAMES):
        raise ValueError("The CDSL shell block restoration metadata is incomplete.")
    if "real_codex" in saved and (not isinstance(saved["real_codex"], str)
                                  or not Path(saved["real_codex"]).is_absolute()):
        raise ValueError("The saved path to the original Codex executable is invalid.")
    if "python_executable" in saved and (
        not isinstance(saved["python_executable"], str)
        or "\0" in saved["python_executable"]
        or not Path(saved["python_executable"]).is_absolute()
    ):
        raise ValueError("The saved Python executable path is invalid.")
    for name in saved["rc"]:
        record = saved["rc"].get(name)
        if (
            not isinstance(record, dict)
            or not isinstance(record.get("block_sha256"), str)
            or not isinstance(record.get("prefix_sha256"), str)
            or not isinstance(record.get("original_missing"), bool)
            or record.get("separator") not in ("", "\n")
        ):
            raise ValueError("The CDSL shell block restoration metadata is incomplete.")
    return saved, entry


def _shim(paths: dict[str, Path], *, root: Path = ROOT, python: str | None = None) -> bytes:
    entry = (
        "import os\n"
        "import sys\n\n"
        f"sys.argv[0] = {str(paths['shim'])!r}\n"
        f"sys.path.insert(0, {str(root)!r})\n"
        f"REAL_CODEX = {str(paths['real_codex'])!r}\n"
        "try:\n"
        "    from cdsl.codex_entry import main\n"
        "except ImportError:\n"
        "    os.execv(REAL_CODEX, [REAL_CODEX, *sys.argv[1:]])\n"
        "raise SystemExit(main(real_codex=REAL_CODEX))\n"
    )
    return (
        "#!/bin/sh\n"
        "# CDSL managed entry\n"
        "# Keep the Python interpreter selected during installation.\n"
        "# The official codex file remains unchanged.\n"
        f"exec {shlex.quote(sys.executable if python is None else python)} -c {shlex.quote(entry)} \"$@\"\n"
    ).encode("utf-8")


def _hook(paths: dict[str, Path]) -> bytes:
    # Preserve IFS, positional arguments, and the relative order of empty PATH entries.
    return (
        "# Prepend only the dedicated CDSL entry to PATH.\n"
        f"_cdsl_startup_bin={shlex.quote(str(paths['shim'].parent))}\n"
        "_cdsl_startup_result=$_cdsl_startup_bin\n"
        "if [ \"${PATH+x}\" = x ]; then\n"
        "    _cdsl_startup_rest=$PATH\n"
        "    while :; do\n"
        "        case $_cdsl_startup_rest in\n"
        "            *:*)\n"
        "                _cdsl_startup_part=${_cdsl_startup_rest%%:*}\n"
        "                _cdsl_startup_rest=${_cdsl_startup_rest#*:}\n"
        "                _cdsl_startup_more=1 ;;\n"
        "            *)\n"
        "                _cdsl_startup_part=$_cdsl_startup_rest\n"
        "                _cdsl_startup_more=0 ;;\n"
        "        esac\n"
        "        if [ \"$_cdsl_startup_part\" != \"$_cdsl_startup_bin\" ]; then\n"
        "            _cdsl_startup_result=$_cdsl_startup_result:$_cdsl_startup_part\n"
        "        fi\n"
        "        [ \"$_cdsl_startup_more\" = 1 ] || break\n"
        "    done\n"
        "fi\n"
        "PATH=$_cdsl_startup_result\n"
        "export PATH\n"
        "unset _cdsl_startup_bin _cdsl_startup_result _cdsl_startup_rest _cdsl_startup_part _cdsl_startup_more\n"
        "hash -r 2>/dev/null || :\n"
    ).encode("utf-8")


def _block(paths: dict[str, Path]) -> bytes:
    hook = shlex.quote(str(paths["hook"]))
    return BEGIN + b"\n" + (
        f"if [ -r {hook} ]; then\n"
        f"    . {hook}\n"
        "fi\n"
    ).encode("utf-8") + END + b"\n"


def _block_spans(content: bytes) -> list[tuple[int, int]]:
    """Find complete, separate blocks without guessing at damaged boundaries."""
    spans = []
    start = None
    position = 0
    for line in content.splitlines(keepends=True):
        bare = line.rstrip(b"\r\n")
        if BEGIN in line or END in line:
            if bare == BEGIN and start is None:
                start = position
            elif bare == END and start is not None:
                spans.append((start, position + len(line)))
                start = None
            else:
                raise ValueError("The CDSL startup block boundaries are modified, nested, or incomplete; the shell file was preserved.")
        position += len(line)
    if start is not None:
        raise ValueError("The CDSL startup block has no closing marker; the shell file was preserved.")
    return spans


def _without_block(content: bytes, record: dict[str, Any] | None,
                   paths: dict[str, Path], *, purge: bool = False) -> bytes:
    spans = _block_spans(content)
    if not spans:
        return content
    if len(spans) > 1 and not purge:
        raise ValueError("Multiple CDSL startup blocks were found; explicit --purge is required.")
    for start, end in reversed(spans):
        block = content[start:end]
        recorded = record is not None and _hash(block) == record["block_sha256"]
        if not purge and not recorded and block != _block(paths):
            cause = "The CDSL startup block differs from the saved content" if record else "No usable ownership record exists for this nonstandard CDSL startup block"
            raise ValueError(cause + "; explicit --purge is required.")
        # Only trusted metadata can identify an added separator or a new rc file.
        if (
            recorded and record["separator"] == "\n" and start and end == len(content)
            and content[start - 1:start] == b"\n"
            and _hash(content[:start - 1]) == record["prefix_sha256"]
        ):
            start -= 1
        content = content[:start] + content[end:]
    return content


def _known_shim(content: bytes, paths: dict[str, Path]) -> bool:
    """Compare an older installation's exact template without executing its code."""
    try:
        text = content.decode("utf-8")
        arguments = shlex.split(text[text.index("exec "):])
        if len(arguments) != 5 or arguments[0] != "exec" or arguments[2] != "-c" or arguments[4] != "$@":
            return False
        tree = ast.parse(arguments[3])
        root = ast.literal_eval(tree.body[3].value.args[1])
        real_codex = ast.literal_eval(tree.body[4].value)
        if any(not isinstance(value, str) or "\0" in value or not Path(value).is_absolute()
               for value in (arguments[1], root, real_codex)):
            return False
        expected = _shim({**paths, "real_codex": Path(real_codex)}, root=Path(root), python=arguments[1])
        return content == expected
    except (ValueError, UnicodeError, SyntaxError, IndexError, AttributeError, TypeError, RecursionError):
        return False


def _known_file(name: str, content: bytes, paths: dict[str, Path]) -> bool:
    return content == _hook(paths) if name == "hook" else _known_shim(content, paths)


def _check_owned(entry: dict[str, Any], saved: dict[str, Any] | None,
                 name: str, paths: dict[str, Path], *, purge: bool = False) -> None:
    if entry["kind"] == "missing" or purge:
        return
    if saved and _hash(entry["content"]) == saved["files"][name]:
        return
    if _known_file(name, entry["content"], paths):
        return
    cause = "Content differs from the saved CDSL hash" if saved else "No usable CDSL ownership metadata exists for this nonstandard file"
    raise ValueError(f"{cause}: {paths[name]}. Explicit --purge is required.")


def _load_state(paths: dict[str, Path]) -> tuple[dict[str, Any] | None, dict[str, Any], str | None]:
    entry = _entry(paths["state"])
    try:
        saved, entry = _state(paths)
        return saved, entry, None
    except (ValueError, RecursionError) as error:
        # A regular but invalid record is an artifact to back up, not an authority.
        return None, entry, str(error)


def _recovery_command() -> str:
    return shlex.join([sys.executable, str(ROOT / "scripts/cdsl.py"), "uninstall", "--codex", "--purge", "--dry-run"])


def _prepare(home: Path | None, uninstall: bool = False,
             real_codex: str | Path | None = None, *, purge: bool = False) -> dict[str, Any]:
    try:
        return _prepare_changes(home, uninstall, real_codex, purge=purge)
    except ValueError as error:
        raise ValueError(f"{error}\nNo startup files were changed. Preview recovery: {_recovery_command()}"
                         f"\nRecovery backs up changed files in: {_paths(home)['backups']}") from None


def _prepare_changes(home: Path | None, uninstall: bool = False,
                     real_codex: str | Path | None = None, *, purge: bool = False) -> dict[str, Any]:
    paths = _paths(home)
    saved, old_state, state_problem = _load_state(paths)
    operations = []
    selected_rc = () if uninstall else _selected_rc_names(paths)
    if not uninstall:
        original = real_codex if real_codex is not None else (saved or {}).get("real_codex")
        paths["real_codex"] = resolve_real_codex(home, original)
    elif saved and saved.get("real_codex"):
        paths["real_codex"] = Path(saved["real_codex"])
    result = {
        "home": str(paths["home"]),
        "shim_path": str(paths["shim"]),
        "hook_path": str(paths["hook"]),
        "state_path": str(paths["state"]),
        "backup_directory": str(paths["backups"]),
        "real_codex": str(paths["real_codex"]),
        "shell_files": [str(paths[name]) for name in _RC_NAMES],
        "purge": purge,
        "warnings": [state_problem] if state_problem else [],
    }
    new_state = {"version": 1, "home": str(paths["home"]),
                 "real_codex": str(paths["real_codex"]), "python_executable": sys.executable,
                 "files": {}, "rc": {}}
    private_operations = []
    for name, content, mode in (("shim", _shim(paths), 0o755), ("hook", _hook(paths), 0o600)):
        before = _entry(paths[name])
        _check_owned(before, saved, name, paths, purge=purge)
        after = {"kind": "missing"} if uninstall else _file(content, mode)
        new_state["files"][name] = _hash(content)
        if before != after:
            private_operations.append((name, paths[name], before, after))
    # Scan every supported rc, including blocks absent from or omitted by metadata.
    for name in _RC_NAMES:
        before = _entry(paths[name])
        content = before.get("content", b"")
        record = saved["rc"].get(name) if saved is not None else None
        try:
            base = _without_block(content, record, paths, purge=purge)
        except ValueError as error:
            raise ValueError(f"{paths[name]}: {error}") from None
        original_missing = record["original_missing"] if record else before["kind"] == "missing"
        if uninstall or name not in selected_rc:
            after = {"kind": "missing"} if original_missing and not base else _file(base, before.get("mode", 0o600))
            if before["kind"] == "missing":
                after = before
        else:
            separator = b"\n" if base and not base.endswith(b"\n") else b""
            block = _block(paths)
            after = _file(base + separator + block, before.get("mode", 0o600))
            new_state["rc"][name] = {
                "block_sha256": _hash(block),
                "prefix_sha256": _hash(base),
                "separator": separator.decode(),
                "original_missing": original_missing,
            }
        if before != after:
            operations.append((name, paths[name], before, after))
    after_state = {"kind": "missing"} if uninstall else _file(
        (json.dumps(new_state, indent=2, sort_keys=True) + "\n").encode(), 0o600,
    )
    state_operation = [("state", paths["state"], old_state, after_state)] if old_state != after_state else []
    # Publish metadata last. Recognizable artifacts remain recoverable after a hard stop.
    operations = (operations + private_operations if uninstall else private_operations + operations) + state_operation
    changes = [{
        "path": str(path),
        "action": "remove" if after["kind"] == "missing" else ("create" if before["kind"] == "missing" else "update"),
        "backup": before["kind"] == "file",
    } for _, path, before, after in operations]
    if any(change["backup"] for change in changes):
        _safe_parents(paths["backups"] / "unused")
    action = "unchanged" if not operations else ("uninstall" if uninstall else ("update" if saved else "install"))
    return {"paths": paths, "operations": operations, "result": {**result, "action": action, "changes": changes}}


def inspect_startup(home: Path | None = None) -> dict[str, Any]:
    """Inventory startup artifacts without resolving Codex or changing files."""
    paths = _paths(home)
    artifacts = []
    issues = []
    saved = None
    state_entry = None
    try:
        saved, state_entry, problem = _load_state(paths)
        status = "valid" if saved else ("missing" if state_entry["kind"] == "missing" else "invalid")
        if problem:
            issues.append(f"{paths['state']}: {problem}")
        artifacts.append({"path": str(paths["state"]), "kind": state_entry["kind"], "status": status})
    except (OSError, ValueError) as error:
        issues.append(str(error))
        artifacts.append({"path": str(paths["state"]), "kind": "unsupported", "status": "unsafe"})
    present = state_entry is None or state_entry["kind"] != "missing"
    for name in ("shim", "hook", *_RC_NAMES):
        try:
            entry = _entry(paths[name])
            content = entry.get("content", b"")
            if name in ("shim", "hook"):
                exists = entry["kind"] != "missing"
                status = "missing"
                if exists:
                    status = "recorded" if saved and _hash(content) == saved["files"][name] else (
                        "recognized" if _known_file(name, content, paths) else "modified or unrecognized")
                consistent = (status == "recorded") if saved else not exists
            else:
                spans = _block_spans(content)
                exists = bool(spans)
                record = saved["rc"].get(name) if saved else None
                recorded = len(spans) == 1 and record and _hash(content[spans[0][0]:spans[0][1]]) == record["block_sha256"]
                status = ("recorded" if recorded else "unrecorded block(s)") if exists else "no block"
                consistent = bool(recorded) if record else not exists
            present = present or exists
            if not consistent:
                issues.append(f"{paths[name]}: {status}; startup integration is incomplete or differs from its metadata.")
            artifacts.append({"path": str(paths[name]), "kind": entry["kind"], "status": status})
        except (OSError, ValueError) as error:
            present = True
            issues.append(f"{paths[name]}: {error}")
            artifacts.append({"path": str(paths[name]), "kind": "unsupported", "status": "unsafe", "detail": str(error)})
    return {"clean": not present, "artifacts": artifacts, "issues": issues,
            "recovery_command": _recovery_command(), "backup_directory": str(paths["backups"])}


def plan_startup(home: Path | None = None, *, real_codex: str | Path | None = None) -> dict[str, Any]:
    """Return only affected paths and actions, without shell contents or secret values."""
    return _prepare(home, real_codex=real_codex)["result"]


def _stage(path: Path, content: bytes, mode: int) -> Path:
    _safe_parents(path)
    descriptor, name = tempfile.mkstemp(prefix=f".{path.name}.cdsl-", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            os.fchmod(stream.fileno(), mode)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    return temporary


def _restore(path: Path, entry: dict[str, Any]) -> None:
    if entry["kind"] == "missing":
        path.unlink(missing_ok=True)
        return
    temporary = _stage(path, entry["content"], entry["mode"])
    try:
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _sync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


@contextmanager
def _startup_lock(paths: dict[str, Path]):
    # Lock the directory inode, so crashes release the lock without a stale file.
    directory = paths["state"].parent
    _safe_parents(directory / "unused")
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError("Another CDSL startup operation is running. Wait for it to finish and retry.") from None
        yield
    finally:
        os.close(descriptor)


def _apply(prepared: dict[str, Any], *, on_backups=None) -> dict[str, Any]:
    operations = prepared["operations"]
    if not operations:
        return prepared["result"]
    staged = {}
    backups = []
    committed = []
    try:
        for _, path, _, _ in operations:
            _safe_parents(path)
        if any(before["kind"] == "file" for _, _, before, _ in operations):
            _safe_parents(prepared["paths"]["backups"] / "unused")
        for name, path, before, after in operations:
            _safe_parents(path)
            path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            if after["kind"] == "file":
                staged[path] = _stage(path, after["content"], after["mode"])
            if before["kind"] == "file":
                backup_dir = prepared["paths"]["backups"]
                _safe_parents(backup_dir / "unused")
                backup_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
                backup = backup_dir / f"startup-{name.lstrip('.')}-{uuid.uuid4().hex}.bak"
                temporary = _stage(backup, before["content"], 0o600)
                try:
                    os.replace(temporary, backup)
                finally:
                    temporary.unlink(missing_ok=True)
                backups.append(backup)
                _sync_directory(backup_dir)
        if backups and on_backups is not None:
            on_backups([str(path) for path in backups])
        if any(_entry(path) != before for _, path, before, _ in operations):
            raise ValueError("Startup settings changed after validation. The operation was canceled.")
        for _, path, before, after in operations:
            if _entry(path) != before:
                raise ValueError("Startup settings changed during the operation. Rolling back changes.")
            if after["kind"] == "missing":
                path.unlink()
            else:
                os.replace(staged[path], path)
            committed.append((path, before, after))
            _sync_directory(path.parent)
    except BaseException as error:
        rollback_errors = []
        for path, before, after in reversed(committed):
            try:
                if _entry(path) != after:
                    raise ValueError("A concurrently edited file cannot be rolled back.")
                _restore(path, before)
                _sync_directory(path.parent)
            except (OSError, ValueError):
                rollback_errors.append(str(path))
        if rollback_errors:
            message = "Could not restore startup settings: " + ", ".join(rollback_errors)
        else:
            message = f"Startup operation failed; applied changes were rolled back: {error}"
        if backups:
            message += "\nBackups were retained: " + ", ".join(str(path) for path in backups)
        message += "\nPreview recovery: " + _recovery_command()
        raise OSError(message) from error
    finally:
        for temporary in staged.values():
            temporary.unlink(missing_ok=True)
    return {**prepared["result"], "backups": [str(path) for path in backups]}


def install_startup(home: Path | None = None, *, dry_run: bool = False,
                    real_codex: str | Path | None = None, on_backups=None) -> dict[str, Any]:
    """Install the dedicated entry and shell integration without changing official Codex files."""
    prepared = _prepare(home, real_codex=real_codex)
    if dry_run or not prepared["operations"]:
        return prepared["result"]
    with _startup_lock(prepared["paths"]):
        return _apply(_prepare(home, real_codex=real_codex), on_backups=on_backups)


def uninstall_startup(home: Path | None = None, *, dry_run: bool = False,
                      purge: bool = False, on_backups=None) -> dict[str, Any]:
    """Remove only managed entries and blocks, preserving renderer settings and other files."""
    prepared = _prepare(home, uninstall=True, purge=purge)
    if dry_run or not prepared["operations"]:
        return prepared["result"]
    with _startup_lock(prepared["paths"]):
        return _apply(_prepare(home, uninstall=True, purge=purge), on_backups=on_backups)
