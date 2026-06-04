"""
ולידציה לפני בנייה/טעינה (שלב 6) — ריכוז כל הבעיות ללשונית "בעיות".

טהור, נטול-I/O. אוסף שלושה סוגי-בדיקות:
  1. מיפוי — סטטוסי-העמודה שכבר חושבו ב-mapper (INVALID/MISSING/NO_DICT).
  2. תאריכים — תאים בעמודות מסוג Date שאינם ניתנים לפירוש (דרך formatter.parse_date).
  3. אורך Id — ערכי Id בייצוא ה-DB שאורכם ≠ 18 (v1 אין ממיר 15→18).

המנוע גנרי; מה שספציפי-לטמפלייט (data_start_row וכו') מגיע מבחוץ.
"""
from __future__ import annotations

from dataclasses import dataclass

from modules import formatter, mapper, sheets_io

# חומרות
SEVERITY_ERROR = "error"
SEVERITY_WARNING = "warning"

# סוגי-בעיה (kind)
KIND_UNMAPPED = "unmapped"        # אובייקט ממופה אך אין API
KIND_INVALID_API = "invalid_api"  # API מולא אך לא קיים במילון
KIND_NO_DICT = "no_dict"          # האובייקט מחוץ למילון
KIND_BAD_DATE = "bad_date"        # תא Date שלא נפרסר
KIND_BAD_ID = "bad_id"            # אורך Id ≠ 18

_HEADER_ROWS = 2


@dataclass
class Issue:
    """בעיה בודדת לתצוגה בלשונית 'בעיות'."""
    kind: str        # אחד מקבועי KIND_*
    severity: str    # SEVERITY_ERROR / SEVERITY_WARNING
    label: str       # תווית-העמודה בעברית (או שם-אובייקט)
    location: str    # מיקום אנושי: אות-עמודה + שורה, למשל "G" או "G5"
    message: str     # הסבר קריא בעברית


# סטטוס-עמודה → (חומרה, kind, תבנית-הודעה). רק סטטוסים שהם "בעיה".
_STATUS_TO_ISSUE = {
    mapper.STATUS_INVALID: (
        SEVERITY_ERROR, KIND_INVALID_API,
        "שם ה-API '{api}' אינו קיים באובייקט {obj} — תקן במסך המיפוי.",
    ),
    mapper.STATUS_MISSING: (
        SEVERITY_WARNING, KIND_UNMAPPED,
        "העמודה משויכת לאובייקט {obj} אך אין לה שם-API — מפה או סמן 'לא רלוונטי'.",
    ),
    mapper.STATUS_NO_DICT: (
        SEVERITY_WARNING, KIND_NO_DICT,
        "האובייקט {obj} לא נכלל בשאילתת המילון — לא ניתן לאמת את העמודה.",
    ),
}


def validate_mapping(cols: list[mapper.TemplateColumn]) -> list[Issue]:
    """אוסף בעיות-מיפוי מסטטוסי-העמודה (כבר חושבו ב-validate_columns)."""
    issues: list[Issue] = []
    for c in cols:
        rule = _STATUS_TO_ISSUE.get(c.status)
        if rule is None:
            continue  # VALID / IGNORE / CONTROL — לא בעיה
        severity, kind, template = rule
        msg = template.format(api=c.clean_api or c.proposed_api or "—", obj=c.object_api or "—")
        issues.append(Issue(
            kind=kind,
            severity=severity,
            label=c.label or "—",
            location=sheets_io.col_letter(c.index),
            message=msg,
        ))
    return issues


def _date_apis(cols, dictionary) -> dict[int, str]:
    """{col_index → clean_api} לעמודות VALID שסוג-הנתון שלהן Date (לפי המילון)."""
    # {(object_api, api): datatype}
    type_by_field: dict[tuple[str, str], str] = {}
    for obj_api, obj in dictionary.items():
        for f in obj.fields:
            type_by_field[(obj_api, f.api)] = f.datatype

    date_cols: dict[int, str] = {}
    for c in cols:
        if c.status != mapper.STATUS_VALID or not c.clean_api:
            continue
        datatype = type_by_field.get((c.object_api, c.clean_api), "")
        if datatype.strip().lower().startswith("date"):  # "Date" / "Date/Time"
            date_cols[c.index] = c.clean_api
    return date_cols


