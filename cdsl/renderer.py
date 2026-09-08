"""Render aligned Codex status using CCSL 1.0.27 colors and graphs."""

from __future__ import annotations

import math
import os
import re
import unicodedata
from contextvars import ContextVar
from datetime import datetime, timedelta, timezone
from pathlib import PurePath
from . import ccsl_render


JST = timezone(timedelta(hours=9))
_ESCAPES = re.compile(r"\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)|\x1b\[[0-?]*[ -/]*[@-~]")
_CONTROLS = re.compile(r"[\x00-\x1f\x7f-\x9f]")
_PERMISSION_ORANGE = "\x1b[38;2;255;193;7m"
_HINT_GRAY = "\x1b[38;5;245m"
_COMPATIBILITY = ContextVar("cdsl_render_compatibility", default=False)
_ASCII_GRAPH = str.maketrans({"▁": "_", "▂": ".", "▃": ":", "▄": "-",
                             "▅": "=", "▆": "+", "▇": "*", "█": "#", "▒": ".", "─": "_"})


def terminal_compatibility(environ: dict | None = None) -> bool:
    """Use conservative output for legacy terminals, with an explicit override."""
    env = os.environ if environ is None else environ
    mode = env.get("CDSL_RENDER_MODE", "auto").strip().lower()
    if mode not in {"auto", "ascii", "unicode"}:
        raise ValueError("CDSL_RENDER_MODE must be auto, ascii, or unicode.")
    if mode != "auto":
        return mode == "ascii"
    term = env.get("TERM", "").lower()
    color_term = env.get("COLORTERM", "").lower()
    if color_term in {"truecolor", "24bit"} or "256color" in term or "direct" in term:
        return False
    return (not term or term.startswith("vt")
            or term in {"ansi", "dumb", "linux", "xterm", "xterm-color", "screen", "screen-bce", "tmux", "rxvt"})


def _text(value: object, fallback: str = "") -> str:
    """Remove terminal controls from session-provided text."""
    if value is None:
        return fallback
    return _CONTROLS.sub("", _ESCAPES.sub("", str(value))) or fallback


