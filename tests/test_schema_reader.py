"""
Test schema_reader — detect_objects and read_header_columns.
"""
import pytest
from config.runtime_schema import RuntimeSchema
from modules.schema_reader import detect_objects, read_header_columns
from modules.mapper import STATUS_VALID

# ─── shared fixture ──────────────────────────────────────────────────────────
_ROWS_MULTI = [
    # row 0: object names (forward-fill: empty cells inherit previous)
    ["Contact", "", "", "Campaign", ""],
    # row 1: customer labels
    ["שם פרטי", "שם משפחה", "אימייל", "שם קמפיין", "תאריך התחלה"],
    # row 2: API names
    ["FirstName", "LastName", "Email", "Name", "StartDate"],
    # row 3: data
    ["יוסי", "כהן", "yosi@test.com", "כנס 2025", "01/03/2025"],
]

_ROWS_SINGLE = [
    # row 0: ignored for single-object tables
    ["", "", ""],
    # row 1: customer labels
    ["שם", "אימייל", "טלפון"],
    # row 2: API names
    ["FirstName", "Email", "Phone"],
    # row 3: data
    ["ישראל", "a@b.com", "050-1234567"],
]


def test_detect_objects_unique_in_order():
    result = detect_objects(_ROWS_MULTI, object_row=0)
    assert result == ["Contact", "Campaign"]


def test_detect_objects_skips_empty_cells():
    rows = [["", "", "Contact", "", "Campaign"], [], [], []]
    result = detect_objects(rows, object_row=0)
    assert result == ["Contact", "Campaign"]


def test_detect_objects_empty_row():
    rows = [["", "", ""], [], [], []]
    result = detect_objects(rows, object_row=0)
    assert result == []


def test_detect_objects_out_of_range_row():
    result = detect_objects(_ROWS_MULTI, object_row=99)
    assert result == []


def test_read_header_multi_object_assigns_correct_objects():
    schema = RuntimeSchema(table_type="multi")
    cols = read_header_columns(_ROWS_MULTI, schema)
    obj_apis = [c.object_api for c in cols]
    # Contact forward-fills cols 0-2; Campaign forward-fills cols 3-4
    assert obj_apis == ["Contact", "Contact", "Contact", "Campaign", "Campaign"]


def test_read_header_multi_labels():
    schema = RuntimeSchema(table_type="multi")
    cols = read_header_columns(_ROWS_MULTI, schema)
    assert cols[0].label == "שם פרטי"
    assert cols[3].label == "שם קמפיין"


def test_read_header_multi_proposed_api():
    schema = RuntimeSchema(table_type="multi")
    cols = read_header_columns(_ROWS_MULTI, schema)
    assert cols[0].proposed_api == "FirstName"
    assert cols[4].proposed_api == "StartDate"


def test_read_header_single_object_all_same_object():
    schema = RuntimeSchema(table_type="single", single_object_api="Lead")
    cols = read_header_columns(_ROWS_SINGLE, schema)
    for col in cols:
        assert col.object_api == "Lead"


def test_read_header_single_object_labels():
    schema = RuntimeSchema(table_type="single", single_object_api="Lead")
    cols = read_header_columns(_ROWS_SINGLE, schema)
    assert cols[0].label == "שם"
    assert cols[1].label == "אימייל"


def test_read_header_column_count():
    schema = RuntimeSchema(table_type="multi")
    cols = read_header_columns(_ROWS_MULTI, schema)
    assert len(cols) == 5


def test_read_header_indices_are_sequential():
    schema = RuntimeSchema(table_type="multi")
    cols = read_header_columns(_ROWS_MULTI, schema)
    for i, col in enumerate(cols):
        assert col.index == i