def validate_dates(
    cols: list[mapper.TemplateColumn],
    tmpl_rows: list[list[str]],
    dictionary: dict,
    *,
    data_start_row: int,
) -> list[Issue]:
    """תאים בעמודות-תאריך שאינם ניתנים לפירוש → Issue('bad_date') עם מיקום מדויק."""
    date_cols = _date_apis(cols, dictionary)
    if not date_cols:
        return []

    label_by_index = {c.index: c.label for c in cols}
    issues: list[Issue] = []
    for r in range(data_start_row, len(tmpl_rows)):
        row = tmpl_rows[r]
        for idx in date_cols:
            value = row[idx] if 0 <= idx < len(row) else None
            text = formatter.normalize_text(value)
            if not text:
                continue  # תא ריק — אין מה לפרסר
            if formatter.parse_date(text) is None:
                issues.append(Issue(
                    kind=KIND_BAD_DATE,
                    severity=SEVERITY_ERROR,
                    label=label_by_index.get(idx, "—"),
                    location=f"{sheets_io.col_letter(idx)}{r + 1}",  # שורת-גיליון 1-based
                    message=f"הערך '{text}' אינו תאריך תקין — צפוי פורמט כמו 04.06.2026.",
                ))
    return issues


def validate_ids(db_by_object: dict[str, list[dict]]) -> list[Issue]:
    """ערכי Id בייצוא ה-DB שאורכם ≠ 18 → Issue('bad_id'). v1: אין ממיר 15→18."""
    issues: list[Issue] = []
    for obj, records in db_by_object.items():
        for rec in records:
            sid = formatter.normalize_text(rec.get("Id"))
            if sid and len(sid) != 18:
                issues.append(Issue(
                    kind=KIND_BAD_ID,
                    severity=SEVERITY_WARNING,
                    label=obj,
                    location="Id",
                    message=f"Id '{sid}' באורך {len(sid)} (צפוי 18) — ייתכן Id קצר (15) שאינו נתמך.",
                ))
    return issues


_SEVERITY_HE = {SEVERITY_ERROR: "שגיאה", SEVERITY_WARNING: "אזהרה"}
_KIND_HE = {
    KIND_UNMAPPED: "עמודה ללא מיפוי",
    KIND_INVALID_API: "שדה API לא קיים",
    KIND_NO_DICT: "אובייקט מחוץ למילון",
    KIND_BAD_DATE: "תאריך לא תקין",
    KIND_BAD_ID: "אורך Id שגוי",
}


def build_issues_grid(
    issues: list[Issue],
) -> tuple[list[list[str]], list[tuple[int, int, str]]]:
    """
    גריד לשונית 'בעיות': 2 שורות-כותרת ואז שורה לכל Issue.

    שורות עם severity=='error' נצבעות אדום (cell_colors על עמודה 0).
    גריד עם 2 שורות בלבד = אין בעיות.
    """
    header_he = ["סוג", "חומרה", "עמודה", "מיקום", "הסבר"]
    header_api = ["", "", "", "", ""]
    grid: list[list[str]] = [header_he, header_api]
    cell_colors: list[tuple[int, int, str]] = []

    for i, issue in enumerate(issues):
        grid.append([
            _KIND_HE.get(issue.kind, issue.kind),
            _SEVERITY_HE.get(issue.severity, issue.severity),
            issue.label,
            issue.location,
            issue.message,
        ])
        if issue.severity == SEVERITY_ERROR:
            cell_colors.append((_HEADER_ROWS + i, 0, "red"))

    return grid, cell_colors
