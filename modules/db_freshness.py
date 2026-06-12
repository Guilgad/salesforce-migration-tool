"""Standalone helper: Drive modifiedTime → freshness days/label."""
from __future__ import annotations
from datetime import datetime, timezone


def days_since_modified(modified_time_str: str) -> int | None:
    """
    Parse Drive modifiedTime ISO string (e.g. '2025-06-01T10:00:00Z').
    Returns full days elapsed (UTC), or None if empty/unparseable.
    """
    if not modified_time_str:
        return None
    try:
        dt = datetime.fromisoformat(modified_time_str.replace("Z", "+00:00"))
        return (datetime.now(timezone.utc) - dt).days
    except (ValueError, TypeError):
        return None


def freshness_label(days: int | None) -> str:
    """Convert day count to Hebrew display label."""
    if days is None:
        return ""
    if days == 0:
        return "🟢 עודכן היום"
    if days <= 3:
        return f"🟡 עודכן לפני {days} ימים"
    return f"⚠️ עודכן לפני {days} ימים — מומלץ לרענן"
