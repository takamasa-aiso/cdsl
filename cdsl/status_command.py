"""Pass a collected snapshot to the configured status display command."""

from __future__ import annotations

import errno
import json
import math
import os
from pathlib import Path
import selectors
import signal
import subprocess
import sys
import time
import tomllib


ROOT = Path(__file__).resolve().parents[1]
MAX_OUTPUT_BYTES = 64 * 1024
_ALLOWED_SETTINGS = {"command", "timeout_seconds", "refresh_interval"}


def load_status_settings(config_path: Path | None = None) -> dict:
    """Load settings, using built-in defaults only when the default config file is absent."""
    override = os.environ.get("CDSL_CONFIG")
    explicit = config_path is not None or override is not None
    if config_path is not None:
        path = Path(config_path).expanduser()
    elif override is not None:
        if not override.strip():
            raise ValueError("Set CDSL_CONFIG to the path of a configuration file.")
        path = Path(override).expanduser()
    else:
        path = Path.home() / ".config" / "cdsl" / "config.toml"
    try:
        with path.open("rb") as stream:
            raw = stream.read(MAX_OUTPUT_BYTES + 1)
    except FileNotFoundError:
        if explicit:
            raise ValueError("The specified CDSL configuration file was not found.") from None
        raw = b""
    except OSError:
        raise ValueError("Could not read the CDSL configuration file.") from None
    if len(raw) > MAX_OUTPUT_BYTES:
        raise ValueError("The CDSL configuration file exceeds the 64 KiB limit.")
    try:
        parsed = tomllib.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, tomllib.TOMLDecodeError):
        raise ValueError("The CDSL configuration file must contain valid UTF-8 TOML.") from None
    if set(parsed) - {"statusLine"}:
        raise ValueError("CDSL configuration may contain only [statusLine].")
    settings = parsed.get("statusLine", {})
    if not isinstance(settings, dict) or set(settings) - _ALLOWED_SETTINGS:
        raise ValueError("[statusLine] may contain only command, timeout_seconds, and refresh_interval.")
    command = settings.get("command", [sys.executable, str(ROOT / "scripts" / "statusline.py")])
    if (
        not isinstance(command, list) or not command
        or not all(isinstance(item, str) and "\0" not in item for item in command)
        or not command[0].strip()
    ):
        raise ValueError("statusLine.command must be a string array starting with an executable name.")
    result = {"command": list(command)}
    for name, default, minimum in (("timeout_seconds", 2.0, 0.001), ("refresh_interval", 1.0, 0.1)):
        value = settings.get(name, default)
        if (
            isinstance(value, bool) or not isinstance(value, (int, float))
            or not minimum <= value <= 60 or not math.isfinite(value)
        ):
            raise ValueError(f"statusLine.{name} must be a finite number between {minimum:g} and 60 seconds.")
        result[name] = float(value)
    return result


def _stop(process: subprocess.Popen) -> None:
    """Terminate only the timed-out renderer process and its children."""
    try:
        if os.name == "posix":
            os.killpg(process.pid, signal.SIGKILL)
        else:
            process.kill()
    except ProcessLookupError:
        pass
    try:
        process.wait(timeout=1)
    except subprocess.TimeoutExpired:
        pass


def _run_bounded(command: list[str], payload: bytes, timeout: float) -> tuple[int, bytes]:
    try:
        process = subprocess.Popen(
            command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            shell=False, start_new_session=True,
        )
    except OSError as error:
        reason = "executable was not found" if error.errno == errno.ENOENT else "executable could not be started"
        raise ValueError(f"Status line {reason}.") from None
    output = bytearray()
    stderr_size = 0
    sent = 0
    selector = selectors.DefaultSelector()
    deadline = time.monotonic() + timeout
    try:
        for stream, event, name in (
            (process.stdin, selectors.EVENT_WRITE, "stdin"),
            (process.stdout, selectors.EVENT_READ, "stdout"),
            (process.stderr, selectors.EVENT_READ, "stderr"),
        ):
            os.set_blocking(stream.fileno(), False)
            selector.register(stream, event, name)
        while selector.get_map():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise ValueError("The status line command timed out.")
            for key, _events in selector.select(remaining):
                stream = key.fileobj
                if key.data == "stdin":
                    try:
                        sent += os.write(stream.fileno(), payload[sent:sent + 16384])
                    except BrokenPipeError:
                        sent = len(payload)
                    except BlockingIOError:
                        continue
                    if sent == len(payload):
                        selector.unregister(stream)
                        stream.close()
                    continue
                try:
                    chunk = os.read(stream.fileno(), 16384)
                except BlockingIOError:
                    continue
                if not chunk:
                    selector.unregister(stream)
                    stream.close()
                    continue
                if key.data == "stdout":
                    if len(output) + len(chunk) > MAX_OUTPUT_BYTES:
                        raise ValueError("Status line stdout exceeds the 64 KiB limit.")
                    output.extend(chunk)
                else:
                    stderr_size += len(chunk)
                    if stderr_size > MAX_OUTPUT_BYTES:
                        raise ValueError("Status line stderr exceeds the 64 KiB limit.")
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise ValueError("The status line command timed out.")
        try:
            code = process.wait(timeout=remaining)
        except subprocess.TimeoutExpired:
            raise ValueError("The status line command timed out.") from None
        return code, bytes(output)
    except BaseException:
        _stop(process)
        raise
    finally:
        selector.close()
        for stream in (process.stdin, process.stdout, process.stderr):
            stream.close()


def render_via_command(
    snapshot: dict, width: int, height: int, color: bool, config_path: Path | None = None,
) -> str:
    """Send JSON through stdin and return bounded UTF-8 ANSI output without trailing newlines."""
    if not isinstance(snapshot, dict):
        raise ValueError("The status line requires a snapshot object.")
    if any(isinstance(value, bool) or not isinstance(value, int) or value <= 0 for value in (width, height)):
        raise ValueError("Status line terminal width and height must be positive integers.")
    if not isinstance(color, bool):
        raise ValueError("The status line color setting must be true or false.")
    settings = load_status_settings(config_path)
    protocol = {"version": 1, "session": snapshot, "terminal": {"columns": width, "rows": height, "color": color}}
    try:
        payload = (json.dumps(protocol, ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")
    except (TypeError, ValueError, UnicodeEncodeError):
        raise ValueError("Could not encode the status line snapshot as UTF-8 JSON.") from None
    code, output = _run_bounded(settings["command"], payload, settings["timeout_seconds"])
    if code != 0:
        # Do not expose raw stderr or argv, which may contain credentials.
        raise ValueError(f"The status line command failed with exit code {code}.")
    try:
        return output.decode("utf-8").rstrip("\r\n")
    except UnicodeDecodeError:
        raise ValueError("Status line stdout is not valid UTF-8.") from None
