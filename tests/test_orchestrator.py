"""Tests for modules/orchestrator.py — adapt_columns + output tab naming."""
import pytest
from config.runtime_schema import (
    RuntimeSchema, ColumnMapping,
    ROLE_FIELD, ROLE_CONTROL, ROLE_SKIP,
    ST_OK, ST_CHECK,
)
from modules.orchestrator import adapt_columns, OUTPUT_TAB, OUTPUT_TAB_MANUAL
from modules.mapper import STATUS_VALID, STATUS_CONTROL


def _schema_with_mappings() -> RuntimeSchema:
    s = RuntimeSchema()
    # label_row = 1 is already the default, but set explicitly for clarity
    s.label_row = 1
    s.mappings = {
        0: ColumnMapping(col_index=0, object_api="Contact", field_api="FirstName",
                         role=ROLE_FIELD, status=ST_OK, instance=1),
        1: ColumnMapping(col_index=1, object_api="Contact", field_api="LastName",
                         role=ROLE_FIELD, status=ST_OK, instance=1),
        2: ColumnMapping(col_index=2, object_api="Contact", field_api="Email",
                         role=ROLE_FIELD, status=ST_OK, instance=2),
        3: ColumnMapping(col_index=3, object_api="Contact", field_api="ctrl",
                         role=ROLE_CONTROL, status=ST_OK, instance=1),
        4: ColumnMapping(col_index=4, object_api="Campaign", field_api="Name",
                         role=ROLE_FIELD, status=ST_OK, instance=1),
        5: ColumnMapping(col_index=5, object_api="Contact", field_api="Phone",
                         role=ROLE_SKIP, status=ST_OK, instance=1),
    }
    return s


def _header_rows() -> list:
    return [
        ["Contact", "Contact", "Contact", "Contact", "Campaign", "Contact"],
        ["שם פרטי", "שם משפחה", "אימייל", "השתתף", "שם קמפיין", "טלפון"],
        ["FirstName", "LastName", "Email", "ctrl", "Name", "Phone"],
    ]


def test_adapt_columns_returns_only_target_object():
    s = _schema_with_mappings()
    cols = adapt_columns(s, "Contact", _header_rows())
    assert all(c.object_api == "Contact" for c in cols)
    assert len(cols) == 4  # 3 FIELD + 1 CONTROL (SKIP excluded)


def test_adapt_columns_uses_label_row():
    s = _schema_with_mappings()
    cols = adapt_columns(s, "Contact", _header_rows())
    labels = {c.clean_api: c.label for c in cols}
    assert labels["FirstName"] == "שם פרטי"
    assert labels["LastName"] == "שם משפחה"


def test_adapt_columns_instance_becomes_block():
    s = _schema_with_mappings()
    cols = adapt_columns(s, "Contact", _header_rows())
    email_col = next(c for c in cols if c.clean_api == "Email")
    assert email_col.block == "2"  # instance=2


def test_adapt_columns_role_to_status():
    s = _schema_with_mappings()
    cols = adapt_columns(s, "Contact", _header_rows())
    status_map = {c.clean_api: c.status for c in cols}
    assert status_map["FirstName"] == STATUS_VALID
    assert status_map["ctrl"] == STATUS_CONTROL
    assert "Phone" not in status_map  # SKIP excluded entirely


def test_adapt_columns_sorted_by_index():
    s = _schema_with_mappings()
    cols = adapt_columns(s, "Contact", _header_rows())
    indices = [c.index for c in cols]
    assert indices == sorted(indices)


def test_output_tab_name_convention():
    assert OUTPUT_TAB("Contact") == "פלט - Contact"
    assert OUTPUT_TAB_MANUAL("Contact") == "פלט ידני - Contact"
