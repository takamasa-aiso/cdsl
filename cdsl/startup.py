"""Launch CDSL through a dedicated PATH entry without changing the official Codex entry."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shlex
import stat
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
        if path.is_file() and os.access(path, os.X_OK) and not is_cdsl_entry(path, paths["home"]):
            return path
    raise ValueError("Could not find official Codex. Install it and try again, or specify its absolute path with --real-codex.")


def _selected_rc_names(paths: dict[str, Path]) -> tuple[str, str]:
    # Bash reads only the first existing login file; updating .profile alone is insufficient.
    login = next((name for name in _LOGIN_RC_NAMES
                  if paths[name].exists() or paths[name].is_symlink()), ".profile")
    return ".bashrc", login


def _entry(path: Path) -> dict[str, Any]:
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


def _shim(paths: dict[str, Path]) -> bytes:
    import sys

    entry = (
        "import os\n"
        "import sys\n\n"
        f"sys.argv[0] = {str(paths['shim'])!r}\n"
        f"sys.path.insert(0, {str(ROOT)!r})\n"
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
        f"exec {shlex.quote(sys.executable)} -c {shlex.quote(entry)} \"$@\"\n"
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


def _block_span(content: bytes) -> tuple[int, int] | None:
    starts = []
    ends = []
    position = 0
    for line in content.splitlines(keepends=True):
        bare = line.rstrip(b"\r\n")
        for marker, occurrences in ((BEGIN, starts), (END, ends)):
            if marker in line:
                if bare != marker:
                    raise ValueError("The CDSL startup block markers have been modified.")
                occurrences.append((position, position + len(line)))
        position += len(line)
    if not starts and not ends:
        return None
    if len(starts) != 1 or len(ends) != 1 or starts[0][0] >= ends[0][0]:
        raise ValueError("The CDSL startup block markers are duplicated or missing.")
    return starts[0][0], ends[0][1]


def _without_block(content: bytes, record: dict[str, Any] | None) -> bytes:
    span = _block_span(content)
    if span is None:
        return content
    if record is None or _hash(content[span[0]:span[1]]) != record["block_sha256"]:
        raise ValueError("Ownership metadata is missing, or the CDSL startup block has been modified since installation.")
    start, end = span
    if (
        record["separator"] == "\n" and start and end == len(content)
        and content[start - 1:start] == b"\n"
        and _hash(content[:start - 1]) == record["prefix_sha256"]
    ):
        start -= 1
    return content[:start] + content[end:]


def _check_owned(entry: dict[str, Any], saved: dict[str, Any] | None, name: str, path: Path) -> None:
    if entry["kind"] == "missing":
        return
    if saved is None or _hash(entry["content"]) != saved["files"][name]:
        raise ValueError(f"Refusing to overwrite or remove a file that no longer matches the CDSL-managed content: {path}")


def _prepare(home: Path | None, uninstall: bool = False,
             real_codex: str | Path | None = None) -> dict[str, Any]:
    paths = _paths(home)
    saved, old_state = _state(paths)
    operations = []
    selected_rc = () if uninstall else _selected_rc_names(paths)
    previous_rc = tuple(saved["rc"]) if saved else ()
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
        "real_codex": str(paths["real_codex"]),
        "shell_files": [str(paths[name]) for name in selected_rc],
    }
    if uninstall and saved is None:
        return {"paths": paths, "operations": [], "result": {**result, "action": "unchanged", "changes": []}}
    new_state = {"version": 1, "home": str(paths["home"]),
                 "real_codex": str(paths["real_codex"]), "files": {}, "rc": {}}
    private_operations = []
    for name, content, mode in (("shim", _shim(paths), 0o755), ("hook", _hook(paths), 0o600)):
        before = _entry(paths[name])
        _check_owned(before, saved, name, paths[name])
        after = {"kind": "missing"} if uninstall else _file(content, mode)
        new_state["files"][name] = _hash(content)
        if before != after:
            private_operations.append((name, paths[name], before, after))
    for name in dict.fromkeys((*selected_rc, *previous_rc)):
        before = _entry(paths[name])
        content = before.get("content", b"")
        record = saved["rc"].get(name) if saved is not None else None
        base = _without_block(content, record)
        original_missing = record["original_missing"] if record else before["kind"] == "missing"
        if uninstall or name not in selected_rc:
            after = {"kind": "missing"} if original_missing and not base else _file(base, before.get("mode", 0o600))
            # Do not recreate an empty file if the user has deleted it.
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
    # Save restoration metadata before installation; remove startup blocks first on uninstall.
    operations = operations + private_operations + state_operation if uninstall else state_operation + private_operations + operations
    changes = [{
        "path": str(path),
        "action": "remove" if after["kind"] == "missing" else ("create" if before["kind"] == "missing" else "update"),
        "backup": before["kind"] == "file",
    } for _, path, before, after in operations]
    action = "unchanged" if not operations else ("uninstall" if uninstall else ("update" if saved else "install"))
    return {"paths": paths, "operations": operations, "result": {**result, "action": action, "changes": changes}}


def plan_startup(home: Path | None = None, *, real_codex: str | Path | None = None) -> dict[str, Any]:
    """Return only affected paths and actions, without shell contents or secret values."""
    return _prepare(home, real_codex=real_codex)["result"]


def _stage(path: Path, content: bytes, mode: int) -> Path:
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


def _apply(prepared: dict[str, Any]) -> dict[str, Any]:
    operations = prepared["operations"]
    if not operations:
        return prepared["result"]
    staged = {}
    backups = []
    committed = []
    failed = True
    rollback_failed = False
    try:
        for name, path, before, after in operations:
            path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            if after["kind"] == "file":
                staged[path] = _stage(path, after["content"], after["mode"])
            if before["kind"] == "file":
                backup_dir = prepared["paths"]["backups"]
                backup_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
                backup = backup_dir / f"startup-{name.lstrip('.')}-{uuid.uuid4().hex}.bak"
                temporary = _stage(backup, before["content"], 0o600)
                try:
                    os.replace(temporary, backup)
                finally:
                    temporary.unlink(missing_ok=True)
                backups.append(backup)
        if any(_entry(path) != before for _, path, before, _ in operations):
            raise ValueError("Startup settings changed after validation. Installation was canceled.")
        for _, path, before, after in operations:
            if _entry(path) != before:
                raise ValueError("Startup settings changed during installation. Rolling back changes.")
            if after["kind"] == "missing":
                path.unlink()
            else:
                os.replace(staged[path], path)
            committed.append((path, before))
        failed = False
    except BaseException as error:
        rollback_errors = []
        for path, before in reversed(committed):
            try:
                _restore(path, before)
            except OSError:
                rollback_errors.append(str(path))
        if rollback_errors:
            rollback_failed = True
            message = "Could not restore startup settings: " + ", ".join(rollback_errors)
            if backups:
                message += ". Backups were retained: " + ", ".join(str(path) for path in backups)
            raise OSError(message) from error
        raise
    finally:
        for temporary in staged.values():
            temporary.unlink(missing_ok=True)
        if failed and not rollback_failed:
            for backup in backups:
                backup.unlink(missing_ok=True)
    return {**prepared["result"], "backups": [str(path) for path in backups]}


def install_startup(home: Path | None = None, *, dry_run: bool = False,
                    real_codex: str | Path | None = None) -> dict[str, Any]:
    """Install the dedicated entry and shell integration without changing official Codex files."""
    prepared = _prepare(home, real_codex=real_codex)
    return prepared["result"] if dry_run else _apply(prepared)


def uninstall_startup(home: Path | None = None, *, dry_run: bool = False) -> dict[str, Any]:
    """Remove only managed entries and blocks, preserving renderer settings and other files."""
    prepared = _prepare(home, uninstall=True)
    return prepared["result"] if dry_run else _apply(prepared)
