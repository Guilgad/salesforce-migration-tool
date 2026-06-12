"""Orchestration layer: adapts RuntimeSchema → engine inputs."""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from config.runtime_schema import RuntimeSchema

from config.runtime_schema import ROLE_FIELD, ROLE_CONTROL, ROLE_SKIP
from modules.mapper import TemplateColumn, STATUS_VALID, STATUS_CONTROL, STATUS_IGNORE

_ROLE_TO_STATUS = {
    ROLE_FIELD: STATUS_VALID,
    ROLE_CONTROL: STATUS_CONTROL,
}


def OUTPUT_TAB(object_api: str) -> str:
    """שם לשונית פלט רגילה לאובייקט."""
    return f"פלט - {object_api}"


def OUTPUT_TAB_MANUAL(object_api: str) -> str:
    """שם לשונית פלט ידני לאובייקט."""
    return f"פלט ידני - {object_api}"


def adapt_columns(schema, object_api: str, header_rows: list) -> list[TemplateColumn]:
    """
    Convert schema.mappings for object_api → list[TemplateColumn].

    - Filters to mappings whose object_api matches.
    - Skips ROLE_SKIP mappings entirely.
    - ROLE_FIELD → STATUS_VALID, ROLE_CONTROL → STATUS_CONTROL.
    - block = str(cm.instance or 1).
    - label = header_rows[schema.label_row][col_index] if available, else cm.field_api.
    - Returns sorted by index.
    """
    label_row: list = (
        header_rows[schema.label_row]
        if len(header_rows) > schema.label_row
        else []
    )

    result: list[TemplateColumn] = []
    for col_index, cm in schema.mappings.items():
        if cm.object_api != object_api:
            continue
        if cm.role == ROLE_SKIP:
            continue

        status = _ROLE_TO_STATUS.get(cm.role, STATUS_IGNORE)
        label = (
            label_row[col_index]
            if col_index < len(label_row)
            else None
        ) or cm.field_api

        result.append(TemplateColumn(
            index=col_index,
            block=str(cm.instance or 1),
            label=label,
            proposed_api=cm.field_api,
            object_api=object_api,
            clean_api=cm.field_api,
            status=status,
        ))

    return sorted(result, key=lambda tc: tc.index)
