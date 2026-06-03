"""
מיפוי עמודות הטמפלייט לשדות סיילספורס (שלבים 2–3 בזרימה).

המודול נבנה בפרוסות:
  1. חילוץ עמודות   — קריאת שורות-הכותרת של הטמפלייט → רשימת עמודות מסודרת.   ← פרוסה זו
  2. מיפוי אובייקטים — בלוק→אובייקט SF + "עמודות נודדות".
  3. ולידציה        — סיווג כל עמודה מול מילון השדות + מועמדים ל-dropdown.

המנוע גנרי: מבנה שורות-הכותרת מגיע מ-`config.template_config` (ספציפי-לטמפלייט),
לא קשיח כאן.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class TemplateColumn:
    """עמודה אחת בטמפלייט, כפי שחולצה משורות-הכותרת."""
    index: int            # אינדקס העמודה בגיליון (0-based)
    block: str            # כותרת הבלוק (מועברת קדימה על-פני תאים ממוזגים)
    label: str            # שם העמודה בעברית (שורת ה-label)
    proposed_api: str     # שם ה-API המוצע (שורת ה-api); '' אם ריק


def _cell(row: list[str], i: int) -> str:
    """תא לפי אינדקס, חסין לשורות 'קצרות' (תאים ריקים בסוף מושמטים ב-API)."""
    if 0 <= i < len(row) and row[i] is not None:
        return str(row[i]).strip()
    return ""


def extract_columns(
    rows: list[list[str]],
    *,
    block_row: int,
    label_row: int,
    api_row: int,
) -> list[TemplateColumn]:
    """
    מחלץ את עמודות הטמפלייט משורות-הכותרת.

    - כותרת הבלוק (שורת block) דלילה (תאים ממוזגים) — מועברת קדימה עד הכותרת הבאה.
    - עמודות *לפני* הבלוק הראשון (block ריק) הן עמודות-תיאור — נשמרות עם block='',
      והשלב הבא יתעלם מהן.
    - מוחזרות כל העמודות עד לרוחב המרבי של שלוש שורות-הכותרת (כדי לשמר אינדקסים).
    """
    width = max(
        len(rows[block_row]) if block_row < len(rows) else 0,
        len(rows[label_row]) if label_row < len(rows) else 0,
        len(rows[api_row]) if api_row < len(rows) else 0,
    )
    block_src = rows[block_row] if block_row < len(rows) else []
    label_src = rows[label_row] if label_row < len(rows) else []
    api_src = rows[api_row] if api_row < len(rows) else []

    columns: list[TemplateColumn] = []
    current_block = ""
    for i in range(width):
        title = _cell(block_src, i)
        if title:
            current_block = title  # תחילת בלוק חדש — מכאן והלאה זה הבלוק
        columns.append(
            TemplateColumn(
                index=i,
                block=current_block,
                label=_cell(label_src, i),
                proposed_api=_cell(api_src, i),
            )
        )
    return columns
