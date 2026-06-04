"""
פתק-הערות חופשי של המשתמש (פאנל-צד).

נשמר בקובץ טקסט מקומי (ב-.gitignore), כך שהתוכן שורד רענון/סגירה של האפליקציה.
הכלי לעולם לא מוחק את הקובץ מיוזמתו — רק המשתמש, דרך תיבת-הטקסט.
"""
from __future__ import annotations

from config import settings


def load() -> str:
    """טוען את תוכן הפתק. חסין לקובץ חסר/פגום (מחזיר '')."""
    try:
        with open(settings.NOTES_FILE, encoding="utf-8") as f:
            return f.read()
    except (FileNotFoundError, OSError):
        return ""


def save(text: str) -> None:
    """שומר את תוכן הפתק. כשל-כתיבה לא קריטי (הפתק פשוט לא יישמר הפעם)."""
    try:
        with open(settings.NOTES_FILE, "w", encoding="utf-8") as f:
            f.write(text or "")
    except OSError:
        pass
