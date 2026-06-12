"""Tests for modules/junction_builder.py."""
import pytest
from config.runtime_schema import JunctionConfig
from modules import junction_builder
from modules.dedup_engine import DedupResult, PersonResult
from modules.splitter import SplitRecord


# ── minimal fixtures ─────────────────────────────────────────────────────────

def _split(source_row: int, block: str, values: dict) -> SplitRecord:
    return SplitRecord(object_api="", block=block, source_row=source_row, values=values)


def _dedup(local_keys: list[str], record_indices_per_key: list[list[int]]) -> DedupResult:
    persons = [
        PersonResult(
            local_key=lk,
            record_indices=ri,
            action="Insert",
            sf_id=None,
            found_by=None,
            ambiguous=False,
            unkeyed=False,
        )
        for lk, ri in zip(local_keys, record_indices_per_key)
    ]
    return DedupResult(persons=persons, counts={})


# ── shared config ────────────────────────────────────────────────────────────

CM_CFG = JunctionConfig(
    object_a="Contact", block_a="C",
    object_b="Campaign", block_b="K",
    junction_object="CampaignMember",
    id_field_a="ContactId", id_field_b="CampaignId",
)

REL_CFG = JunctionConfig(
    object_a="Contact", block_a="Primary",
    object_b="Contact", block_b="Secondary",
    junction_object="npe4__Relationship__c",
    id_field_a="npe4__Contact__c", id_field_b="npe4__RelatedContact__c",
    symmetric=True,
)


# ── derive_junctions ─────────────────────────────────────────────────────────

def test_basic_junction_one_row():
    """One row with both sides present → one junction record."""
    split_a = [_split(3, "C", {"FirstName": "Alice"})]
    dedup_a = _dedup(["C1"], [[0]])
    split_b = [_split(3, "K", {})]
    dedup_b = _dedup(["K1"], [[0]])
    id_map_a = {"C1": "003xx"}
    id_map_b = {"K1": "701xx"}

    records = junction_builder.derive_junctions(
        tmpl_rows=[[], [], [], ["", ""]],
        _columns=[],
        split_a=split_a, dedup_a=dedup_a,
        split_b=split_b, dedup_b=dedup_b,
        id_map_a=id_map_a, id_map_b=id_map_b,
        db_pairs=set(),
        config=CM_CFG,
        data_start_row=3,
    )
    assert len(records) == 1
    r = records[0]
    assert r.sf_id_a == "003xx"
    assert r.sf_id_b == "701xx"
    assert r.warning is None
    assert r.exists_in_db is False


def test_missing_side_b_id_produces_warning():
    split_a = [_split(3, "C", {})]
    dedup_a = _dedup(["C1"], [[0]])
    split_b = [_split(3, "K", {})]
    dedup_b = _dedup(["K1"], [[0]])
    id_map_a = {"C1": "003xx"}
    id_map_b = {}

    records = junction_builder.derive_junctions(
        tmpl_rows=[[], [], [], []],
        _columns=[],
        split_a=split_a, dedup_a=dedup_a,
        split_b=split_b, dedup_b=dedup_b,
        id_map_a=id_map_a, id_map_b=id_map_b,
        db_pairs=set(),
        config=CM_CFG,
        data_start_row=3,
    )
    assert len(records) == 1
    assert records[0].warning is not None
    assert records[0].sf_id_b == ""


def test_missing_side_a_id_produces_warning():
    split_a = [_split(3, "C", {})]
    dedup_a = _dedup(["C1"], [[0]])
    split_b = [_split(3, "K", {})]
    dedup_b = _dedup(["K1"], [[0]])

    records = junction_builder.derive_junctions(
        tmpl_rows=[[], [], [], []],
        _columns=[],
        split_a=split_a, dedup_a=dedup_a,
        split_b=split_b, dedup_b=dedup_b,
        id_map_a={}, id_map_b={"K1": "701xx"},
        db_pairs=set(),
        config=CM_CFG,
        data_start_row=3,
    )
    assert records[0].warning is not None


def test_control_column_false_skips_row():
    tmpl_rows = [[], [], [], ["", "FALSE", ""]]
    cfg = JunctionConfig(
        object_a="Contact", block_a="C",
        object_b="Campaign", block_b="K",
        junction_object="CampaignMember",
        id_field_a="ContactId", id_field_b="CampaignId",
        control_col_index=1,
    )
    split_a = [_split(3, "C", {})]
    dedup_a = _dedup(["C1"], [[0]])
    split_b = [_split(3, "K", {})]
    dedup_b = _dedup(["K1"], [[0]])

    records = junction_builder.derive_junctions(
        tmpl_rows=tmpl_rows,
        _columns=[],
        split_a=split_a, dedup_a=dedup_a,
        split_b=split_b, dedup_b=dedup_b,
        id_map_a={"C1": "003xx"}, id_map_b={"K1": "701xx"},
        db_pairs=set(),
        config=cfg,
        data_start_row=3,
    )
    assert records == []


