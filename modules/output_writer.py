"""
output_writer — בניית גריד פלט מוכן-לטעינה (פרוסה טהורה, בלי I/O).

לוקח את החלטות ה-dedup (אנשים) ומרכיב גריד `list[list[str]]`: שורה לאדם, עם
עמודות-מטא ועמודות-שדה. שני שלבים קריטיים לכל אדם:
  - קונסולידציה: מיזוג רשומות-החבר שהתמזגו לאותו אדם (ראשון-לא-ריק פר-שדה).
  - backfill: ל-Upsert בלבד — שדה שנשאר ריק ממולא מה-DB (upsert עם תא ריק *מוחק*
    דאטה בסיילספורס; מאומת). דאטת-טמפלייט גוברת, ה-DB ממלא חורים בלבד.

הכתיבה בפועל לגיליון = פרוסת I/O נפרדת; כאן רק מבנה הגריד.
"""
from __future__ import annotations

from modules import dedup_engine, mapper

# עמודות-המטא, בסדר שייכתב (לפני עמודות-השדה)
META_COLUMNS = ["local_key", "__Action", "__Id", "__נמצא_לפי", "__Status", "__Errors"]

_STATUS_AMBIGUOUS = "⚠️ ריבוי התאמות"
_STATUS_UNKEYED = "⚠️ ללא מפתח"


def _field_columns(columns: list[mapper.TemplateColumn], object_api: str) -> list[str]:
    """איחוד clean_api של עמודות תקפות לאובייקט, בסדר-הופעה יציב (בלי כפילויות)."""
    seen: list[str] = []
    for c in columns:
        if (
            c.object_api == object_api
            and c.status == mapper.STATUS_VALID
            and c.clean_api
            and c.clean_api not in seen
        ):
            seen.append(c.clean_api)
    return seen


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


def _status_flag(person: dedup_engine.PersonResult) -> str:
    """דגל קדם-טעינה ל-__Status (לפני טעינה; ריק כשהכל תקין)."""
    if person.ambiguous:
        return _STATUS_AMBIGUOUS
    if person.unkeyed:
        return _STATUS_UNKEYED
    return ""


def build_contacts_grid(
    dedup_result: dedup_engine.DedupResult,
    record_values: list[dict],
    columns: list[mapper.TemplateColumn],
    db_by_id: dict[str, dict],
    *,
    object_api: str = "Contact",
) -> list[list[str]]:
    """
    מרכיב גריד פלט: שורת-כותרת (META_COLUMNS + עמודות-שדה) ואז שורה לכל אדם.

    dedup_result:  פלט dedup_engine.deduplicate (אנשים + החלטות).
    record_values: אותה רשימת רשומות שהוזנה ל-deduplicate (אינדקסים תואמים ל-record_indices).
    columns:       עמודות מאומתות (mapper.validate_columns) — לקביעת עמודות-השדה.
    db_by_id:      רשומות DB מקוריות לפי Id ({Id: {api: value}}) — ל-backfill.
    """
    fields = _field_columns(columns, object_api)
    header = META_COLUMNS + fields
    grid: list[list[str]] = [header]

    for person in dedup_result.persons:
        merged = _consolidate(person.record_indices, record_values, fields)

        # backfill: ל-Upsert בלבד, שדה ריק → ערך מה-DB (מקורי)
        if person.action == dedup_engine.ACTION_UPSERT and person.sf_id:
            db_rec = db_by_id.get(person.sf_id, {})
            for f in fields:
                if not merged[f]:
                    merged[f] = str(db_rec.get(f, "") or "").strip()

        meta = [
            person.local_key,
            person.action,
            person.sf_id or "",
            str(person.found_by + 1) if person.found_by is not None else "",
            _status_flag(person),
            "",  # __Errors — יתמלא אחרי טעינה
        ]
        grid.append(meta + [merged[f] for f in fields])

    return grid
