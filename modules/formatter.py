"""
פירמוט ערכים מינימלי (v1) — תאריכים וטקסט בלבד.

טהור, נטול-I/O. דרך Google Sheets API כל ערך מגיע כמחרוזת, ולכן אי-אפשר להבחין
"תא-תאריך אמיתי" מ"טקסט" — `parse_date` מנסה לפרסר לפי פורמטים מוכרים; מה שלא
נפרסר מוחזר כ-None (הקורא — הוולידטור — מחליט אם זו בעיה).

מספרים/בוליאני/תרגום-פיקליסט מחוץ ל-v1 (ראה תוכנית הפיתוח).
"""
from __future__ import annotations

from datetime import datetime

# פורמטי-קלט מקובלים לתאריך. הראשון שמצליח מנצח. כולם → 'YYYY-MM-DD'.
_DATE_FORMATS = (
    "%Y-%m-%d",   # 2026-06-04
    "%d.%m.%Y",   # 04.06.2026 / 4.6.2026
    "%d/%m/%Y",   # 04/06/2026
    "%d-%m-%Y",   # 04-06-2026
    "%Y/%m/%d",   # 2026/06/04
)


def normalize_text(value) -> str:
    """חיתוך רווחים בקצוות; None → ''."""
    if value is None:
        return ""
    return str(value).strip()


def parse_date(value) -> str | None:
    """
    מחזיר 'YYYY-MM-DD' אם הערך ניתן לפירוש כתאריך, אחרת None.

    ריק/None → None (אין מה לפרסר; הקורא מחליט אם ריק = תקין).
    מנסה את הפורמטים ב-_DATE_FORMATS לפי הסדר; הראשון שמצליח מנצח.
    """
    text = normalize_text(value)
    if not text:
        return None
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None
