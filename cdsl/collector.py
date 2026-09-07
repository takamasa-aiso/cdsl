"""Read only the values needed for display from Codex session records."""

from __future__ import annotations

import json
import math
import os
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .permissions import PERMISSION_FIELDS, permission_snapshot


TIMELINE_BUCKETS = 36
_ANCHOR_BYTES = 128


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        number = float(value)
    except (ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def _count(value: Any) -> int | None:
    number = _number(value)
    if number is None or number < 0 or not number.is_integer():
        return None
    return int(number)


def _epoch(value: Any) -> float | None:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.timestamp()
    if isinstance(value, str):
        try:
            return _epoch(datetime.fromisoformat(value.replace("Z", "+00:00")))
        except (ValueError, OverflowError):
            return None
    return _number(value)


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _git_status(cwd: str | None) -> dict[str, Any]:
    result: dict[str, Any] = {
        "git_branch": None,
        "modified_files": None,
        "untracked_files": None,
    }
    if not cwd:
        return result
    try:
        process = subprocess.run(
            [
                "git", "--no-optional-locks", "-c", "core.fsmonitor=false", "-C", cwd,
                "status", "--porcelain=v1", "-z", "--branch", "--untracked-files=all",
            ],
            capture_output=True,
            timeout=1,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return result
    if process.returncode:
        return result
    entries = process.stdout.decode("utf-8", errors="replace").split("\0")
    result.update(modified_files=0, untracked_files=0)
    position = 0
    while position < len(entries):
        entry = entries[position]
        position += 1
        if entry.startswith("## "):
            branch = entry[3:].split("...", 1)[0]
            for prefix in ("No commits yet on ", "Initial commit on "):
                if branch.startswith(prefix):
                    branch = branch[len(prefix):]
            result["git_branch"] = branch
        elif entry.startswith("?? "):
            result["untracked_files"] += 1
        elif len(entry) >= 3:
            result["modified_files"] += 1
            if "R" in entry[:2] or "C" in entry[:2]:
                position += 1
    return result


class SessionReader:
    """Read appended data and retain incomplete lines until the next read."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._identity: tuple[int, int] | None = None
        self._reset()

    def _reset(self) -> None:
        self._offset = 0
        self._pending = b""
        self._anchor = b""
        self._previous_total: int | None = None
        self._token_events: list[tuple[float, int]] = []
        self._state: dict[str, Any] = {
            "model": None,
            "cwd": None,
            "session_id": None,
            "context_tokens": None,
            "context_window": None,
            "context_percent": None,
            "cache_ratio": None,
            "session_tokens": None,
            "session_used_percent": None,
            "session_reset_at": None,
            "session_window_minutes": 300,
            "weekly_used_percent": None,
            "weekly_reset_at": None,
            "weekly_window_minutes": 10080,
            "limits_received": False,
            "session_limit_available": None,
            "weekly_limit_available": None,
            "permissions_source": None,
            **permission_snapshot({}),
        }

    def _read(self) -> None:
        try:
            with self.path.open("rb") as stream:
                stat = os.fstat(stream.fileno())
                identity = (stat.st_dev, stat.st_ino)
                reset = identity != self._identity or stat.st_size < self._offset
                if not reset and self._anchor:
                    stream.seek(self._offset - len(self._anchor))
                    reset = stream.read(len(self._anchor)) != self._anchor
                if reset:
                    self._reset()
                    self._identity = identity
                stream.seek(self._offset)
                added = stream.read()
                self._offset += len(added)
                if not added:
                    return
                self._anchor = (self._anchor + added)[-_ANCHOR_BYTES:]
                lines = (self._pending + added).split(b"\n")
                self._pending = lines.pop()
                for line in lines:
                    try:
                        record = json.loads(line)
                    except (ValueError, UnicodeDecodeError):
                        continue
                    if isinstance(record, dict):
                        self._consume(record)
        except (OSError, ValueError):
            return

    def _consume(self, record: dict[str, Any]) -> None:
        payload = _dict(record.get("payload"))
        kind = record.get("type")
        if kind == "session_meta":
            for destination, value in (
                ("cwd", payload.get("cwd")),
                ("session_id", payload.get("id") or payload.get("session_id")),
            ):
                if isinstance(value, str):
                    self._state[destination] = value
            if PERMISSION_FIELDS.intersection(payload):
                self._state.update(permission_snapshot(payload), permissions_source="session_meta")
        elif kind == "turn_context":
            for key in ("cwd", "model"):
                if isinstance(payload.get(key), str):
                    self._state[key] = payload[key]
            if PERMISSION_FIELDS.intersection(payload):
                self._state.update(permission_snapshot(payload), permissions_source="turn_context")
        elif kind == "event_msg" and payload.get("type") == "thread_settings_applied":
            # Applying /permissions appends and flushes this event without waiting for another turn.
            # Ignore settings owned by another thread and copied through a fork or similar operation.
            owner = payload.get("thread_id")
            if owner is not None and owner != self._state["session_id"]:
                return
            settings = _dict(payload.get("thread_settings"))
            if "permission_profile" in settings and "approval_policy" in settings:
                self._state.update(permission_snapshot(settings), permissions_source="thread_settings_applied")
        elif kind == "event_msg" and payload.get("type") == "token_count":
            self._usage(_dict(payload.get("info")), _epoch(record.get("timestamp")))
            if "rate_limits" in payload:
                self._rate_limits(payload["rate_limits"])
        elif kind == "event_msg" and payload.get("type") == "rate_limits":
            self._rate_limits(payload.get("rate_limits", payload))

    def _usage(self, info: dict[str, Any], timestamp: float | None) -> None:
        if not info:
            return
        usage = _dict(info.get("last_token_usage"))
        tokens = _count(usage.get("total_tokens"))
        window = _count(info.get("model_context_window"))
        self._state["context_tokens"] = tokens
        self._state["context_window"] = window if window else None
        self._state["context_percent"] = (
            tokens / window * 100 if tokens is not None and window else None
        )
        inputs = _count(usage.get("input_tokens"))
        cached = _count(usage.get("cached_input_tokens"))
        self._state["cache_ratio"] = (
            cached / inputs if inputs and cached is not None and cached <= inputs else None
        )
        total = _count(_dict(info.get("total_token_usage")).get("total_tokens"))
        self._state["session_tokens"] = total
        if total is not None:
            delta = total if self._previous_total is None else max(0, total - self._previous_total)
            self._previous_total = total
            if delta and timestamp is not None:
                self._token_events.append((timestamp, delta))

    def _rate_limits(self, limits: Any) -> None:
        limits = _dict(limits)
        if "primary" in limits or "secondary" in limits:
            self._state["limits_received"] = True
        present = set()
        for name in ("primary", "secondary"):
            window = _dict(limits.get(name))
            minutes = _count(window.get("window_minutes"))
            # Weekly-only plans use a 10080-minute primary slot; identify windows by duration.
            field = {300: "session", 10080: "weekly"}.get(minutes)
            if field is None:
                continue
            present.add(field)
            self._state[f"{field}_limit_available"] = True
            used = _number(window.get("used_percent"))
            reset_at = _epoch(window.get("resets_at"))
            if reset_at is not None:
                if reset_at != self._state[f"{field}_reset_at"]:
                    # Do not carry usage forward when only the next window timestamp is provided.
                    self._state[f"{field}_used_percent"] = None
                self._state[f"{field}_reset_at"] = reset_at
            if used is not None and used >= 0:
                self._state[f"{field}_used_percent"] = used
            # Treat null as no update; snapshot checks whether retained values have expired.
            self._state[f"{field}_window_minutes"] = minutes
        complete_windows = all(
            name in limits and (
                limits[name] is None
                or (_count(_dict(limits[name]).get("window_minutes")) or 0) > 0
            )
            for name in ("primary", "secondary")
        )
        if complete_windows:
            for field in ("session", "weekly"):
                if field not in present and self._state[f"{field}_limit_available"] is None:
                    self._state[f"{field}_limit_available"] = False

    def _timeline(self, now: float, minutes: int, reset_at: float | None = None) -> list[float]:
        if not self._token_events:
            return []
        end = reset_at if reset_at is not None else now
        start = end - minutes * 60
        buckets = [0] * TIMELINE_BUCKETS
        for timestamp, tokens in self._token_events:
            if start <= timestamp <= min(now, end):
                bucket = min(TIMELINE_BUCKETS - 1, int((timestamp - start) / (minutes * 60) * TIMELINE_BUCKETS))
                buckets[bucket] += tokens
        peak = max(buckets)
        return [value / peak for value in buckets] if peak else [0.0] * TIMELINE_BUCKETS

    def snapshot(self, now: datetime | float | str | None = None) -> dict[str, Any]:
        self._read()
        current_time = _epoch(now) if now is not None else time.time()
        if current_time is None:
            raise ValueError("now must be a datetime, an ISO 8601 string, or epoch seconds")
        result = dict(self._state)
        for field in ("session", "weekly"):
            reset_at = result[f"{field}_reset_at"]
            if reset_at is not None and reset_at <= current_time:
                result[f"{field}_used_percent"] = None
                result[f"{field}_reset_at"] = None
        result.update(_git_status(result["cwd"]))
        result.update(
            now=current_time,
            session_file=str(self.path),
            timeline_scope="current_session",
            session_timeline=self._timeline(current_time, result["session_window_minutes"], result["session_reset_at"]),
            weekly_timeline=self._timeline(current_time, result["weekly_window_minutes"], result["weekly_reset_at"]),
        )
        return result
