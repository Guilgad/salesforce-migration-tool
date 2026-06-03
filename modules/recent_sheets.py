"""
זיכרון מקומי של גיליונות שחוברו לאחרונה (MRU — Most Recently Used), פר-תפקיד.

נשמר בקובץ JSON מקומי (ב-.gitignore), כך שהרשימה שורדת רענון/סגירה של האפליקציה.
לכל תפקיד (template / db / soql) רשימה נפרדת, אחרון-ראשון, עד `_MAX` פריטים.
"""
from __future__ import annotations

import json
import time

from config import settings

_MAX = 5


def load() -> dict[str, list[dict]]:
    """טוען את כל הזיכרון. חסין לקובץ חסר/פגום (מחזיר {})."""
    try:
        with open(settings.RECENT_SHEETS_FILE, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def recent_for(role: str) -> list[dict]:
    """רשימת הגיליונות האחרונים לתפקיד נתון (אחרון-ראשון). כל פריט: id/name/ts."""
    items = load().get(role, [])
    return items if isinstance(items, list) else []


def remember(role: str, sheet_id: str, name: str) -> None:
    """רושם גיליון שחובר בהצלחה: מעלה לראש הרשימה, מסיר כפילות לפי id, וגוזם ל-_MAX."""
    if not sheet_id:
        return
    data = load()
    items = [x for x in data.get(role, []) if isinstance(x, dict) and x.get("id") != sheet_id]
    items.insert(0, {"id": sheet_id, "name": name or sheet_id, "ts": time.time()})
    data[role] = items[:_MAX]
    try:
        with open(settings.RECENT_SHEETS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except OSError:
        pass  # כשל כתיבה לא קריטי — הזיכרון פשוט לא יישמר הפעם
