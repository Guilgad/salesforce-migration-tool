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

import re
from dataclasses import dataclass

# סטטוס ולידציה של עמודה (פרוסה 3)
STATUS_VALID = "valid"      # ✅ ה-API קיים במילון לאובייקט
STATUS_INVALID = "invalid"  # 🔴 API מולא אך לא קיים במילון
STATUS_MISSING = "missing"  # 🟡 אובייקט ממופה אבל אין API
STATUS_IGNORE = "ignore"    # ⚪ עמודת-תיאור/מפריד
STATUS_NO_DICT = "no_dict"  # ⚠️ האובייקט לא נמצא במילון (לא נשאל בשלב 1)

# שם-API בסיילספורס הוא אותיות/ספרות/קו-תחתון בלבד — משמש לחילוץ מתוך ערך מעוטר
_API_TOKEN = re.compile(r"[A-Za-z0-9_]+")


@dataclass
class TemplateColumn:
    """עמודה אחת בטמפלייט, כפי שחולצה משורות-הכותרת ומועשרת בשלבים."""
    index: int            # אינדקס העמודה בגיליון (0-based)
    block: str            # כותרת הבלוק (מועברת קדימה על-פני תאים ממוזגים)
    label: str            # שם העמודה בעברית (שורת ה-label)
    proposed_api: str     # שם ה-API המוצע (שורת ה-api); '' אם ריק
    # נקבעים בפרוסה 2 (assign_objects):
    object_api: str = ""  # אובייקט ה-SF שאליו שייכת העמודה; '' = לא ממופה
    ignored: bool = False  # עמודת-תיאור/מפריד שאינה נטענת
    # נקבעים בפרוסה 3 (validate_columns):
    clean_api: str = ""   # ה-API אחרי חילוץ מערך מעוטר ("Name (Campaign Name)"→"Name")
    status: str = ""      # אחד מקבועי STATUS_*


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


def assign_objects(
    columns: list[TemplateColumn],
    block_to_object: dict[str, str],
    wandering_overrides: dict[str, str],
) -> list[TemplateColumn]:
    """
    מצמיד לכל עמודה אובייקט SF (מעדכן את העמודות במקום ומחזיר אותן).

    - עמודת-תיאור/מפריד (בלי בלוק, או בלי תווית וגם בלי API) → ignored.
    - חריג נודד (תווית ב-wandering_overrides) → גובר על ברירת-המחדל של הבלוק.
    - אחרת → לפי מיפוי הבלוק. בלוק לא-ממופה → object_api נשאר '' (יסומן בולידציה).
    """
    for c in columns:
        if not c.block or (not c.label and not c.proposed_api):
            c.ignored = True
            c.object_api = ""
            continue
        if c.label in wandering_overrides:
            c.object_api = wandering_overrides[c.label]
        else:
            c.object_api = block_to_object.get(c.block, "")
    return columns


def normalize_api(raw: str) -> str:
    """
    מחלץ שם-API תקין מערך שעשוי להיות מעוטר.
    "Name (Campaign Name)" → "Name" · "Requested_Amount__c" → ללא שינוי · "" → "".
    """
    m = _API_TOKEN.match((raw or "").strip())
    return m.group(0) if m else ""


def validate_columns(
    columns: list[TemplateColumn],
    dictionary: dict,
) -> list[TemplateColumn]:
    """
    מסווג כל עמודה מול מילון השדות (מעדכן במקום ומחזיר).

    dictionary: dict[object_api → ObjectInfo] (מ-field_dictionary.ParseResult.objects).
    """
    field_apis = {
        obj_api: {f.api for f in obj.fields} for obj_api, obj in dictionary.items()
    }
    for c in columns:
        if c.ignored:
            c.status = STATUS_IGNORE
            c.clean_api = ""
            continue
        c.clean_api = normalize_api(c.proposed_api)
        if c.object_api not in field_apis:
            c.status = STATUS_NO_DICT
        elif not c.clean_api:
            c.status = STATUS_MISSING
        elif c.clean_api in field_apis[c.object_api]:
            c.status = STATUS_VALID
        else:
            c.status = STATUS_INVALID
    return columns


def candidates_for(object_api: str, dictionary: dict) -> list:
    """רשימת שדות האובייקט מהמילון (ל-dropdown תיקון). ריק אם האובייקט לא במילון."""
    obj = dictionary.get(object_api)
    return list(obj.fields) if obj else []
