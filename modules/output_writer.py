"""
output_writer — בניית גריד פלט מוכן-לטעינה (פרוסה טהורה, בלי I/O).

לוקח את החלטות ה-dedup (אנשים) ומרכיב גריד `list[list[str]]`: שתי שורות-כותרת
(עברית מעל API) ואז שורה לאדם. שני שלבים קריטיים לכל אדם:
  - קונסולידציה: מיזוג רשומות-החבר שהתמזגו לאותו אדם (ראשון-לא-ריק פר-שדה).
  - backfill: ל-Upsert בלבד — שדה שנשאר ריק ממולא מה-DB (upsert עם תא ריק *מוחק*
    דאטה בסיילספורס; מאומת). דאטת-טמפלייט גוברת, ה-DB ממלא חורים בלבד.

מבנה העמודות: עמודות לא-נטענות (`local_key`, `נמצא לפי`) משמאל, אחריהן הנטענות
(`Id` + שדות). תא "נמצא לפי" נצבע לפי איכות ההתאמה (🟢 מנגנון 1 / 🟡 מנגנון 2-3 /
🟠 הכרעה-בשילוב) — רשימת הצבעים מוחזרת לצד הגריד ל-sheets_io.color_cells.

רשומות דו-משמעיות/חסרות-זיהוי **מוחרגות** מהגריד הראשי (לא נטענות) ועוברות ל-
`build_manual_grid` → לשונית "טיפול ידני" להכרעה ידנית.

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

_RESOLVED_TEXT = "נבחר ידנית"  # תווית ל"נמצא לפי" אחרי הכרעה ידנית בלשונית הטיפול

# ===== לשונית "טיפול ידני" =====
# כותרות העמודות הקבועות (לפני עמודות-השדה). "בחר" = עמודה ריקה שהמשתמש מסמן בה ✓.
_MANUAL_HEADER = ["מפתח פנימי", "סיבה", "שורת-מקור", "בחר", "סוג", "מזהה"]
_MANUAL_REASON = {"ambiguous": "ריבוי התאמות", "unkeyed": "ללא נתוני זיהוי"}
_ROW_SOURCE = "מקור"   # שורת רשומת-הקלט
_ROW_DB = "מאגר"       # שורת מועמד מה-DB


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
      - הכרעה-בשילוב (כמה מנגנונים צורפו) → "שילוב 1+2" (🟠, בולט — פחות בטוח)
      - Upsert לפי מנגנון 1 → "1" (🟢)
      - Upsert לפי מנגנון 2/3 → "2"/"3" (🟡)
      - Insert חדש תקין → ריק, ללא צבע
    (דו-משמעי/חסר-מפתח כלל לא מגיעים לכאן — הם מוחרגים מהגריד הראשי לטיפול ידני.)
    """
    if person.combined_mechs:
        label = "+".join(str(m + 1) for m in person.combined_mechs)
        return f"שילוב {label}", "orange"
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
    manual_choices: dict[str, str] | None = None,
) -> tuple[list[list[str]], list[tuple[int, int, str]]]:
    """
    מרכיב גריד פלט: 2 שורות-כותרת (עברית מעל API) ואז שורה לכל אדם, ולצדו רשימת
    צבעים לתא "נמצא לפי".

    dedup_result:  פלט dedup_engine.deduplicate (אנשים + החלטות).
    record_values: אותה רשימת רשומות שהוזנה ל-deduplicate (אינדקסים תואמים ל-record_indices).
    columns:       עמודות מאומתות (mapper.validate_columns) — לקביעת עמודות-השדה.
    db_by_id:      רשומות DB מקוריות לפי Id ({Id: {api: value}}) — ל-backfill.
    manual_choices: {local_key → sf_id שנבחר ידנית בלשונית "טיפול ידני"} (פרוסה 8ב).
                    אדם דו-משמעי/חסר-זיהוי עם בחירה כזו נכנס לגריד כ-Upsert עם ה-Id
                    הנבחר (במקום להיות מוחרג). אידמפוטנטי — בנייה חוזרת משקפת את הבחירות.

    מחזיר (grid, cell_colors):
      grid:        list[list[str]] — 2 שורות-כותרת + שורה לאדם.
      cell_colors: list[(row0, col0, color)] בקואורדינטות אבסולוטיות לתא "נמצא לפי".
    """
    choices = manual_choices or {}
    field_pairs = _field_columns(columns, object_api)
    fields = [api for api, _label in field_pairs]

    # שתי שורות-כותרת: עברית מעל API. סדר: עמודות-תצוגה → Id → שדות.
    header_he = [he for he, _api in _DISPLAY_COLUMNS] + [_ID_COLUMN[0]] + [
        label for _api, label in field_pairs
    ]
    header_api = [api for _he, api in _DISPLAY_COLUMNS] + [_ID_COLUMN[1]] + fields
    grid: list[list[str]] = [header_he, header_api]
    cell_colors: list[tuple[int, int, str]] = []

    row_idx = 0  # שורת-פלט בפועל (אחרי דילוג על דו-משמעי/חסר-מפתח) — לקואורדינטת הצבע
    for person in dedup_result.persons:
        chosen = choices.get(person.local_key)
        if (person.ambiguous or person.unkeyed) and not chosen:
            continue  # מוחרגים מהטעינה → לשונית "טיפול ידני" (אלא אם נבחרו ידנית)

        # Id אפקטיבי: בחירה ידנית גוברת; אחרת החלטת ה-dedup
        sf_id = chosen if chosen else person.sf_id
        merged = _consolidate(person.record_indices, record_values, fields)

        # backfill: לכל Upsert (כולל בחירה ידנית), שדה ריק → ערך מה-DB (מקורי)
        if sf_id:
            db_rec = db_by_id.get(sf_id, {})
            for f in fields:
                if not merged[f]:
                    merged[f] = str(db_rec.get(f, "") or "").strip()

        if chosen:
            found_text, color = _RESOLVED_TEXT, "orange"  # הוכרע ידנית — בולט לווידוא
        else:
            found_text, color = _found_by_cell(person)
        if color is not None:
            cell_colors.append((_HEADER_ROWS + row_idx, _FOUND_BY_COL, color))

        row = [person.local_key, found_text, sf_id or ""] + [merged[f] for f in fields]
        grid.append(row)
        row_idx += 1

    return grid, cell_colors


