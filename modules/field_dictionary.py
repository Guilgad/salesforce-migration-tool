"""
פירוק תוצאת ה-SOQL מ-Salesforce Inspector למילון שדות (שלב 2 בזרימה).

הקלט הוא הגיליון שהמשתמש הדביק מ-Inspector (תוצאת שאילתת FieldDefinition משלב 1).
Inspector מוסיף עמודות-תג משלו (`_`, `EntityDefinition`), ולכן הפרסר מזהה עמודות
לפי **שם-הכותרת** ולא לפי מיקום — חסין לעמודות עודפות.

הפלט: לכל אובייקט (לפי שם-API) רשימת השדות שלו (Label / API / DataType),
בתוספת רשימת אזהרות — למשל אם אובייקט שביקשת בשלב 1 חזר בלי שום שדה.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# שמות הכותרות שהשאילתה משלב 1 מייצרת (מזוהים לפי שם, לא לפי מיקום)
_H_OBJ_API = "EntityDefinition.QualifiedApiName"
_H_OBJ_LABEL = "EntityDefinition.Label"
_H_FIELD_LABEL = "Label"
_H_FIELD_API = "QualifiedApiName"
_H_DATATYPE = "DataType"
_REQUIRED_HEADERS = (_H_OBJ_API, _H_OBJ_LABEL, _H_FIELD_LABEL, _H_FIELD_API, _H_DATATYPE)


@dataclass
class FieldInfo:
    """שדה בודד באובייקט."""
    label: str       # תווית ידידותית (Label)
    api: str         # שם ה-API (QualifiedApiName)
    datatype: str    # סוג הנתון כפי ש-Inspector מציג (Lookup(), Checkbox, ...)


@dataclass
class ObjectInfo:
    """אובייקט בודד והשדות שלו."""
    api: str
    label: str
    fields: list[FieldInfo] = field(default_factory=list)


@dataclass
class ParseResult:
    """תוצאת הפירוק: מילון אובייקטים (לפי שם-API) + אזהרות לתצוגה."""
    objects: dict[str, ObjectInfo]
    warnings: list[str]


def _cell(row: list[str], i: int) -> str:
    """מחזיר תא לפי אינדקס, גם אם השורה 'קצרה' (תאים ריקים בסוף מושמטים ב-API)."""
    if 0 <= i < len(row) and row[i] is not None:
        return str(row[i]).strip()
    return ""


def parse_field_dictionary(
    rows: list[list[str]],
    requested_objects: list[str] | None = None,
) -> ParseResult:
    """
    מפרק את שורות גיליון התוצאה למילון שדות.

    rows: ערכי הגיליון (שורה ראשונה = כותרות).
    requested_objects: האובייקטים שביקשת בשלב 1 — לבדיקת-שפיות (אזהרה על חסר).
    """
    if not rows:
        return ParseResult(objects={}, warnings=["גיליון תוצאת ה-SOQL ריק."])

    header = [_cell(rows[0], i) for i in range(len(rows[0]))]
    idx: dict[str, int] = {}
    missing_headers: list[str] = []
    for name in _REQUIRED_HEADERS:
        if name in header:
            idx[name] = header.index(name)
        else:
            missing_headers.append(name)
    if missing_headers:
        return ParseResult(
            objects={},
            warnings=[f"חסרות עמודות בכותרת הגיליון: {', '.join(missing_headers)}"],
        )

    objects: dict[str, ObjectInfo] = {}
    for row in rows[1:]:
        obj_api = _cell(row, idx[_H_OBJ_API])
        if not obj_api:
            continue  # שורה ריקה / לא רלוונטית
        obj = objects.get(obj_api)
        if obj is None:
            obj = ObjectInfo(api=obj_api, label=_cell(row, idx[_H_OBJ_LABEL]))
            objects[obj_api] = obj
        obj.fields.append(
            FieldInfo(
                label=_cell(row, idx[_H_FIELD_LABEL]),
                api=_cell(row, idx[_H_FIELD_API]),
                datatype=_cell(row, idx[_H_DATATYPE]),
            )
        )

    warnings: list[str] = []
    for req in requested_objects or []:
        if req not in objects:
            warnings.append(
                f"ביקשת את '{req}' בשלב 1, אך לא חזרו עבורו שדות — בדוק את שם-ה-API או שהרצת עליו."
            )

    return ParseResult(objects=objects, warnings=warnings)
