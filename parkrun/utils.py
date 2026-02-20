"""Shared time-parsing and formatting utilities."""


def parse_time_minutes(t: str) -> float | None:
    """Parse 'MM:SS' or 'H:MM:SS' into fractional minutes. Returns None on failure."""
    parts = str(t).split(":")
    try:
        if len(parts) == 2:
            return int(parts[0]) + int(parts[1]) / 60
        if len(parts) == 3:
            return int(parts[0]) * 60 + int(parts[1]) + int(parts[2]) / 60
    except (ValueError, TypeError):
        pass
    return None


def format_time(minutes: float) -> str:
    """Format fractional minutes as 'M:SS'."""
    total_seconds = round(minutes * 60)
    m, s = divmod(total_seconds, 60)
    return f"{m}:{s:02d}"
