"""Orchestration layer: adapts RuntimeSchema → engine inputs."""
from __future__ import annotations

from collections import namedtuple
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


# ── Pure build core (no Streamlit, no I/O) — the integration-testable seam ───

BuildOutput = namedtuple(
    "BuildOutput", "grid cell_colors result columns record_dicts source_rows"
)


def apply_grid_id_conversion(grid: list) -> list:
    """Convert any 15-char alphanumeric cell to its 18-char Salesforce Id; others unchanged."""
    return [
        [
            convert_id_15_to_18(c)
            if isinstance(c, str) and len(c) == 15 and c.isalnum()
            else c
            for c in row
        ]
        for row in grid
    ]


def build_object_core(schema, object_api: str, input_rows: list, db_recs: list) -> "BuildOutput":
    """
    Pure build core: schema + input rows + DB records → BuildOutput. **No Streamlit, no I/O.**

    Mirrors `main._run_build_pipeline`'s transformation sequence EXACTLY (adapt_columns →
    split_object → apply_value_maps → apply_extra_fields → deduplicate → build_contacts_grid →
    15→18 conversion), so the full UI→schema→engines wiring — including the DB cross-reference
    that decides insert vs upsert — can be integration-tested without a browser. This is the
    seam that would have caught the `db_tabs` bug.

    db_recs: the DB rows for this object already resolved to dicts (caller reads them via the
             db_tabs mapping). Empty list = no DB data → every record is a new Insert.
    """
    from modules.splitter import split_object
    from modules.dedup_engine import deduplicate
    from modules.output_writer import build_contacts_grid
    from config.runtime_schema import IdentityConfig

    columns = adapt_columns(schema, object_api, input_rows)
    records = split_object(object_api, input_rows, columns, data_start_row=schema.data_start_row)
    records = apply_value_maps(records, schema)
    records = apply_extra_fields(records, schema, object_api)

    record_dicts = [r.values for r in records]
    source_rows = [r.source_row for r in records]
    db_by_id = {r["Id"]: r for r in db_recs if r.get("Id")}

    id_cfg = schema.identity.get(object_api, IdentityConfig())
    result = deduplicate(
        record_dicts, id_cfg.mechanisms or [], db_recs,
        digits_only_fields=schema.digits_only_fields,
        local_key_prefix=object_api[:1].upper(),
        dedup_internal=id_cfg.dedup_internal,
    )

    grid, cell_colors = build_contacts_grid(
        result, record_dicts, columns, db_by_id, object_api=object_api,
    )
    grid = apply_grid_id_conversion(grid)
    return BuildOutput(grid, cell_colors, result, columns, record_dicts, source_rows)


# ── Read Salesforce Ids from a written output tab ────────────────────────────

LOCAL_KEY_HEADER = "local_key"   # API header written by output_writer._DISPLAY_COLUMNS
SF_ID_HEADER = "Id"              # API header written by output_writer._ID_COLUMN


def read_ids_from_output_tab(rows: list) -> dict:
    """Parse re-read output tab → {local_key: sf_id}. Expects 2 header rows then data."""
    if len(rows) < 2:
        return {}
    api_headers = rows[1]
    key_col = next((i for i, h in enumerate(api_headers) if h == LOCAL_KEY_HEADER), None)
    id_col = next((i for i, h in enumerate(api_headers) if h == SF_ID_HEADER), None)
    if key_col is None or id_col is None:
        return {}
    result = {}
    for row in rows[2:]:
        key = row[key_col] if key_col < len(row) else ""
        sf_id = row[id_col] if id_col < len(row) else ""
        if key and sf_id:
            result[key] = sf_id
    return result
