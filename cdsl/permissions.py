"""Convert effective thread permissions to display labels."""

from __future__ import annotations

import json
from pathlib import Path
import re
import tomllib
from typing import Any


PERMISSION_FIELDS = frozenset({
    "sandbox_policy", "permission_profile", "active_permission_profile",
    "approval_policy", "approvals_reviewer", "file_system_sandbox_policy",
})


def _dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def _text(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _network_enabled(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if value in ("enabled", "unrestricted"):
        return True
    if value in ("disabled", "restricted"):
        return False
    return None


def permission_snapshot(payload: dict) -> dict[str, str | None]:
    """Return permission types without copying allowed paths or user settings."""
    sandbox = payload.get("sandbox_policy")
    sandbox_type = _text(sandbox) or _text(_dict(sandbox).get("type"))
    profile = _dict(payload.get("permission_profile"))
    profile_type = _text(profile.get("type"))
    active = payload.get("active_permission_profile")
    profile_name = _text(active) or _text(_dict(active).get("id"))
    filesystem = _dict(profile.get("file_system"))
    network = _network_enabled(profile.get("network"))
    if network is None:
        network = _network_enabled(_dict(sandbox).get("network_access"))
    entries = filesystem.get("entries")
    explicit_write = isinstance(entries, list) and any(_dict(entry).get("access") == "write" for entry in entries)
    ordinary_filesystem = filesystem.get("type") != "unrestricted"
    # Preserve named profiles instead of relabeling them as built-in modes.
    if profile_name is not None and not profile_name.startswith(":"):
        mode = profile_name
    elif profile_type == "disabled":
        mode = "Full Access"
    elif profile_type is not None:
        if (
            profile_type == "managed" and ordinary_filesystem
            and profile_name in (":workspace", ":workspace-write")
            and sandbox_type in (None, "workspace-write")
        ):
            mode = "Workspace"
        elif (
            profile_type == "managed" and ordinary_filesystem and not explicit_write
            and profile_name in (":read-only", ":readonly")
            and sandbox_type in (None, "read-only") and network is not True
        ):
            mode = "Read Only"
        else:
            mode = "Custom permissions"
    elif sandbox_type == "workspace-write":
        mode = "Workspace"
    elif sandbox_type == "read-only" and network is not True:
        mode = "Read Only"
    elif sandbox_type == "danger-full-access" and network is not False:
        mode = "Full Access"
    elif sandbox_type is not None or profile_name is not None:
        mode = "Custom permissions"
    else:
        mode = None

    approval = payload.get("approval_policy")
    approval_policy = _text(approval)
    if isinstance(approval, dict) and "granular" in approval:
        approval_policy = "granular"
    reviewer = _text(payload.get("approvals_reviewer"))
    if approval_policy == "on-request":
        if reviewer in ("auto_review", "auto-review"):
            approval_mode = "Approve for me"
        elif reviewer == "user":
            approval_mode = "Ask for approval"
        else:
            approval_mode = "On request"
    else:
        approval_mode = {
            "never": "Never", "on-failure": "On failure", "untrusted": "Untrusted",
            "granular": "Granular",
        }.get(approval_policy)
    return {
        "permission_mode": mode,
        "permission_profile_name": profile_name,
        "permission_profile_type": profile_type,
        "sandbox_policy": sandbox_type,
        "approval_policy": approval_policy,
        "approvals_reviewer": reviewer,
        "approval_mode": approval_mode,
    }


_MISSING = object()
_CYCLE_PATH = ("tui", "keymap", "chat", "next_permission_mode")


def _cycle_setting(config: dict):
    value = config
    for name in _CYCLE_PATH:
        if not isinstance(value, dict):
            raise ValueError("Invalid keymap table")
        if name not in value:
            return _MISSING
        value = value[name]
    return value


def _read_keymap_config(path: Path, *, required: bool = False) -> dict:
    try:
        with path.open("rb") as stream:
            content = stream.read(1024 * 1024 + 1)
    except FileNotFoundError:
        if required:
            raise
        return {}
    if len(content) > 1024 * 1024:
        raise ValueError("Config exceeds the keymap reader limit")
    return tomllib.loads(content.decode("utf-8"))


def _key_label(binding: str) -> str:
    """Format one saved shortcut, including a two-stroke chord."""
    if not binding or len(binding) > 160 or any(ord(c) < 32 or ord(c) == 127 for c in binding):
        raise ValueError("Invalid key binding")
    strokes = binding.split()
    if not 1 <= len(strokes) <= 2:
        raise ValueError("Invalid key sequence")
    labels = []
    names = {"enter": "Enter", "return": "Enter", "tab": "Tab", "backtab": "Shift+Tab",
             "esc": "Esc", "escape": "Esc", "space": "Space", "backspace": "Backspace",
             "delete": "Delete", "insert": "Insert", "home": "Home", "end": "End",
             "pageup": "PageUp", "page-up": "PageUp", "pagedown": "PageDown", "page-down": "PageDown",
             "minus": "-", "up": "Up", "down": "Down",
             "left": "Left", "right": "Right"}
    for stroke in strokes:
        modifiers = []
        key = stroke.lower()
        while match := re.match(r"^(ctrl|alt|shift)-", key):
            modifier = match.group(1).title()
            if modifier in modifiers:
                raise ValueError("Duplicate modifier")
            modifiers.append(modifier)
            key = key[match.end():]
        if key in names:
            label = names[key]
        elif re.fullmatch(r"f(?:[1-9]|1[0-9]|2[0-4])", key):
            label = key.upper()
        elif len(key) == 1 and key.isprintable() and not key.isspace():
            label = key
        else:
            raise ValueError("Unknown key name")
        labels.append("+".join([*modifiers, label]))
    return " ".join(labels)


def permission_cycle_keys(codex_home: Path, run_dir: Path, cwd: str | None) -> list[str] | None:
    """Read saved user/profile shortcuts; return None for ambiguous overrides.

    Only the shortcut labels leave this reader. Config values, command-line
    arguments, and permission paths are never added to the display snapshot.
    """
    from .binding import owner_alive

    try:
        if not owner_alive(run_dir):
            return None
        owner = json.loads((run_dir / "owner.json").read_text())
        arguments = (Path("/proc") / str(owner["pid"]) / "cmdline").read_bytes()
        arguments = [value.decode("utf-8") for value in arguments.split(b"\0") if value]
        profile = None
        index = 1
        while index < len(arguments):
            value = arguments[index]
            if value == "--":
                break
            if value in ("--profile", "-p"):
                index += 1
                profile = arguments[index]
            elif value.startswith("--profile="):
                profile = value.split("=", 1)[1]
            elif value.startswith("-p") and not value.startswith("--"):
                profile = value[2:].removeprefix("=")
            elif value in ("--config", "-c") or value.startswith(("--config=", "-c")):
                if value in ("--config", "-c"):
                    index += 1
                    override = arguments[index]
                else:
                    override = value.split("=", 1)[1] if value.startswith("--config=") else value[2:]
                try:
                    if _cycle_setting(tomllib.loads(override)) is not _MISSING:
                        return None
                except tomllib.TOMLDecodeError:
                    if "keymap" in override:
                        return None
            index += 1
        if not owner_alive(run_dir):
            return None

        # TUI edits change RAM directly, so project/CLI precedence cannot be
        # reconstructed reliably by remerging files in a separate process.
        for name in ("config.toml", "managed_config.toml"):
            if _cycle_setting(_read_keymap_config(Path("/etc/codex") / name)) is not _MISSING:
                return None
        if cwd:
            directory = Path(cwd).resolve()
            for parent in (directory, *directory.parents):
                config_path = parent / ".codex/config.toml"
                if config_path.resolve() == (codex_home / "config.toml").resolve():
                    continue
                if _cycle_setting(_read_keymap_config(config_path)) is not _MISSING:
                    return None
        value = _cycle_setting(_read_keymap_config(codex_home / "config.toml"))
        if profile is not None:
            if not profile or profile in (".", "..") or Path(profile).name != profile:
                return None
            selected = _cycle_setting(_read_keymap_config(codex_home / f"{profile}.config.toml", required=True))
            if selected is not _MISSING:
                value = selected
        if value is _MISSING:
            return []
        bindings = [value] if isinstance(value, str) else value
        if not isinstance(bindings, list) or not all(isinstance(item, str) for item in bindings):
            return None
        return [_key_label(binding) for binding in bindings]
    except (OSError, ValueError, KeyError, IndexError, TypeError, UnicodeError):
        return None
