"""
junction_builder — generic junction / relationship record derivation.

Pure (no I/O): given split+dedup results for two parent objects (A and B),
derives junction records (e.g. CampaignMember, npe4__Relationship__c, or any
custom junction object). Replaces relationship_builder + campaign_member_builder
for the v2 generic engine.

Prerequisites: both parent objects must have been loaded to Salesforce and their
Ids pasted back before derive_junctions can produce non-warning records.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from config.runtime_schema import JunctionConfig
from modules import dedup_engine, mapper, splitter

_NOT_PARTICIPATING = {"", "0", "false", "לא", "no"}


@dataclass
class JunctionRecord:
    """One junction instance derived from a template row."""
    source_row: int
    local_key_a: str
    local_key_b: str
    sf_id_a: str
    sf_id_b: str
    field_values: dict[str, str]
    exists_in_db: bool
    warning: str | None


def _cell(row: list[str], i: int) -> str:
    if 0 <= i < len(row) and row[i] is not None:
        return str(row[i]).strip()
    return ""


def _is_active(value: str) -> bool:
    """Return True if the control column signals 'create this junction'."""
    return str(value).strip().casefold() not in _NOT_PARTICIPATING


def derive_junctions(
    tmpl_rows: list[list[str]],
    columns: list,  # list[mapper.TemplateColumn] — unused in P5; reserved for P6
    split_a: list[splitter.SplitRecord],
    dedup_a: dedup_engine.DedupResult,
    split_b: list[splitter.SplitRecord],
    dedup_b: dedup_engine.DedupResult,
    id_map_a: dict[str, str],
    id_map_b: dict[str, str],
    db_pairs: set[tuple[str, str]],
    *,
    config: JunctionConfig,
    data_start_row: int,
) -> list[JunctionRecord]:
    """
    Derive junction records for every template row that has both A and B present.

    split_a/dedup_a: result of splitting/deduping object A.
    split_b/dedup_b: result of splitting/deduping object B.
    id_map_a/id_map_b: local_key → sf_id (from loaded output grids).
    db_pairs: set of (id_a, id_b) — or sorted pairs for symmetric — already in DB.
    config.block_a / config.block_b: used to filter split records by row.
    config.control_col_index: if set, only rows where that cell is truthy produce a junction.
    config.field_mappings: list of (field_api, col_index) for extra fields on the junction.
    config.symmetric: if True, DB check uses (min, max) sort so A↔B = B↔A.
    """
    # Build (source_row, block) → record_index maps
    row_block_a: dict[tuple[int, str], int] = {}
    for i, rec in enumerate(split_a):
        row_block_a.setdefault((rec.source_row, config.block_a), i)

    row_block_b: dict[tuple[int, str], int] = {}
    for i, rec in enumerate(split_b):
        row_block_b.setdefault((rec.source_row, config.block_b), i)

    # record_index → local_key
    idx_to_key_a: dict[int, str] = {
        idx: p.local_key for p in dedup_a.persons for idx in p.record_indices
    }
    idx_to_key_b: dict[int, str] = {
        idx: p.local_key for p in dedup_b.persons for idx in p.record_indices
    }

    results: list[JunctionRecord] = []
    for r in range(data_start_row, len(tmpl_rows)):
        idx_b = row_block_b.get((r, config.block_b))
        if idx_b is None:
            continue  # no B record on this row → no junction

        # Control column gate
        if config.control_col_index is not None:
            val = _cell(tmpl_rows[r], config.control_col_index)
            if not _is_active(val):
                continue

        idx_a = row_block_a.get((r, config.block_a))
        key_a = idx_to_key_a.get(idx_a, "") if idx_a is not None else ""
        key_b = idx_to_key_b.get(idx_b, "")

        sf_id_a = id_map_a.get(key_a, "") if key_a else ""
        sf_id_b = id_map_b.get(key_b, "") if key_b else ""

        # Extra field values from field_mappings
        field_values: dict[str, str] = {
            api: _cell(tmpl_rows[r], col)
            for api, col in config.field_mappings
        }

        warning: str | None = None
        exists_in_db = False
        if not sf_id_a:
            warning = f"Id חסר לרשומה {key_a or '?'} ({config.object_a}) — יש לטעון קודם"
        elif not sf_id_b:
            warning = f"Id חסר לרשומה {key_b or '?'} ({config.object_b}) — יש לטעון קודם"
        else:
            if config.symmetric:
                pair = (min(sf_id_a, sf_id_b), max(sf_id_a, sf_id_b))
            else:
                pair = (sf_id_a, sf_id_b)
            exists_in_db = pair in db_pairs

        results.append(JunctionRecord(
            source_row=r,
            local_key_a=key_a,
            local_key_b=key_b,
            sf_id_a=sf_id_a,
            sf_id_b=sf_id_b,
            field_values=field_values,
            exists_in_db=exists_in_db,
            warning=warning,
        ))

    return results


_HEADER_ROWS = 2


def build_junction_grid(
    junction_records: list[JunctionRecord],
    config: JunctionConfig,
) -> tuple[list[list[str]], list[tuple[int, int, str]]]:
    """
    Build a 2-header load grid for a set of junction records.

    Row 0: Hebrew display labels.
    Row 1: API field names (id_field_a, id_field_b, then extra fields).
    Data rows: one per valid junction record (skips exists_in_db and warning).

    Returns (grid, cell_colors) where cell_colors marks display-only column (col 0) red.
    """
    extra_apis = [api for api, _ in config.field_mappings]

    header_he = [
        f"{config.object_a} (שם)",
        f"{config.object_a} Id",
        f"{config.object_b} Id",
    ] + extra_apis

    header_api = [
        "",              # display-only — not loaded
        config.id_field_a,
        config.id_field_b,
    ] + extra_apis

    grid: list[list[str]] = [header_he, header_api]
    cell_colors: list[tuple[int, int, str]] = []

    row_idx = 0
    for rec in junction_records:
        if rec.exists_in_db or rec.warning:
            continue
        extra_vals = [rec.field_values.get(api, "") for api in extra_apis]
        grid.append([rec.local_key_a, rec.sf_id_a, rec.sf_id_b] + extra_vals)
        cell_colors.append((_HEADER_ROWS + row_idx, 0, "red"))
        row_idx += 1

    return grid, cell_colors


def db_junction_pairs_from_records(
    db_records: list[dict],
    config: JunctionConfig,
) -> set[tuple[str, str]]:
    """
    Extract (id_a, id_b) pairs from DB records of the junction object.

    config.symmetric=True → pairs stored as (min, max) so A↔B and B↔A are identical.
    Skips records where either Id is empty.
    """
    pairs: set[tuple[str, str]] = set()
    for rec in db_records:
        a = str(rec.get(config.id_field_a, "") or "").strip()
        b = str(rec.get(config.id_field_b, "") or "").strip()
        if a and b:
            if config.symmetric:
                pairs.add((min(a, b), max(a, b)))
            else:
                pairs.add((a, b))
    return pairs
