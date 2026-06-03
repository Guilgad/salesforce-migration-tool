"""
output_writer — בניית גריד פלט מוכן-לטעינה (פרוסה טהורה, בלי I/O).

לוקח את החלטות ה-dedup (אנשים) ומרכיב גריד `list[list[str]]`: שתי שורות-כותרת
(עברית מעל API) ואז שורה לאדם. שני שלבים קריטיים לכל אדם:
  - קונסולידציה: מיזוג רשומות-החבר שהתמזגו לאותו אדם (ראשון-לא-ריק פר-שדה).
  - backfill: ל-Upsert בלבד — שדה שנשאר ריק ממולא מה-DB (upsert עם תא ריק *מוחק*
    דאטה בסיילספורס; מאומת). דאטת-טמפלייט גוברת, ה-DB ממלא חורים בלבד.

מבנה העמודות: עמודות לא-נטענות (`local_key`, `נמצא לפי`) משמאל, אחריהן הנטענות
(`Id` + שדות). תא "נמצא לפי" נצבע לפי איכות ההתאמה (🟢 מנגנון 1 / 🟡 מנגנון 2-3 /
🔴 ידני) — רשימת הצבעים מוחזרת לצד הגריד ל-sheets_io.color_cells.

הכתיבה בפועל לגיליון = פרוסת I/O נפרדת; כאן רק מבנה הגריד ורשימת הצבעים.
"""
from __future__ import annotations

from modules import dedup_engine, mapper

# עמודות לא-נטענות (תצוגה בלבד), בסדר שייכתב — לפני Id והשדות.
# כל ערך: (תווית עברית, שם-API). ל-"נמצא לפי" אין שדה SF → API ריק.
_DISPLAY_COLUMNS = [("מפתח פנימי", "local_key"), ("נמצא לפי", "")]
# העמודה הנטענת הראשונה: ה-Id (לאחריה עמודות-השדה הדינמיות).
_ID_COLUMN = ("מזהה", "Id")

# אינדקס עמודת "נמצא לפי" בגריד (col 1) ומספר שורות-הכותרת (לחישוב שורת-הנתונים).
_FOUND_BY_COL = 1
_HEADER_ROWS = 2

_MANUAL_TEXT = "בדיקה ידנית"


def _field_columns(
    columns: list[mapper.TemplateColumn], object_api: str
) -> list[tuple[str, str]]:
    """
    עמודות-השדה התקפות לאובייקט כזוגות (clean_api, label), בסדר-הופעה יציב
    ובלי כפילויות (התווית העברית נלקחת מהעמודה הראשונה לכל clean_api).
    """
    pairs: list[tuple[str, str]] = []
    seen: set[str] = set()
    for c in columns:
        if (
            c.object_api == object_api
            and c.status == mapper.STATUS_VALID
            and c.clean_api
            and c.clean_api not in seen
        ):
            seen.add(c.clean_api)
            pairs.append((c.clean_api, c.label))
    return pairs


def _consolidate(member_indices: list[int], record_values: list[dict], fields: list[str]) -> dict:
    """מיזוג רשומות-החבר לערך אחד פר-שדה: ראשון-לא-ריק מנצח."""
    merged: dict[str, str] = {}
    for f in fields:
        for mi in member_indices:
            val = str(record_values[mi].get(f, "") or "").strip()
            if val:
                merged[f] = val
                break
        merged.setdefault(f, "")
    return merged


def _found_by_cell(person: dedup_engine.PersonResult) -> tuple[str, str | None]:
    """
    טקסט וצבע לתא "נמצא לפי":
      - דו-משמעי / חסר-מפתח → טיפול ידני (🔴)
      - Upsert לפי מנגנון 1 → "1" (🟢)
      - Upsert לפי מנגנון 2/3 → "2"/"3" (🟡)
      - Insert חדש תקין → ריק, ללא צבע
    """
    if person.ambiguous or person.unkeyed:
        return _MANUAL_TEXT, "red"
    if person.action == dedup_engine.ACTION_UPSERT and person.found_by is not None:
        color = "green" if person.found_by == 0 else "yellow"
        return str(person.found_by + 1), color
    return "", None


def build_contacts_grid(
    dedup_result: dedup_engine.DedupResult,
    record_values: list[dict],
    columns: list[mapper.TemplateColumn],
    db_by_id: dict[str, dict],
    *,
    object_api: str = "Contact",
) -> tuple[list[list[str]], list[tuple[int, int, str]]]:
    """
    מרכיב גריד פלט: 2 שורות-כותרת (עברית מעל API) ואז שורה לכל אדם, ולצדו רשימת
    צבעים לתא "נמצא לפי".

    dedup_result:  פלט dedup_engine.deduplicate (אנשים + החלטות).
    record_values: אותה רשימת רשומות שהוזנה ל-deduplicate (אינדקסים תואמים ל-record_indices).
    columns:       עמודות מאומתות (mapper.validate_columns) — לקביעת עמודות-השדה.
    db_by_id:      רשומות DB מקוריות לפי Id ({Id: {api: value}}) — ל-backfill.

    מחזיר (grid, cell_colors):
      grid:        list[list[str]] — 2 שורות-כותרת + שורה לאדם.
      cell_colors: list[(row0, col0, color)] בקואורדינטות אבסולוטיות לתא "נמצא לפי".
    """
    field_pairs = _field_columns(columns, object_api)
    fields = [api for api, _label in field_pairs]

    # שתי שורות-כותרת: עברית מעל API. סדר: עמודות-תצוגה → Id → שדות.
    header_he = [he for he, _api in _DISPLAY_COLUMNS] + [_ID_COLUMN[0]] + [
        label for _api, label in field_pairs
    ]
    header_api = [api for _he, api in _DISPLAY_COLUMNS] + [_ID_COLUMN[1]] + fields
    grid: list[list[str]] = [header_he, header_api]
    cell_colors: list[tuple[int, int, str]] = []

    for i, person in enumerate(dedup_result.persons):
        merged = _consolidate(person.record_indices, record_values, fields)

        # backfill: ל-Upsert בלבד, שדה ריק → ערך מה-DB (מקורי)
        if person.action == dedup_engine.ACTION_UPSERT and person.sf_id:
            db_rec = db_by_id.get(person.sf_id, {})
            for f in fields:
                if not merged[f]:
                    merged[f] = str(db_rec.get(f, "") or "").strip()

        found_text, color = _found_by_cell(person)
        if color is not None:
            cell_colors.append((_HEADER_ROWS + i, _FOUND_BY_COL, color))

        row = [person.local_key, found_text, person.sf_id or ""] + [merged[f] for f in fields]
        grid.append(row)

    return grid, cell_colors