def test_control_column_true_includes_row():
    tmpl_rows = [[], [], [], ["", "TRUE", ""]]
    cfg = JunctionConfig(
        object_a="Contact", block_a="C",
        object_b="Campaign", block_b="K",
        junction_object="CampaignMember",
        id_field_a="ContactId", id_field_b="CampaignId",
        control_col_index=1,
    )
    split_a = [_split(3, "C", {})]
    dedup_a = _dedup(["C1"], [[0]])
    split_b = [_split(3, "K", {})]
    dedup_b = _dedup(["K1"], [[0]])

    records = junction_builder.derive_junctions(
        tmpl_rows=tmpl_rows,
        _columns=[],
        split_a=split_a, dedup_a=dedup_a,
        split_b=split_b, dedup_b=dedup_b,
        id_map_a={"C1": "003xx"}, id_map_b={"K1": "701xx"},
        db_pairs=set(),
        config=cfg,
        data_start_row=3,
    )
    assert len(records) == 1


def test_control_column_hebrew_lo_skips():
    tmpl_rows = [[], [], [], ["", "לא", ""]]
    cfg = JunctionConfig(
        object_a="Contact", block_a="C", object_b="Campaign", block_b="K",
        junction_object="CampaignMember", id_field_a="ContactId", id_field_b="CampaignId",
        control_col_index=1,
    )
    split_a = [_split(3, "C", {})]
    dedup_a = _dedup(["C1"], [[0]])
    split_b = [_split(3, "K", {})]
    dedup_b = _dedup(["K1"], [[0]])
    records = junction_builder.derive_junctions(
        tmpl_rows=tmpl_rows, _columns=[],
        split_a=split_a, dedup_a=dedup_a,
        split_b=split_b, dedup_b=dedup_b,
        id_map_a={"C1": "003xx"}, id_map_b={"K1": "701xx"},
        db_pairs=set(), config=cfg, data_start_row=3,
    )
    assert records == []


def test_exists_in_db_flagged():
    split_a = [_split(3, "C", {})]
    dedup_a = _dedup(["C1"], [[0]])
    split_b = [_split(3, "K", {})]
    dedup_b = _dedup(["K1"], [[0]])
    db_pairs = {("003xx", "701xx")}

    records = junction_builder.derive_junctions(
        tmpl_rows=[[], [], [], []],
        _columns=[],
        split_a=split_a, dedup_a=dedup_a,
        split_b=split_b, dedup_b=dedup_b,
        id_map_a={"C1": "003xx"}, id_map_b={"K1": "701xx"},
        db_pairs=db_pairs,
        config=CM_CFG,
        data_start_row=3,
    )
    assert records[0].exists_in_db is True
    assert records[0].warning is None


def test_symmetric_db_check_both_orders():
    """symmetric=True: sorted pair means A↔B = B↔A."""
    split_a = [_split(3, "Primary", {})]
    dedup_a = _dedup(["C1"], [[0]])
    split_b = [_split(3, "Secondary", {})]
    dedup_b = _dedup(["C2"], [[0]])
    db_pairs = {("003aa", "003bb")}

    records = junction_builder.derive_junctions(
        tmpl_rows=[[], [], [], []],
        _columns=[],
        split_a=split_a, dedup_a=dedup_a,
        split_b=split_b, dedup_b=dedup_b,
        id_map_a={"C1": "003bb"}, id_map_b={"C2": "003aa"},
        db_pairs=db_pairs,
        config=REL_CFG,
        data_start_row=3,
    )
    assert records[0].exists_in_db is True


def test_row_without_side_b_block_skipped():
    split_a = [_split(3, "C", {})]
    dedup_a = _dedup(["C1"], [[0]])
    split_b = []
    dedup_b = _dedup([], [])

    records = junction_builder.derive_junctions(
        tmpl_rows=[[], [], [], []],
        _columns=[],
        split_a=split_a, dedup_a=dedup_a,
        split_b=split_b, dedup_b=dedup_b,
        id_map_a={"C1": "003xx"}, id_map_b={},
        db_pairs=set(),
        config=CM_CFG,
        data_start_row=3,
    )
    assert records == []