def build_manual_grid(
    dedup_result: dedup_engine.DedupResult,
    record_values: list[dict],
    columns: list[mapper.TemplateColumn],
    db_by_id: dict[str, dict],
    source_rows: list[int],
    *,
    object_api: str = "Contact",
    marked: dict[str, str] | None = None,
) -> list[list[str]]:
    """
    גריד ללשונית "טיפול ידני": לכל אדם דו-משמעי/חסר-זיהוי, שורת **מקור** (רשומת
    הקלט) ואחריה שורה לכל **מועמד-DB**, כדי שאפשר להשוות ולסמן את הנכון בעמודת "בחר".

    source_rows: source_row לכל רשומת-קלט (אינדקסים תואמים ל-record_values), לתצוגת
                 שורת-המקור בטמפלייט (מוצג 1-based).
    marked: {local_key → sf_id שכבר נבחר} — מסמן מחדש ✓ בשורת-המועמד התואמת, כדי
            לשמר את בחירות המשתמש בכתיבה-חוזרת (אידמפוטנטיות).
    מחזיר list[list[str]] עם שורת-כותרת אחת; ריק (רק כותרת) אם אין רשומות לטיפול ידני.
    """
    marks = marked or {}
    field_pairs = _field_columns(columns, object_api)
    fields = [api for api, _label in field_pairs]
    header = _MANUAL_HEADER + [label for _api, label in field_pairs]
    grid: list[list[str]] = [header]

    for person in dedup_result.persons:
        if not (person.ambiguous or person.unkeyed):
            continue
        reason = _MANUAL_REASON["unkeyed" if person.unkeyed else "ambiguous"]
        src = ", ".join(str(source_rows[mi] + 1) for mi in person.record_indices)

        # שורת המקור: ערכי רשומת-הקלט (ממוזגים אם כמה רשומות-חבר)
        merged = _consolidate(person.record_indices, record_values, fields)
        grid.append(
            [person.local_key, reason, src, "", _ROW_SOURCE, ""]
            + [merged[f] for f in fields]
        )

        # שורה לכל מועמד-DB (ambiguous בלבד; ל-unkeyed אין מועמדים)
        for sid in person.match_ids:
            db_rec = db_by_id.get(sid, {})
            check = "✓" if marks.get(person.local_key) == sid else ""
            grid.append(
                [person.local_key, "", "", check, _ROW_DB, sid]
                + [str(db_rec.get(f, "") or "").strip() for f in fields]
            )

    return grid


def parse_manual_choices(manual_rows: list[list[str]]) -> tuple[dict[str, str], list[str]]:
    """
    קורא את לשונית "טיפול ידני" שהמשתמש סימן בה, ומחזיר ({local_key → sf_id נבחר}, אזהרות).

    בחירה = שורת **מאגר** שעמודת "בחר" שלה לא-ריקה (✓/x/כל סימון) → ה-Id שלה נבחר
    ל-local_key. שורה ראשונה = כותרת (לאיתור אינדקסי העמודות לפי שם). מספר סימונים
    לאותו local_key → אזהרה, נלקח הראשון.
    """
    choices: dict[str, str] = {}
    warnings: list[str] = []
    if not manual_rows or len(manual_rows) < 2:
        return choices, warnings

    header = manual_rows[0]
    try:
        c_key = header.index("מפתח פנימי")
        c_mark = header.index("בחר")
        c_type = header.index("סוג")
        c_id = header.index("מזהה")
    except ValueError:
        warnings.append("מבנה לשונית הטיפול הידני לא מזוהה — לא נקלטו בחירות.")
        return choices, warnings

    def cell(row: list[str], i: int) -> str:
        return str(row[i]).strip() if i < len(row) else ""

    for row in manual_rows[1:]:
        if cell(row, c_type) != _ROW_DB or not cell(row, c_mark):
            continue
        key, sid = cell(row, c_key), cell(row, c_id)
        if not key or not sid:
            continue
        if key in choices and choices[key] != sid:
            warnings.append(f"{key}: סומנה יותר מרשומה אחת — נלקחה הראשונה ({choices[key]}).")
            continue
        choices.setdefault(key, sid)
    return choices, warnings
