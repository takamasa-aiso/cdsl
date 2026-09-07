"""Colors, graphs, and number formatting derived from CCSL 1.0.27.

Source: https://github.com/usedhonda/statusline
Original: statusline.py (1.0.27)
Original SHA-256: 1bb95106e158ca8ea517256130e117915a10b1548f2b93f4a46171bd4390feda
Copyright (c) 2025 usedhonda
See THIRD_PARTY_NOTICES.md for attribution and the upstream MIT license.
See LICENSE at the repository root for the license terms.
"""

import re


class Colors:
    """Fixed ANSI palette; the renderer removes color at its output boundary."""
    BRIGHT_CYAN = '\x1b[1;96m'
    BRIGHT_MAGENTA = '\x1b[1;95m'
    BRIGHT_GREEN = '\x1b[1;92m'
    BRIGHT_YELLOW = '\x1b[1;93m'
    BRIGHT_RED = '\x1b[1;95m'
    BRIGHT_WHITE = '\x1b[1;97m'
    LIGHT_GRAY = '\x1b[1;97m'
    DIM_GREEN = '\x1b[32m'
    DIM_YELLOW = '\x1b[33m'
    DIM_RED = '\x1b[31m'
    BOLD = '\x1b[1m'
    BG_RED = '\x1b[41m'
    DARK_GRAY = '\x1b[38;5;237m'
    FUTURE_GRAY = '\x1b[38;5;242m'
    RESET = '\x1b[0m'



def format_token_count(tokens):
    """Format token count for display"""
    if tokens >= 1000000:
        return f"{tokens / 1000000:.1f}M"
    elif tokens >= 1000:
        return f"{tokens / 1000:.1f}K"
    return str(tokens)


def format_token_count_short(tokens):
    """Format token count for display (3 significant digits)"""
    if tokens >= 1000000:
        val = tokens / 1000000
        if val >= 100:
            return f"{round(val)}M"      # 100M, 200M
        else:
            return f"{val:.1f}M"         # 14.0M, 1.5M
    elif tokens >= 1000:
        val = tokens / 1000
        if val >= 100:
            return f"{round(val)}K"      # 332K, 500K
        else:
            return f"{val:.1f}K"         # 14.0K, 99.5K
    return str(tokens)


def get_percentage_color(percentage):
    """Get color based on percentage threshold"""
    if percentage >= 90:
        return '\033[1;91m'  # bright red
    elif percentage >= 80:
        return Colors.BRIGHT_YELLOW
    return Colors.BRIGHT_GREEN


def get_percentage_color_dim(percentage):
    """Get dim (non-bold) color for fractional progress bar segments"""
    if percentage >= 90:
        return Colors.DIM_RED
    elif percentage >= 80:
        return Colors.DIM_YELLOW
    return Colors.DIM_GREEN


def get_progress_bar(percentage, width=20):
    """Render context usage with a dim block for the fractional segment."""
    filled_exact = width * percentage / 100
    filled = int(filled_exact)
    fraction = filled_exact - filled
    has_fraction = fraction > 0.01 and filled < width
    color = get_percentage_color(percentage)
    dim_color = get_percentage_color_dim(percentage)
    bar = color + '█' * filled
    if has_fraction:
        bar += dim_color + '█'
        empty = width - filled - 1
    else:
        empty = width - filled
    bar += Colors.LIGHT_GRAY + '▒' * empty + Colors.RESET
    return bar


def create_sparkline(values, width=20, current_pos=None):
    """Create a compact sparkline graph.

    Args:
        values: List of numeric values to plot
        width: Display width in characters
        current_pos: Optional float 0.0-1.0 indicating current time position.
                     Segments after current_pos are rendered as future.
    """
    if not values:
        return ""

    # Use unicode block characters for sparkline
    chars = ["▁", "▂", "▃", "▄", "▅", "▆", "▇", "█"]

    data_width = min(width, len(values))

    # Calculate current segment boundary
    current_segment = data_width  # default: all segments are "past"
    if current_pos is not None:
        current_segment = int(current_pos * data_width)
        # Clamp to valid range
        current_segment = max(0, min(data_width, current_segment))

    max_val = max(values)
    min_val = min(values)

    if max_val == min_val:
        # All values are the same
        sparkline = ""
        for i in range(data_width):
            if i > current_segment:
                sparkline += Colors.FUTURE_GRAY + chars[0] + Colors.RESET
            elif max_val == 0:
                sparkline += Colors.LIGHT_GRAY + chars[0] + Colors.RESET
            else:
                sparkline += Colors.BRIGHT_GREEN + chars[4] + Colors.RESET
        return sparkline

    sparkline = ""
    step = len(values) / data_width if len(values) > data_width else 1

    for i in range(data_width):
        # Future segments (strictly after current)
        if i > current_segment:
            sparkline += Colors.FUTURE_GRAY + chars[0] + Colors.RESET
            continue

        idx = int(i * step) if step > 1 else i
        if idx < len(values):
            normalized = (values[idx] - min_val) / (max_val - min_val)
            char_idx = min(len(chars) - 1, int(normalized * len(chars)))

            # Color based on value
            if normalized > 0.7:
                color = Colors.BRIGHT_RED
            elif normalized > 0.4:
                color = Colors.BRIGHT_YELLOW
            else:
                color = Colors.BRIGHT_GREEN

            sparkline += color + chars[char_idx] + Colors.RESET

    return sparkline


def shorten_model_name(model):
    """Shorten model prefixes and redundant context-size suffixes."""
    # Normalize raw model IDs, such as "claude-opus-4-7[1m]" to "Opus 4.7".
    # Drop date suffixes, such as "claude-haiku-4-5-20251001" to "Haiku 4.5".
    m = re.match(r'^claude-([a-z]+)-(\d+(?:-\d+)?)(?:-\d{8})?(?:\[\d+m\])?$', model, re.IGNORECASE)
    if m:
        family = m.group(1).capitalize()
        version = m.group(2).replace('-', '.')
        model = f"{family} {version}"

    # Remove the "Claude " prefix.
    name = re.sub(r'^Claude\s+', '', model, flags=re.IGNORECASE)

    # Remove context-size suffixes such as "(1M context)" or "(200k context)".
    name = re.sub(r'\s*\([\d.]+[kKmM]?\s+context\)', '', name).strip()

    # Move leading versions after the model name: "3.5 Haiku" to "Haiku 3.5".
    m = re.match(r'^([\d.]+)\s+(Haiku|Sonnet|Opus|Fable)', name, re.IGNORECASE)
    if m:
        name = f"{m.group(2)} {m.group(1)}"

    return name


_NATIVE_1M_VERSIONS = ('4.5', '4-5', '4.6', '4-6', '4.7', '4-7', '4.8', '4-8')


def should_show_1m_badge(model, context_size):
    """Omit the 1M badge for models where it would be redundant."""
    if context_size <= 200000:
        return False
    normalized = model.lower() if model else ''
    if 'fable' in normalized:
        return False
    if ('opus' in normalized or 'sonnet' in normalized) and any(
        v in normalized for v in _NATIVE_1M_VERSIONS
    ):
        return False
    return True


def _get_utilization_color(pct):
    """Get color based on utilization percentage."""
    if pct >= 90:
        return f"{Colors.BG_RED}{Colors.BRIGHT_WHITE}"
    elif pct >= 75:
        return Colors.BRIGHT_RED
    elif pct >= 50:
        return Colors.BRIGHT_YELLOW
    return Colors.BRIGHT_GREEN