def _number(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
        return number if math.isfinite(number) and number >= 0 else None
    except (TypeError, ValueError, OverflowError):
        return None


def _date(value: object) -> datetime | None:
    try:
        if isinstance(value, datetime):
            result = value
        elif isinstance(value, (int, float)) and not isinstance(value, bool):
            result = datetime.fromtimestamp(value, timezone.utc)
        elif isinstance(value, str):
            result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        else:
            return None
        return result.replace(tzinfo=JST) if result.tzinfo is None else result
    except (ValueError, OverflowError, OSError):
        return None


def _timeline(value: object) -> list[float]:
    if not isinstance(value, (list, tuple)):
        return []
    return [_number(item) or 0 for item in value]


def _context(snapshot: dict, now: datetime) -> dict:
    window = _number(snapshot.get("context_window"))
    session_reset = _date(snapshot.get("session_reset_at"))
    weekly_reset = _date(snapshot.get("weekly_reset_at"))
    session_window = (_number(snapshot.get("session_window_minutes")) or 300) * 60
    weekly_window = (_number(snapshot.get("weekly_window_minutes")) or 10080) * 60

    def position(reset: datetime | None, seconds: float) -> float | None:
        if reset is None:
            return None
        return max(0, min(1, 1 - (reset - now).total_seconds() / seconds))

    session_position = position(session_reset, session_window)
    session_range = None
    if session_reset is not None:
        start = (session_reset - timedelta(seconds=session_window)).astimezone(JST)
        end = session_reset.astimezone(JST)
        session_range = (f"{start.hour}:{start.minute:02d}", f"{end.hour}:{end.minute:02d}")
    cache_ratio = min(100, (_number(snapshot.get("cache_ratio")) or 0) * 100)
    directory = _text(snapshot.get("cwd"), ".")
    return {
        "model": _text(snapshot.get("model"), "Codex"),
        "current_dir": _text(snapshot.get("current_dir")) or PurePath(directory).name or directory,
        "git_branch": _text(snapshot.get("git_branch")),
        "modified_files": int(_number(snapshot.get("modified_files")) or 0),
        "context_size": int(window or 0),
        "cache_ratio": cache_ratio,
        "burn_timeline": _timeline(snapshot.get("session_timeline")),
        "burn_current_pos": session_position,
        "api_session_range": session_range,
        "weekly_timeline": _timeline(snapshot.get("weekly_timeline")),
        "weekly_current_pos": position(weekly_reset, weekly_window),
    }


def _clusters(text: str) -> list[tuple[str, int]]:
    """Group combining characters and emoji into terminal cells."""
    result = []
    joined = False
    compatibility = _COMPATIBILITY.get()
    for char in text:
        if result and (unicodedata.combining(char) or char in ("\ufe0e", "\ufe0f", "\u200d") or joined):
            previous, size = result[-1]
            if joined and compatibility:
                # Some legacy fonts display ZWJ components separately.
                size += 2 if unicodedata.east_asian_width(char) in ("W", "F", "A") else 1
            elif char == "\ufe0f" or joined and unicodedata.east_asian_width(char) in ("W", "F"):
                size = max(size, 2)
            result[-1] = (previous + char, size)
        else:
            wide = unicodedata.east_asian_width(char) in (("W", "F", "A") if compatibility else ("W", "F"))
            result.append((char, 2 if wide else 1))
        joined = char == "\u200d"
    return result


def display_width(text: str) -> int:
    """Measure visible width, including CJK, combining marks, and common emoji."""
    return sum(size for _, size in _clusters(_ESCAPES.sub("", text)))


def _clip(text: str, width: int) -> str:
    if display_width(text) <= width:
        return text
    if width <= 0:
        return ""
    result = []
    used = 0
    for cluster, size in _clusters(text):
        if used + size > width - 1:
            break
        result.append(cluster)
        used += size
    return "".join(result) + ("." if _COMPATIBILITY.get() else "…")


def _paint(text: str, color: str, colors) -> str:
    return color + text + colors.RESET


def _fit_ansi(text: str, width: int) -> str:
    """Fit narrow output without splitting ANSI sequences or combining marks."""
    if display_width(text) <= width:
        return text
    parts = []
    used = 0
    position = 0
    for match in _ESCAPES.finditer(text):
        for cluster, size in _clusters(text[position:match.start()]):
            if used + size > width - 1:
                return "".join(parts) + ("." if _COMPATIBILITY.get() else "…")
            parts.append(cluster)
            used += size
        parts.append(match.group())
        position = match.end()
    for cluster, size in _clusters(text[position:]):
        if used + size > width - 1:
            return "".join(parts) + ("." if _COMPATIBILITY.get() else "…")
        parts.append(cluster)
        used += size
    return "".join(parts)


def _header(context: dict, width: int) -> str:
    """Prioritize the actual branch name over long directory names."""
    colors = ccsl_render.Colors
    model = ccsl_render.shorten_model_name(context["model"])
    show_badge = context["context_size"] >= 1_000_000 and ccsl_render.should_show_1m_badge(context["model"], context["context_size"])
    if show_badge:
        model += "(1M)"
    branch, directory = context["git_branch"], context["current_dir"]

    def build(model_size, branch_size, directory_size, icons=True, modified=True, separator=" | "):
        icons = icons and not _COMPATIBILITY.get()
        model_text = _clip(model, model_size)
        if show_badge and model_text.endswith("(1M)"):
            model_text = model_text[:-4] + colors.BRIGHT_MAGENTA + "(1M)" + colors.BRIGHT_YELLOW
        parts = [_paint("[" + model_text + "]", colors.BRIGHT_YELLOW, colors)]
        if directory_size:
            parts.append(_paint(("📁 " if icons else "") + _clip(directory, directory_size), colors.BRIGHT_CYAN, colors))
        if branch:
            text = ("🌿 " if icons else "") + _clip(branch, branch_size)
            if modified and context["modified_files"]:
                text += f" {colors.BRIGHT_YELLOW}M{context['modified_files']}"
            parts.append(_paint(text, colors.BRIGHT_GREEN, colors))
        return separator.join(parts)

    for options in (
        (width, 24, 24, True, True, " | "),
        (24, 24, 10, True, True, " | "),
        (24, 24, 0 if branch else 12, True, True, " | "),
        (16, 16, 0 if branch else 8, False, False, " "),
    ):
        line = build(*options)
        if display_width(line) <= width:
            return line
    if branch:
        model_size = max(1, min(display_width(model), width // 3, width - min(4, display_width(branch)) - 3))
        return build(model_size, max(1, width - model_size - 3), 0, False, False, " ")
    return _paint("[" + _clip(model, max(1, width - 2)) + "]", colors.BRIGHT_YELLOW, colors)


def _badge(value: float | None, available: bool | None, context=False) -> str:
    colors = ccsl_render.Colors
    if value is None:
        content = "N/A" if available is False else "--"
        color = colors.BRIGHT_WHITE
    else:
        percentage = int(min(100, value))
        content = f"{percentage:2d}%"
        color = ccsl_render.get_percentage_color(percentage) if context else ccsl_render._get_utilization_color(percentage)
        if context and percentage >= 85:
            color = colors.BG_RED + colors.BRIGHT_WHITE + colors.BOLD
    return _paint("[" + content + "]", color, colors)


def _remaining(reset: object, now: datetime) -> str | None:
    date = _date(reset)
    if date is None:
        return None
    seconds = max(0, int((date - now).total_seconds()))
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes}m"
    if minutes < 1440:
        return f"{minutes // 60}h{minutes % 60:02d}m"
    return f"{minutes // 1440}d{minutes // 60 % 24}h{minutes % 60:02d}m"


def _detail(items: list[tuple[str, str]], width: int, colors) -> str:
    """Keep numbers first and append details only when they fit."""
    if width <= 0:
        return ""
    result = ""
    for index, (text, color) in enumerate(items):
        if index == 0:
            result = _paint(_clip(text, width), color, colors)
        elif display_width(result) + 1 + display_width(text) <= width:
            result += " " + _paint(text, color, colors)
    return result


def _metric_rows(snapshot: dict, context: dict, width: int, now: datetime) -> list[str]:
    colors = ccsl_render.Colors
    if width >= 60:
        labels, label_width, graph_max, detail_goal = ("Context:", "Session:", "Weekly:"), 9, 20, 25
    elif width >= 35:
        labels, label_width, graph_max, detail_goal = ("C:", "S:", "W:"), 3, 12, 14
    else:
        labels, label_width, graph_max, detail_goal = ("C:", "S:", "W:"), 3, 8, 6
    if width < 9:
        # Keep the closing bracket at width 10, including the left padding.
        label_width = 2
    graph_width = min(graph_max, max(1, width - label_width - 8 - detail_goal)) if width >= 14 else 0
    graph_separator = " " if graph_width else ""
    detail_width = max(0, width - label_width - graph_width - len(graph_separator) - 7)
    percentage = _number(snapshot.get("context_percent"))
    tokens, window = _number(snapshot.get("context_tokens")), _number(snapshot.get("context_window"))
    if percentage is None and tokens is not None and window:
        percentage = tokens / window * 100
    values = (percentage, _number(snapshot.get("session_used_percent")), _number(snapshot.get("weekly_used_percent")))
    available = (None, snapshot.get("session_limit_available"), snapshot.get("weekly_limit_available"))
    graphs = []
    for index in range(3):
        if graph_width == 0:
            graph = ""
        elif index == 0 and percentage is not None:
            graph = ccsl_render.get_progress_bar(min(100, percentage), width=graph_width)
        elif index and context["burn_timeline" if index == 1 else "weekly_timeline"]:
            timeline = context["burn_timeline" if index == 1 else "weekly_timeline"]
            current = context["burn_current_pos" if index == 1 else "weekly_current_pos"]
            graph = ccsl_render.create_sparkline(timeline, width=graph_width, current_pos=current)
        else:
            graph = ""
        if _COMPATIBILITY.get():
            # Block/shade glyphs can have different cell widths on CJK terminals.
            graph = graph.translate(_ASCII_GRAPH)
        missing = graph_width - display_width(graph)
        if missing > 0:
            graph += _paint(("_" if _COMPATIBILITY.get() else "─") * missing, colors.DARK_GRAY, colors)
        graphs.append(graph)
    token_format = ccsl_render.format_token_count if width >= 60 else ccsl_render.format_token_count_short
    compact_tokens = token_format(int(tokens)) if tokens is not None else "--"
    compact_window = token_format(int(window)) if window else "--"
    context_detail = compact_tokens + "/" + compact_window
    if display_width(context_detail) > detail_width and width < 60:
        context_detail = compact_tokens
    context_items = [(context_detail, colors.BRIGHT_WHITE)]
    if context["cache_ratio"] >= 50:
        icon = "" if _COMPATIBILITY.get() else "♻️ "
        context_items.append((f"{icon}{int(context['cache_ratio'])}% cached", colors.BRIGHT_GREEN))
    session_tokens = _number(snapshot.get("session_tokens"))
    session_detail = ccsl_render.format_token_count_short(int(session_tokens)) if session_tokens is not None else ("N/A" if available[1] is False else "--")
    if width >= 60 and session_tokens is not None:
        session_detail += " token"
    session_items = [(session_detail, colors.BRIGHT_WHITE)]
    if context["api_session_range"]:
        start, end = context["api_session_range"]
        session_items.append((f"({start}-{end})", colors.BRIGHT_GREEN))
    weekly_detail = _remaining(snapshot.get("weekly_reset_at"), now) or ("N/A" if available[2] is False else "--")
    weekly_items = [(weekly_detail, colors.BRIGHT_WHITE)]
    rows = []
    for index, items in enumerate((context_items, session_items, weekly_items)):
        label_color = colors.BRIGHT_CYAN
        if index == 0 and percentage is not None and percentage >= 85:
            label_color = colors.BG_RED + colors.BRIGHT_WHITE + colors.BOLD
        label = _paint(labels[index], label_color, colors) + " " * (label_width - display_width(labels[index]))
        badge = _badge(values[index], available[index], context=index == 0)
        line = label + graphs[index] + graph_separator + badge
        if detail_width:
            line += " " + _detail(items, detail_width, colors)
        rows.append(line)
    return rows


def _permission_line(snapshot: dict, width: int) -> str:
    colors = ccsl_render.Colors
    mode = _text(snapshot.get("permission_mode")) if isinstance(snapshot.get("permission_mode"), str) else ""
    if not mode:
        sandbox = snapshot.get("sandbox_policy")
        if isinstance(sandbox, dict):
            sandbox = sandbox.get("type")
        mode = {"read-only": "Read Only", "workspace-write": "Workspace", "danger-full-access": "Full Access"}.get(sandbox, "unknown") if isinstance(sandbox, str) else "unknown"
    approval = _text(snapshot.get("approval_mode")) if isinstance(snapshot.get("approval_mode"), str) else ""
    if not approval:
        policy = snapshot.get("approval_policy")
        approval = {"on-request": "Ask for approval", "never": "Never", "on-failure": "On failure", "untrusted": "Untrusted"}.get(policy, "unknown") if isinstance(policy, str) else "unknown"
        if policy == "on-request" and snapshot.get("approvals_reviewer") == "auto_review":
            approval = "Approve for me"
    text = mode if mode == approval == "unknown" else mode + " | " + approval
    keys = snapshot.get("permission_cycle_keys")
    if isinstance(keys, list) and keys and isinstance(keys[0], str) and _text(keys[0]):
        key = _text(keys[0])
        hints = (f"({key} for cycle)", f"({key})")
    elif keys == []:
        hints = ("(/keymap to set cycle key)", "(set /keymap)")
    else:
        hints = ("(/keymap to check cycle key)", "(check /keymap)")
    short_mode = {"Custom permissions": "Custom", "Workspace write": "Workspace"}.get(mode, mode)
    short_approval = {"Ask for approval": "Ask", "Approve for me": "Auto review"}.get(approval, approval)
    short_text = short_mode if mode == approval == "unknown" else short_mode + " | " + short_approval
    variants = [("Permissions: ", text), ("Permissions: ", short_text)]
    if width < 50:
        variants.append(("P: ", short_text))
    for hint in hints:
        for prefix, value in variants:
            if display_width(prefix + value + " " + hint) <= width:
                # Keep the hint beside the value instead of at a distant pane edge.
                return (_paint(prefix, _PERMISSION_ORANGE, colors)
                        + _paint(value, colors.BRIGHT_WHITE, colors) + " "
                        + _paint(hint, _HINT_GRAY, colors))
    prefix, value = variants[-1]
    hint = hints[-1]
    remaining = width - display_width(prefix + " " + hint)
    if remaining >= 4:
        return (_paint(prefix, _PERMISSION_ORANGE, colors)
                + _paint(_clip(value, remaining), colors.BRIGHT_WHITE, colors) + " "
                + _paint(hint, _HINT_GRAY, colors))
    prefix, text = next(((p, value) for p, value in variants
                         if display_width(p + value) <= width), variants[-1])
    return (_paint(prefix, _PERMISSION_ORANGE, colors)
            + _paint(_clip(text, width - len(prefix)), colors.BRIGHT_WHITE, colors))


def render(snapshot: dict, width: int = 80, color: bool = True, compatibility: bool = False) -> str:
    """Render five CCSL-style rows without a trailing newline.

    ``cache_ratio`` uses 0..1; utilization uses 0..100. Timestamps accept
    ISO 8601 or epoch seconds and display in JST. ``now`` fixes render time.
    Unavailable limits show ``N/A``; pending values show ``--``.
    Permission labels describe settings without changing them.
    Compatibility output uses ASCII graphs and basic ANSI colors.
    """
    if not isinstance(compatibility, bool):
        raise ValueError("The compatibility setting must be true or false.")
    if not isinstance(snapshot, dict):
        snapshot = {}
    width = max(10, int(_number(width) or 80)) - 2
    now = _date(snapshot.get("now")) or datetime.now(timezone.utc)
    context = _context(snapshot, now)
    token = _COMPATIBILITY.set(compatibility)
    try:
        lines = [_header(context, width), *_metric_rows(snapshot, context, width, now), _permission_line(snapshot, width)]
        output = "\n".join(f"\033[0m\033[1;97m  {_fit_ansi(line, width)}\033[0m" for line in lines)
    finally:
        _COMPATIBILITY.reset(token)
    if compatibility:
        output = (output.replace(_PERMISSION_ORANGE, "\x1b[1;33m")
                  .replace(_HINT_GRAY, "\x1b[37m")
                  .replace(ccsl_render.Colors.DARK_GRAY, "\x1b[2;37m")
                  .replace(ccsl_render.Colors.FUTURE_GRAY, "\x1b[2;37m"))
    if not color or os.environ.get("NO_COLOR") or os.environ.get("STATUSLINE_NO_COLOR"):
        return _ESCAPES.sub("", output)
    return output
