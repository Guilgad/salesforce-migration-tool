"""
schema_reader — קריאת מוסכמת 3-שורות-הכותרת של v2.

גנרי: מקבל שורות גיליון + RuntimeSchema, מחזיר רשימת TemplateColumn.
משתמש ב-mapper.extract_columns() הקיים (שמטפל ב-forward-fill של שורת-הבלוק).

הבדל מ-v1: שורה 0 = שם-אובייקט ישיר (ל-multi) במקום שם-בלוק-עברי + BLOCK_TO_OBJECT.
"""
from __future__ import annotations

from config.runtime_schema import RuntimeSchema
from modules import mapper


def detect_objects(rows: list[list[str]], *, object_row: int) -> list[str]:
    """
    Return unique non-empty object names from `object_row`, preserving first-appearance order.
    Returns [] if object_row is out of range.
    """
    if object_row >= len(rows):
        return []
    seen: set[str] = set()
    result: list[str] = []
    for cell in rows[object_row]:
        val = str(cell or "").strip()
        if val and val not in seen:
            seen.add(val)
            result.append(val)
    return result


def read_header_columns(
    rows: list[list[str]],
    schema: RuntimeSchema,
) -> list[mapper.TemplateColumn]:
    """
    Read the 3-row header and produce a TemplateColumn list.

    For table_type="multi": object_api is taken from schema.object_row (forward-filled
    by extract_columns — same mechanism as v1 block rows).
    For table_type="single": all columns get schema.single_object_api.
    """
    cols = mapper.extract_columns(
        rows,
        block_row=schema.object_row,
        label_row=schema.label_row,
        api_row=schema.api_row,
    )
    for col in cols:
        if schema.table_type == "single":
            col.object_api = schema.single_object_api
        else:
            # In v2 multi-object tables, the block name IS the SF object API name
            col.object_api = col.block
    return cols
