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


# ── Value-map application ─────────────────────────────────────────────────────

def apply_value_maps(records, schema) -> list:
    """
    Translate field values according to schema.value_maps.

    For each SplitRecord, for each field that has a ValueMap (looked up via
    schema.mappings col_index → field_api), apply the map using ValueMap.apply().
    Returns a new list of SplitRecords (originals are not mutated).
    """
    from modules.splitter import SplitRecord

    # Build {field_api: ValueMap} from the col_index-keyed dicts
    vm_by_field: dict[str, object] = {}
    for col_index, vm in schema.value_maps.items():
        cm = schema.mappings.get(col_index)
        if cm and cm.field_api:
            vm_by_field[cm.field_api] = vm

    if not vm_by_field:
        return list(records)

    result = []
    for rec in records:
        new_values = dict(rec.values)
        for field_api, val in rec.values.items():
            vm = vm_by_field.get(field_api)
            if vm is None:
                continue
            translated, found = vm.apply(val)
            if found:
                new_values[field_api] = translated
            elif not found and translated and val:
                # default exists and value is non-empty
                new_values[field_api] = translated
        result.append(SplitRecord(
            object_api=rec.object_api,
            block=rec.block,
            source_row=rec.source_row,
            values=new_values,
        ))
    return result


# ── Extra-fields application ──────────────────────────────────────────────────

def apply_extra_fields(records, schema, object_api: str) -> list:
    """
    Inject constant ExtraField values into each SplitRecord for the given object.

    Returns a new list of SplitRecords (originals are not mutated).
    If no ExtraFields match object_api, returns the records list unchanged.
    """
    from modules.splitter import SplitRecord

    extras = {
        ef.field_api: ef.constant_value
        for ef in schema.extra_fields
        if ef.object_api == object_api
    }

    if not extras:
        return records

    result = []
    for rec in records:
        new_values = {**rec.values, **extras}
        result.append(SplitRecord(
            object_api=rec.object_api,
            block=rec.block,
            source_row=rec.source_row,
            values=new_values,
        ))
    return result


# ── 15→18 Salesforce Id conversion ───────────────────────────────────────────

_SF_CHARS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ012345"


def convert_id_15_to_18(id_val):
    """Convert a 15-char Salesforce Id to its 18-char canonical form. Others unchanged."""
    if not id_val or len(id_val) != 15:
        return id_val
    suffix = ""
    for chunk in range(3):
        flags = 0
        for pos in range(5):
            c = id_val[chunk * 5 + pos]
            if c.isupper():
                flags += 1 << pos
        suffix += _SF_CHARS[flags]
    return id_val + suffix
