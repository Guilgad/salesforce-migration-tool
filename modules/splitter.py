"""
splitter — פיצול שורות-טמפלייט לרשומות פר-אובייקט (המנוע, צד-הקלט של dedup).

טהור (בלי I/O): מקבל שורות-דאטה ועמודות ממופות, ומחזיר רשומות. גנרי — מקבץ עמודות
לפי `block`, וכל בלוק מייצר רשומה אחת לכל שורת-דאטה. כך שני בלוקי Contact (ראשי + נוסף)
הופכים לשתי רשומות Contact נפרדות לכל שורה. רשומה שכל ערכיה ריקים — מדולגת.

הפלט (`SplitRecord.values` כ-{clean_api: value}) הוא בדיוק הקלט ש-`dedup_engine` צורך.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from modules import mapper


@dataclass
class SplitRecord:
    """רשומה אחת שנגזרה מבלוק בשורת-טמפלייט."""
    object_api: str                          # האובייקט (למשל "Contact")
    block: str                               # הבלוק המקורי (מבחין ראשי מול נוסף)
    source_row: int                          # אינדקס השורה בגיליון (0-based) — ל-trace/write-back
    values: dict[str, str] = field(default_factory=dict)  # {clean_api: value}


def _cell(row: list[str], i: int) -> str:
    """תא לפי אינדקס, חסין לשורות 'קצרות' (תאים ריקים בסוף מושמטים ב-API)."""
    if 0 <= i < len(row) and row[i] is not None:
        return str(row[i]).strip()
    return ""


def split_object(
    object_api: str,
    rows: list[list[str]],
    columns: list[mapper.TemplateColumn],
    *,
    data_start_row: int,
) -> list[SplitRecord]:
    """
    מפצל את שורות-הדאטה לרשומות עבור אובייקט נתון.

    object_api:     האובייקט לפיצול (למשל "Contact").
    rows:           כל שורות הגיליון (כולל שורות-הכותרת).
    columns:        עמודות מאומתות (מ-mapper.validate_columns).
    data_start_row: השורה הראשונה של דאטה אמיתית (0-based).

    מחזיר רשומה לכל (בלוק × שורת-דאטה לא-ריקה), כשהבלוקים בסדר-הופעתם.
    כוללת שדות תקפים בלבד (STATUS_VALID עם clean_api) — אלה השדות הנטענים.
    """
    # עמודות נטענות של האובייקט, מקובצות לפי בלוק בסדר-הופעה
    blocks: dict[str, list[mapper.TemplateColumn]] = {}
    for c in columns:
        if c.object_api == object_api and c.status == mapper.STATUS_VALID and c.clean_api:
            blocks.setdefault(c.block, []).append(c)

    records: list[SplitRecord] = []
    for block, cols in blocks.items():
        for r in range(data_start_row, len(rows)):
            row = rows[r]
            values = {c.clean_api: _cell(row, c.index) for c in cols}
            if not any(values.values()):  # רשומה ריקה לחלוטין — מדלגים
                continue
            records.append(
                SplitRecord(
                    object_api=object_api,
                    block=block,
                    source_row=r,
                    values=values,
                )
            )
    return records
