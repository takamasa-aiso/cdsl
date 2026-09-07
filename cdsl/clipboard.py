"""Pass a Windows clipboard image to Codex only when the user presses Ctrl+v."""

from __future__ import annotations

import base64
import binascii
import json
import os
from pathlib import Path
import platform
import re
import shlex
import shutil
import subprocess
import tempfile
import uuid


MAX_IMAGE_BYTES = 32 * 1024 * 1024
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
POWERSHELL_SCRIPT = """$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
$clipImage = [System.Windows.Forms.Clipboard]::GetImage()
if ($null -eq $clipImage) { exit 3 }
$clipBuffer = New-Object System.IO.MemoryStream
try {
    $clipImage.Save($clipBuffer, [System.Drawing.Imaging.ImageFormat]::Png)
    if ($clipBuffer.Length -gt 33554432) { exit 4 }
    [Console]::Out.Write([Convert]::ToBase64String($clipBuffer.ToArray()))
} finally {
    $clipBuffer.Dispose()
    $clipImage.Dispose()
}
"""
_OWNED_NAME = re.compile(r"cdsl-[A-Za-z0-9_-]{1,128}\Z")
_PANE_ID = re.compile(r"%[0-9]{1,12}\Z")


class _ClipboardFailure(Exception):
    pass


def _powershell_executable() -> str | None:
    windows_or_wsl = (
        os.name == "nt"
        or "microsoft" in platform.release().lower()
        or bool(os.environ.get("WSL_INTEROP") or os.environ.get("WSL_DISTRO_NAME"))
    )
    return shutil.which("powershell.exe") if windows_or_wsl else None


def _tmux(socket: str, *arguments: str, **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["tmux", "-L", socket, "-f", "/dev/null", *arguments],
        check=False, capture_output=True, timeout=2, **kwargs,
    )


def _run_target(run_dir: Path, target_pane: str) -> tuple[str, str] | None:
    if not isinstance(target_pane, str) or _PANE_ID.fullmatch(target_pane) is None:
        return None
    try:
        if (run_dir / "exit-code").exists():
            return None
        with (run_dir / "started.json").open("rb") as stream:
            raw = stream.read(16385)
        if len(raw) > 16384:
            return None
        state = json.loads(raw)
        if not isinstance(state, dict):
            return None
        socket, session = state.get("socket"), state.get("session")
        if not all(isinstance(value, str) and _OWNED_NAME.fullmatch(value) for value in (socket, session)):
            return None
        return socket, session
    except (OSError, ValueError, UnicodeDecodeError):
        return None


def _valid_target(socket: str, session: str, pane: str) -> bool:
    try:
        result = _tmux(
            socket, "display-message", "-p", "-t", f"{session}:0.0",
            "#{session_name}\t#{pane_id}\t#{pane_dead}",
        )
        return result.returncode == 0 and result.stdout.decode("utf-8").strip().split("\t") == [session, pane, "0"]
    except (OSError, ValueError, UnicodeDecodeError, subprocess.TimeoutExpired):
        return False


def _fallback(socket: str, session: str, pane: str, *, report: bool = False) -> int:
    # Confirm that the pane is still the same after reading the clipboard.
    if not _valid_target(socket, session, pane):
        return 1
    try:
        result = _tmux(socket, "send-keys", "-t", pane, "C-v")
        if result.returncode:
            return 1
    except (OSError, subprocess.TimeoutExpired):
        return 1
    if report:
        try:
            _tmux(socket, "display-message", "-t", pane, "CDSL: Could not paste the image; forwarded Ctrl+v to Codex.")
        except (OSError, subprocess.TimeoutExpired):
            pass
    return 0


def _read_windows_image(executable: str) -> bytes | None:
    result = subprocess.run(
        [executable, "-NoProfile", "-NonInteractive", "-STA", "-Command", POWERSHELL_SCRIPT],
        check=False, capture_output=True, timeout=15,
    )
    if result.returncode == 3:
        return None
    if result.returncode:
        raise _ClipboardFailure()
    encoded = result.stdout.strip()
    if not encoded or len(encoded) > ((MAX_IMAGE_BYTES + 2) // 3) * 4:
        raise _ClipboardFailure()
    try:
        image = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error) as error:
        raise _ClipboardFailure() from error
    if len(image) > MAX_IMAGE_BYTES or not image.startswith(PNG_SIGNATURE):
        raise _ClipboardFailure()
    return image


def _save_image(image: bytes) -> Path:
    descriptor, name = tempfile.mkstemp(prefix="codex-clipboard-cdsl-", suffix=".png")
    path = Path(name).absolute()
    try:
        with os.fdopen(descriptor, "wb") as stream:
            os.fchmod(stream.fileno(), 0o600)
            stream.write(image)
            stream.flush()
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    return path


def _discard_image(path: Path | None) -> None:
    if path is not None:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass


def _discard_buffer(socket: str, name: str) -> None:
    try:
        _tmux(socket, "delete-buffer", "-b", name)
    except (OSError, subprocess.TimeoutExpired):
        pass


def paste_image(run_dir: Path, target_pane: str) -> int:
    """Paste the PNG path once, without submitting input or printing image contents.

    Retain successful PNG files for asynchronous reads and session resume.
    If no image is available or retrieval fails, forward Ctrl+v to the same pane.
    """
    target = _run_target(Path(run_dir), target_pane)
    if target is None:
        return 1
    socket, session = target
    if not _valid_target(socket, session, target_pane):
        return 1
    executable = _powershell_executable()
    if executable is None:
        return _fallback(socket, session, target_pane)
    path = None
    buffer_name = f"cdsl-clipboard-{uuid.uuid4().hex}"
    buffer_attempted = False
    try:
        image = _read_windows_image(executable)
        if image is None:
            return _fallback(socket, session, target_pane)
        path = _save_image(image)
        # The Codex path parser accepts POSIX shell quoting.
        pasted_path = shlex.quote(str(path)).encode("utf-8")
        buffer_attempted = True
        loaded = _tmux(socket, "load-buffer", "-b", buffer_name, "-", input=pasted_path)
        if loaded.returncode or not _valid_target(socket, session, target_pane):
            raise _ClipboardFailure()
        pasted = _tmux(socket, "paste-buffer", "-p", "-d", "-b", buffer_name, "-t", target_pane)
        if pasted.returncode:
            raise _ClipboardFailure()
        return 0
    except (OSError, ValueError, subprocess.TimeoutExpired, _ClipboardFailure):
        if buffer_attempted:
            _discard_buffer(socket, buffer_name)
        _discard_image(path)
        return _fallback(socket, session, target_pane, report=True)
