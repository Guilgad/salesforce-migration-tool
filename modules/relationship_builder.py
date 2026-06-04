"""
relationship_builder — גזירת קשרים (npe4__Relationship__c) מצמדי אנשי-קשר.

טהור (בלי I/O): לכל שורת-טמפלייט שיש בה גם איש-קשר ראשי וגם "נוסף" — נגזר קשר אחד.
הכלי כותב כיוון אחד בלבד (A < B לפי מיון); NPSP יוצר את ההפוך אוטומטית.

תנאי-קדם: Contacts כבר נטענו לסיילספורס וה-Ids הודבקו חזרה ב-"פלט - Contacts".
בלי זה, contact_id_map יהיה ריק ואף קשר לא ייכתב לפלט.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from modules import dedup_engine, mapper, splitter

# כותרות גריד הקשרים: תצוגה בלבד | נטענות
_HEADER_HE = ["שם א'", "שם ב'", "איש-קשר A", "איש-קשר B", "סוג הקשר"]
_HEADER_API = ["", "", "npe4__Contact__c", "npe4__RelatedContact__c", "npe4__Type__c"]
_HEADER_ROWS = 2
_DISPLAY_COLS = (0, 1)  # עמודות "שם א'" / "שם ב'" — לא נטענות (צבע אדום-בהיר)


@dataclass
class RelRecord:
    """קשר אחד שנגזר מצמד אנשי-קשר בשורת-הטמפלייט."""
    source_row: int
    local_key_a: str    # local_key איש-קשר ראשי
    local_key_b: str    # local_key איש-קשר נוסף
    sf_id_a: str        # SF Id (ריק = לא נטען עדיין)
    sf_id_b: str
    type_val: str       # npe4__Type__c
    name_a: str         # שם לתצוגה בלבד
    name_b: str
    exists_in_db: bool  # True = הזוג כבר ב-DB → לא ייכנס לפלט
    warning: str | None  # Id חסר / בעיה אחרת


def _cell(row: list[str], i: int) -> str:
    if 0 <= i < len(row) and row[i] is not None:
        return str(row[i]).strip()
    return ""


def _display_name(values: dict) -> str:
    """שם לתצוגה מתוך ערכי רשומת-קלט: FirstName + LastName."""
    first = str(values.get("FirstName", "") or "").strip()
    last = str(values.get("LastName", "") or "").strip()
    return (first + " " + last).strip()


def contact_id_map_from_grid(grid_rows: list[list[str]]) -> dict[str, str]:
    """
    local_key → sf_id מלשונית "פלט - Contacts" (מבנה 2-header של build_contacts_grid).
    עמודה 0 = local_key, עמודה 2 = Id. מדלג על Ids ריקים (Contacts שטרם נטענו).
    """
    result: dict[str, str] = {}
    for row in grid_rows[_HEADER_ROWS:]:
        key = _cell(row, 0)
        sid = _cell(row, 2)
        if key and sid:
            result[key] = sid
    return result


def db_rel_pairs_from_records(db_records: list[dict]) -> set[tuple[str, str]]:
    """
    Set של זוגות ממוינים (min_id, max_id) מרשומות DB של npe4__Relationship__c.
    NPSP שומר שני כיוונים — הממיין הופך A↔B לזהה.
    """
    pairs: set[tuple[str, str]] = set()
    for rec in db_records:
        a = str(rec.get("npe4__Contact__c", "") or "").strip()
        b = str(rec.get("npe4__RelatedContact__c", "") or "").strip()
        if a and b:
            pairs.add((min(a, b), max(a, b)))
    return pairs


def derive_relationships(
    tmpl_rows: list[list[str]],
    columns: list[mapper.TemplateColumn],
    split_records: list[splitter.SplitRecord],
    dedup_result: dedup_engine.DedupResult,
    contact_id_map: dict[str, str],
    db_rel_pairs: set[tuple[str, str]],
    *,
    data_start_row: int,
    block_primary: str,
    block_secondary: str,
    relationship_object: str,
) -> list[RelRecord]:
    """
    גוזר קשרים מכל שורת-טמפלייט שיש בה שני אנשי-קשר.

    split_records + dedup_result: ריצת Contacts מקבילה (אותם קלטים, local_key_prefix="C").
    contact_id_map: local_key → sf_id מלשונית "פלט - Contacts" (לאחר טעינה).
    db_rel_pairs: זוגות קיימים-ב-DB (ממוינים) — מסוננים מהפלט.
    """
    # record_idx → local_key
    idx_to_key: dict[int, str] = {}
    for person in dedup_result.persons:
        for idx in person.record_indices:
            idx_to_key[idx] = person.local_key

    # (source_row, block) → record_idx (הראשון — בלוק מכיל עמודה אחת לכל שורה)
    row_block_to_idx: dict[tuple[int, str], int] = {}
    for i, rec in enumerate(split_records):
        row_block_to_idx.setdefault((rec.source_row, rec.block), i)

    # עמודת-סוג: ראשונה ב-columns עם object_api=relationship_object וסטטוס תקף
    type_col_index: int | None = None
    for c in columns:
        if c.object_api == relationship_object and c.status == mapper.STATUS_VALID:
            type_col_index = c.index
            break

    results: list[RelRecord] = []
    for r in range(data_start_row, len(tmpl_rows)):
        idx_a = row_block_to_idx.get((r, block_primary))
        idx_b = row_block_to_idx.get((r, block_secondary))
        if idx_b is None:
            continue  # אין "נוסף" → אין קשר בשורה זו

        key_a = idx_to_key.get(idx_a, "") if idx_a is not None else ""
        key_b = idx_to_key.get(idx_b, "")

        sf_id_a = contact_id_map.get(key_a, "") if key_a else ""
        sf_id_b = contact_id_map.get(key_b, "") if key_b else ""

        # שמות לתצוגה: מתוך הערכים שחולצו, ברירת-מחדל = local_key
        name_a = (_display_name(split_records[idx_a].values) if idx_a is not None else "") or key_a
        name_b = (_display_name(split_records[idx_b].values)) or key_b

        type_val = _cell(tmpl_rows[r], type_col_index) if type_col_index is not None else ""

        warning: str | None = None
        exists_in_db = False
        if not sf_id_a or not sf_id_b:
            missing = key_a if not sf_id_a else key_b
            warning = f"Id חסר לאיש-קשר {missing} — יש לטעון את Contacts קודם"
        else:
            pair = (min(sf_id_a, sf_id_b), max(sf_id_a, sf_id_b))
            exists_in_db = pair in db_rel_pairs

        results.append(RelRecord(
            source_row=r,
            local_key_a=key_a,
            local_key_b=key_b,
            sf_id_a=sf_id_a,
            sf_id_b=sf_id_b,
            type_val=type_val,
            name_a=name_a,
            name_b=name_b,
            exists_in_db=exists_in_db,
            warning=warning,
        ))
    return results


def build_relationship_grid(
    rel_records: list[RelRecord],
) -> tuple[list[list[str]], list[tuple[int, int, str]]]:
    """
    בונה גריד קשרים: 2 שורות-כותרת ואז שורה לכל קשר חדש.

    מדלג על:
    - exists_in_db=True (קיים ב-DB — לא נדרשת טעינה)
    - warning לא-None (Id חסר — אי-אפשר לכתוב)

    מחזיר (grid, cell_colors) — cell_colors לצביעת עמודות-תצוגה (אדום-בהיר = לא-נטען).
    """
    grid: list[list[str]] = [_HEADER_HE[:], _HEADER_API[:]]
    cell_colors: list[tuple[int, int, str]] = []

    row_idx = 0
    for rec in rel_records:
        if rec.exists_in_db or rec.warning:
            continue
        grid.append([rec.name_a, rec.name_b, rec.sf_id_a, rec.sf_id_b, rec.type_val])
        data_row = _HEADER_ROWS + row_idx
        for col in _DISPLAY_COLS:
            cell_colors.append((data_row, col, "red"))
        row_idx += 1

    return grid, cell_colors
