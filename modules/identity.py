"""
מנוע זיהוי (identity) — חישוב מפתח-זהות לפי מנגנונים מדורגים.

גנרי לחלוטין: מקבל את המנגנונים כקלט (המשתמש מרכיב אותם במסך הבחירה),
ואינו מקבע שום צירוף שדות. אותו מפתח משרת שלושה שימושים: dedup פנימי,
איתור רשומה קיימת ב-DB, ועמודת `__נמצא_לפי`.

מנגנון = רשימת שמות-API של שדות שיחד מרכיבים מפתח. המנגנונים מסודרים לפי
עדיפות (1→N); הראשון שכל שדותיו מלאים — מנצח. רשומה שאף מנגנון לא תפס
מקבלת key=None (סימון לטיפול ידני).
"""
from __future__ import annotations

import re
from dataclasses import dataclass

_WS = re.compile(r"\s+")
_SEP = "\x1f"  # מפריד פנימי בין רכיבי מפתח מורכב (לא מופיע בערכים אמיתיים)


@dataclass
class KeyResult:
    """תוצאת חישוב מפתח לרשומה."""
    key: str | None              # None = אף מנגנון לא תפס (כל שדותיו לא מלאים)
    mechanism_index: int | None  # אינדקס המנגנון שתפס (0-based) — לעמודת __נמצא_לפי
    fields_used: list[str] | None


def normalize(value: object) -> str:
    """נירמול מינימלי לערך: חיתוך רווחים בקצוות, כיווץ רווחים פנימיים, ו-casefold."""
    return _WS.sub(" ", str(value if value is not None else "").strip()).casefold()


def compute_key(record: dict[str, object], mechanisms: list[list[str]]) -> KeyResult:
    """
    מחשב מפתח-זהות לרשומה לפי המנגנונים, בסדר עדיפות.

    record: ערכי הרשומה לפי שם-API ({api: value}).
    mechanisms: רשימה מסודרת של מנגנונים (כל מנגנון = רשימת שמות-API), מופעלים בלבד.

    מחזיר את המנגנון הראשון שכל שדותיו מלאים (אחרי נירמול); אחרת key=None.
    """
    for i, fields in enumerate(mechanisms):
        values = [normalize(record.get(f, "")) for f in fields]
        if all(values):  # כל שדות המנגנון מלאים → מפתח תקף
            return KeyResult(key=_SEP.join(values), mechanism_index=i, fields_used=list(fields))
    return KeyResult(key=None, mechanism_index=None, fields_used=None)
