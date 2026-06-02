"""
חיבור ל-Google Sheets דרך ה-service account, ובדיקת גישה למסך החיבור.

מספק את הלוגיקה של "נורות החיבור": לכל גיליון בודק אם ה-service account ניגש אליו
ובאיזו רמה (Editor/Viewer), ומחזיר סטטוס צבע (green/yellow/red) לפי הרמה הנדרשת.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

from config import settings


@dataclass
class AccessResult:
    """תוצאת בדיקת גישה גולמית מול Drive."""
    ok: bool                 # האם ה-service account הצליח לפתוח את הקובץ
    name: str | None
    can_edit: bool
    error: str | None = None


@dataclass
class ConnectionStatus:
    """סטטוס מוכן-לתצוגה לנורית החיבור."""
    color: str               # "green" | "yellow" | "red"
    message: str
    name: str | None = None


_credentials: Credentials | None = None


def get_credentials() -> Credentials:
    """טוען (פעם אחת) את מפתח ה-service account."""
    global _credentials
    if _credentials is None:
        _credentials = Credentials.from_service_account_file(
            str(settings.CREDENTIALS_FILE), scopes=settings.SCOPES
        )
    return _credentials


def service_account_email() -> str:
    return get_credentials().service_account_email


def _drive():
    return build("drive", "v3", credentials=get_credentials(), cache_discovery=False)


def extract_id(link_or_id: str) -> str:
    """מחלץ מזהה גיליון מקישור מלא, או מחזיר את הקלט כמו שהוא."""
    match = re.search(r"/d/([a-zA-Z0-9_-]+)", link_or_id or "")
    return match.group(1) if match else (link_or_id or "").strip()


def check_access(link_or_id: str) -> AccessResult:
    """בודק בפועל אם ה-service account ניגש לגיליון, ובאיזו רמה."""
    file_id = extract_id(link_or_id)
    if not file_id:
        return AccessResult(ok=False, name=None, can_edit=False, error="קישור ריק")
    try:
        f = (
            _drive()
            .files()
            .get(fileId=file_id, fields="name,capabilities(canEdit)", supportsAllDrives=True)
            .execute()
        )
        return AccessResult(ok=True, name=f.get("name"), can_edit=bool(f["capabilities"]["canEdit"]))
    except Exception as e:  # noqa: BLE001 — כל כשל = אין גישה, מדווח למשתמש
        return AccessResult(ok=False, name=None, can_edit=False, error=f"{type(e).__name__}: {e}")


def connection_status(link_or_id: str, needs_write: bool) -> ConnectionStatus:
    """
    מתרגם בדיקת גישה לסטטוס נורית, לפי הרמה הנדרשת:
      - אין גישה            -> 🔴
      - צריך כתיבה ואין      -> 🔴
      - צריך כתיבה ויש       -> 🟢
      - צריך קריאה ויש כתיבה -> 🟡 (עודף הרשאה)
      - צריך קריאה ויש קריאה -> 🟢
    """
    if not (link_or_id or "").strip():
        return ConnectionStatus(color="red", message="לא הוזן קישור")

    result = check_access(link_or_id)
    if not result.ok:
        return ConnectionStatus(
            color="red",
            message=f"אין גישה — שתף עם {service_account_email()}",
        )

    if needs_write:
        if result.can_edit:
            return ConnectionStatus(color="green", message="גישת Editor — מוכן", name=result.name)
        return ConnectionStatus(
            color="red", message="צריך הרשאת Editor (כרגע קריאה בלבד)", name=result.name
        )

    # צריך קריאה בלבד
    if result.can_edit:
        return ConnectionStatus(
            color="yellow", message="עודף הרשאה — מספיק Viewer לבטיחות", name=result.name
        )
    return ConnectionStatus(color="green", message="גישת Viewer — מוכן", name=result.name)
