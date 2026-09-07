"""Bind the displayed Codex process to its conversation log."""

from __future__ import annotations

import json
import os
from pathlib import Path


def _read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def _write_json(path: Path, value: dict) -> None:
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(value), encoding="utf-8")
    temporary.chmod(0o600)
    temporary.replace(path)


def _process_identity(pid: int) -> tuple[str, str] | None:
    try:
        fields = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
        return fields[0], fields[19]
    except (OSError, ValueError, IndexError):
        return None


def write_owner(run_dir: Path, pid: int) -> None:
    """Record process start ticks to detect PID reuse."""
    identity = _process_identity(pid)
    _write_json(run_dir / "owner.json", {
        "pid": pid,
        "start_ticks": identity[1] if identity else None,
    })


def owner_alive(run_dir: Path) -> bool:
    owner = _read_json(run_dir / "owner.json")
    pid = owner.get("pid")
    if not isinstance(pid, int) or isinstance(pid, bool) or pid <= 0:
        return False
    identity = _process_identity(pid)
    return bool(identity and identity[0] not in ("Z", "X")
                and owner.get("start_ticks") == identity[1])


def _session_meta(path: Path) -> dict:
    try:
        with path.open(encoding="utf-8") as stream:
            # Read only the leading metadata, without scanning conversation contents.
            line = stream.readline(2 * 1024 * 1024)
        record = json.loads(line)
        if record.get("type") == "session_meta":
            payload = record.get("payload")
            return payload if isinstance(payload, dict) else {}
    except (OSError, ValueError, AttributeError):
        pass
    return {}


def _root_session(meta: dict) -> bool:
    source = meta.get("source")
    return bool(meta.get("id") and not meta.get("parent_thread_id")
                and meta.get("agent_path") in (None, "", "/", "/root")
                and source != "subagent"
                and not (isinstance(source, dict) and "subagent" in source))


def _descriptor_is_writable(pid: int, descriptor: str) -> bool:
    try:
        info = Path(f"/proc/{pid}/fdinfo/{descriptor}").read_text(encoding="ascii")
        for line in info.splitlines():
            if line.startswith("flags:"):
                flags = int(line.split(":", 1)[1].strip(), 8)
                return (flags & os.O_ACCMODE) in (os.O_WRONLY, os.O_RDWR)
    except (OSError, ValueError):
        pass
    return False


def _direct_children(pid: int) -> list[int]:
    """Read only direct children of launchers such as Node."""
    found = set()
    try:
        for task in Path(f"/proc/{pid}/task").iterdir():
            try:
                for value in (task / "children").read_text().split():
                    child = int(value)
                    fields = Path(f"/proc/{child}/stat").read_text().rsplit(")", 1)[1].split()
                    if int(fields[1]) == pid:
                        found.add(child)
            except (OSError, ValueError, IndexError):
                continue
    except OSError:
        pass
    return sorted(found)


def _root_writers(pid: int) -> dict[Path, dict]:
    candidates = {}
    before = _process_identity(pid)
    if before is None:
        return candidates
    try:
        for fd in Path(f"/proc/{pid}/fd").iterdir():
            if not _descriptor_is_writable(pid, fd.name):
                continue
            try:
                path = fd.resolve(strict=True)
            except (OSError, RuntimeError):
                continue
            if not path.name.startswith("rollout-") or path.suffix != ".jsonl":
                continue
            meta = _session_meta(path)
            if _root_session(meta):
                candidates[path] = meta
    except OSError:
        pass
    return candidates if _process_identity(pid) == before else {}


def _nearest_root_writers(pid: int) -> dict[Path, dict]:
    # Prefer the native process log; do not follow other Codex instances it starts.
    # Search nearby native children only for npm or shell launchers.
    frontier, seen = [pid], set()
    for _depth in range(5):
        candidates, following = {}, []
        for current in frontier:
            if current in seen or len(seen) >= 128:
                continue
            seen.add(current)
            candidates.update(_root_writers(current))
            following.extend(_direct_children(current))
        if candidates:
            return candidates
        frontier = following
        if not frontier:
            break
    return {}


def resolve_binding(run_dir: Path) -> Path | None:
    """Track the root conversation being written by the launched process; reject ambiguity."""
    if not owner_alive(run_dir):
        return None
    owner = _read_json(run_dir / "owner.json")
    fd_dir = Path(f"/proc/{owner['pid']}/fd")
    if not fd_dir.is_dir():
        return None
    candidates = _nearest_root_writers(owner["pid"])
    if len(candidates) == 1 and owner_alive(run_dir):
        return next(iter(candidates))
    # Do not infer the active conversation from mtime when multiple roots are writable.
    # During transitions, do not reuse an old conversation or another process in the same cwd.
    return None
