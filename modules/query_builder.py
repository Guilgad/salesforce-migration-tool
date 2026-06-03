"""
בניית שאילתות Inspector (שלב 1 ב-wizard).

הכלי לא מתחבר ל-Salesforce. במקום זה הוא מרכיב את שאילתת ה-SOQL שהמשתמש
מעתיק ל-Salesforce Inspector, מריץ, ומחזיר את התוצאה ככניסת מילון-השדות.

שלב 1: שאילתת FieldDefinition — מקבלת שמות-API של אובייקטים ומחזירה
את כל השדות שלהם (Label / QualifiedApiName / DataType).
"""
from __future__ import annotations


def clean_object_names(raw: str) -> list[str]:
    """
    מנקה קלט רב-שורתי של שמות-אובייקטים:
    אובייקט בכל שורה, חיתוך רווחים, הסרת שורות ריקות וכפילויות.
    שומר על סדר ההופעה הראשון.
    """
    seen: set[str] = set()
    result: list[str] = []
    for line in (raw or "").splitlines():
        name = line.strip()
        if name and name not in seen:
            seen.add(name)
            result.append(name)
    return result


def build_data_query(object_api: str, fields: list[str]) -> str:
    """מרכיב שאילתת SELECT לייצוא רשומות קיימות (כולל Id לצורך upsert ו-backfill)."""
    field_csv = ", ".join(["Id"] + fields) if fields else "Id"
    return f"SELECT {field_csv}\nFROM {object_api}"


def build_field_definition_query(objects: list[str]) -> str:
    """
    מרכיב שאילתת FieldDefinition עבור רשימת אובייקטים.
    אם הרשימה ריקה — מחזיר מחרוזת ריקה (המסך מציג אזהרה, לא חוסם).
    """
    if not objects:
        return ""
    in_list = ", ".join(f"'{name}'" for name in objects)
    return (
        "SELECT EntityDefinition.Label, EntityDefinition.QualifiedApiName,\n"
        "       Label, QualifiedApiName, DataType\n"
        "FROM FieldDefinition\n"
        f"WHERE EntityDefinition.QualifiedApiName IN ({in_list})"
    )