def test_field_mappings_extracted():
    cfg = JunctionConfig(
        object_a="Contact", block_a="C", object_b="Campaign", block_b="K",
        junction_object="CampaignMember", id_field_a="ContactId", id_field_b="CampaignId",
        field_mappings=[("Status", 2)],
    )
    tmpl_rows = [[], [], [], ["", "", "Responded"]]
    split_a = [_split(3, "C", {})]
    dedup_a = _dedup(["C1"], [[0]])
    split_b = [_split(3, "K", {})]
    dedup_b = _dedup(["K1"], [[0]])

    records = junction_builder.derive_junctions(
        tmpl_rows=tmpl_rows, _columns=[],
        split_a=split_a, dedup_a=dedup_a,
        split_b=split_b, dedup_b=dedup_b,
        id_map_a={"C1": "003xx"}, id_map_b={"K1": "701xx"},
        db_pairs=set(), config=cfg, data_start_row=3,
    )
    assert records[0].field_values.get("Status") == "Responded"


# ── build_junction_grid ──────────────────────────────────────────────────────

def _make_records(rows_data: list[dict]) -> list[junction_builder.JunctionRecord]:
    return [
        junction_builder.JunctionRecord(
            source_row=d.get("source_row", 3),
            local_key_a=d.get("local_key_a", "A1"),
            local_key_b=d.get("local_key_b", "B1"),
            sf_id_a=d.get("sf_id_a", "003xx"),
            sf_id_b=d.get("sf_id_b", "701xx"),
            field_values=d.get("field_values", {}),
            exists_in_db=d.get("exists_in_db", False),
            warning=d.get("warning", None),
        )
        for d in rows_data
    ]


def test_grid_has_two_header_rows():
    records = _make_records([{}])
    grid, _ = junction_builder.build_junction_grid(records, CM_CFG)
    assert len(grid) >= 2
    assert grid[0][0] != grid[1][0]  # Hebrew label ≠ API name


def test_grid_id_fields_in_api_header():
    records = _make_records([{}])
    grid, _ = junction_builder.build_junction_grid(records, CM_CFG)
    assert "ContactId" in grid[1]
    assert "CampaignId" in grid[1]


def test_grid_skips_existing_and_warning():
    records = _make_records([
        {"exists_in_db": True},
        {"warning": "חסר Id"},
        {"sf_id_a": "003aa", "sf_id_b": "701bb"},  # valid
    ])
    grid, _ = junction_builder.build_junction_grid(records, CM_CFG)
    assert len(grid) == 3  # 2 headers + 1 valid row


def test_grid_data_row_has_correct_ids():
    records = _make_records([{"sf_id_a": "003aa", "sf_id_b": "701bb"}])
    grid, _ = junction_builder.build_junction_grid(records, CM_CFG)
    data_row = grid[2]
    assert "003aa" in data_row
    assert "701bb" in data_row


def test_grid_extra_field_in_data_row():
    cfg = JunctionConfig(
        object_a="Contact", block_a="C", object_b="Campaign", block_b="K",
        junction_object="CampaignMember", id_field_a="ContactId", id_field_b="CampaignId",
        field_mappings=[("Status", 5)],
    )
    records = _make_records([{"field_values": {"Status": "Responded"}}])
    grid, _ = junction_builder.build_junction_grid(records, cfg)
    assert "Responded" in grid[2]
    assert "Status" in grid[1]


def test_grid_cell_colors_mark_display_column():
    records = _make_records([{}])
    _, cell_colors = junction_builder.build_junction_grid(records, CM_CFG)
    assert len(cell_colors) >= 1
    assert all(c[2] == "red" for c in cell_colors)


# ── db_junction_pairs_from_records ───────────────────────────────────────────

def test_db_pairs_non_symmetric():
    db_records = [{"ContactId": "003xx", "CampaignId": "701yy"}]
    pairs = junction_builder.db_junction_pairs_from_records(db_records, CM_CFG)
    assert ("003xx", "701yy") in pairs


def test_db_pairs_symmetric_sorted():
    db_records = [
        {"npe4__Contact__c": "003bb", "npe4__RelatedContact__c": "003aa"},
    ]
    pairs = junction_builder.db_junction_pairs_from_records(db_records, REL_CFG)
    assert ("003aa", "003bb") in pairs


def test_db_pairs_missing_id_skipped():
    db_records = [{"ContactId": "003xx", "CampaignId": ""}]
    pairs = junction_builder.db_junction_pairs_from_records(db_records, CM_CFG)
    assert len(pairs) == 0


def test_db_pairs_multiple_records():
    db_records = [
        {"ContactId": "003a", "CampaignId": "701a"},
        {"ContactId": "003b", "CampaignId": "701b"},
    ]
    pairs = junction_builder.db_junction_pairs_from_records(db_records, CM_CFG)
    assert len(pairs) == 2
