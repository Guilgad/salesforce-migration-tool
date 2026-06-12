"""Unit tests for modules/db_freshness and modules/profile_store."""
from __future__ import annotations
import json
import time
from pathlib import Path
import pytest

# ── Part 2: db_freshness ──────────────────────────────────────────────────────
from modules.db_freshness import days_since_modified, freshness_label


def test_days_since_modified_today():
    from datetime import datetime, timezone
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    assert days_since_modified(now_str) == 0


def test_days_since_modified_eight_days_ago():
    from datetime import datetime, timezone, timedelta
    old = datetime.now(timezone.utc) - timedelta(days=8)
    assert days_since_modified(old.strftime("%Y-%m-%dT%H:%M:%SZ")) == 8


def test_days_since_modified_empty_string():
    assert days_since_modified("") is None


def test_days_since_modified_bad_string():
    assert days_since_modified("not-a-date") is None


def test_freshness_label_today():
    assert freshness_label(0) == "🟢 עודכן היום"


def test_freshness_label_two_days():
    assert freshness_label(2) == "🟡 עודכן לפני 2 ימים"


def test_freshness_label_eight_days():
    label = freshness_label(8)
    assert "8" in label and "מומלץ לרענן" in label


def test_freshness_label_none():
    assert freshness_label(None) == ""


# ── Part 1: profile_store ─────────────────────────────────────────────────────
import modules.profile_store as ps
from modules.profile_store import (
    schema_to_dict, schema_from_dict,
    save_profile, load_profile, list_profiles, delete_profile, match_score,
)
from config.runtime_schema import (
    RuntimeSchema, ObjectDef, ColumnMapping, ValueMap, ValueMapEntry,
    IdentityConfig, LookupConfig, JunctionConfig, ExtraField,
    ROLE_FIELD, ST_OK, ST_CHECK,
)


def _minimal_schema() -> RuntimeSchema:
    s = RuntimeSchema()
    s.input_sheet_id = "abc123"
    s.input_tab = "Sheet1"
    s.objects = [ObjectDef("Contact", "אנשי קשר", 1)]
    return s


# ── round-trip tests ──────────────────────────────────────────────────────────

def test_round_trip_minimal_schema():
    s = _minimal_schema()
    restored = schema_from_dict(schema_to_dict(s))
    assert restored.input_sheet_id == "abc123"
    assert len(restored.objects) == 1
    assert restored.objects[0].api_name == "Contact"


def test_round_trip_mappings_int_keys():
    s = RuntimeSchema()
    s.mappings = {
        2: ColumnMapping(col_index=2, object_api="Contact", field_api="FirstName", status=ST_OK),
        5: ColumnMapping(col_index=5, object_api="Campaign", field_api="Name", status=ST_OK),
    }
    d = schema_to_dict(s)
    assert "2" in d["mappings"] and "5" in d["mappings"]  # JSON keys are strings
    restored = schema_from_dict(d)
    assert 2 in restored.mappings and 5 in restored.mappings  # restored as ints
    assert restored.mappings[2].field_api == "FirstName"


def test_round_trip_value_maps():
    s = RuntimeSchema()
    s.value_maps = {3: ValueMap(
        entries=[ValueMapEntry("חברתי", "012ABC", "חברתי")], default=""
    )}
    restored = schema_from_dict(schema_to_dict(s))
    assert 3 in restored.value_maps
    assert restored.value_maps[3].entries[0].source == "חברתי"


def test_round_trip_digits_only_fields():
    s = RuntimeSchema()
    s.digits_only_fields = {"ID_Number__c", "MobilePhone"}
    d = schema_to_dict(s)
    assert isinstance(d["digits_only_fields"], list)
    restored = schema_from_dict(d)
    assert isinstance(restored.digits_only_fields, set)
    assert "ID_Number__c" in restored.digits_only_fields


def test_round_trip_junction_field_mappings_are_tuples():
    s = RuntimeSchema()
    jc = JunctionConfig(
        object_a="Contact", block_a="A", object_b="Campaign", block_b="B",
        junction_object="CampaignMember", id_field_a="ContactId", id_field_b="CampaignId",
        field_mappings=[("Status__c", 7), ("Role__c", 9)],
    )
    s.junctions = [jc]
    d = schema_to_dict(s)
    assert d["junctions"][0]["field_mappings"] == [["Status__c", 7], ["Role__c", 9]]
    restored = schema_from_dict(d)
    fm = restored.junctions[0].field_mappings
    assert fm == [("Status__c", 7), ("Role__c", 9)]
    assert isinstance(fm[0], tuple)


def test_round_trip_junction_control_col_index_none():
    s = RuntimeSchema()
    jc = JunctionConfig("Contact", "A", "Campaign", "B", "CM", "ContactId", "CampaignId")
    s.junctions = [jc]
    restored = schema_from_dict(schema_to_dict(s))
    assert restored.junctions[0].control_col_index is None


def test_round_trip_identity_config():
    s = RuntimeSchema()
    s.identity = {"Contact": IdentityConfig(mechanisms=[["Email"], ["LastName"]], dedup_internal=True)}
    restored = schema_from_dict(schema_to_dict(s))
    assert restored.identity["Contact"].dedup_internal is True
    assert restored.identity["Contact"].mechanisms[0] == ["Email"]


def test_round_trip_lookup_config():
    s = RuntimeSchema()
    s.lookups = [LookupConfig("Contact", 3, "Account", "AccountId", ["Name"])]
    restored = schema_from_dict(schema_to_dict(s))
    assert restored.lookups[0].source_col_index == 3


def test_round_trip_extra_field():
    s = RuntimeSchema()
    s.extra_fields = [ExtraField("Contact", "LeadSource", "Web")]
    restored = schema_from_dict(schema_to_dict(s))
    assert restored.extra_fields[0].constant_value == "Web"


def test_round_trip_empty_schema():
    s = RuntimeSchema()
    restored = schema_from_dict(schema_to_dict(s))
    assert restored.input_sheet_id == ""
    assert restored.mappings == {}
    assert restored.digits_only_fields == set()


def test_schema_to_dict_is_json_serialisable():
    s = _minimal_schema()
    s.digits_only_fields = {"Phone"}
    s.junctions = [JunctionConfig("A", "a", "B", "b", "J", "Af", "Bf",
                                  field_mappings=[("X", 1)])]
    assert isinstance(json.dumps(schema_to_dict(s)), str)


# ── save / load / list / delete ───────────────────────────────────────────────

def test_save_profile_creates_file(tmp_path, monkeypatch):
    monkeypatch.setattr(ps, "_PROFILES_DIR", tmp_path)
    path = save_profile("Test Profile", _minimal_schema(), ["שם פרטי", "אימייל"])
    assert path.exists() and path.suffix == ".json"


def test_save_profile_file_content(tmp_path, monkeypatch):
    monkeypatch.setattr(ps, "_PROFILES_DIR", tmp_path)
    path = save_profile("My Profile", _minimal_schema(), ["col1", "col2"])
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["name"] == "My Profile"
    assert data["column_labels"] == ["col1", "col2"]
    assert "schema" in data


def test_save_profile_empty_name_raises(tmp_path, monkeypatch):
    monkeypatch.setattr(ps, "_PROFILES_DIR", tmp_path)
    with pytest.raises(ValueError):
        save_profile("   ", _minimal_schema(), [])


def test_load_profile_round_trip(tmp_path, monkeypatch):
    monkeypatch.setattr(ps, "_PROFILES_DIR", tmp_path)
    s = _minimal_schema()
    s.objects = [ObjectDef("Contact", "אנשי קשר"), ObjectDef("Campaign", "קמפיינים")]
    path = save_profile("Round Trip", s, ["Label A", "Label B"])
    name, loaded, labels = load_profile(path)
    assert name == "Round Trip"
    assert labels == ["Label A", "Label B"]
    assert len(loaded.objects) == 2


def test_load_profile_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_profile(tmp_path / "nonexistent.json")


def test_list_profiles_empty_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(ps, "_PROFILES_DIR", tmp_path)
    assert list_profiles() == []


def test_list_profiles_returns_entries_newest_first(tmp_path, monkeypatch):
    monkeypatch.setattr(ps, "_PROFILES_DIR", tmp_path)
    save_profile("Alpha", _minimal_schema(), ["a"])
    time.sleep(0.002)   # ensure different ms timestamps
    save_profile("Beta", _minimal_schema(), ["b"])
    profiles = list_profiles()
    assert len(profiles) == 2
    assert profiles[0]["name"] == "Beta"   # newest first
    assert profiles[1]["name"] == "Alpha"


def test_list_profiles_ignores_corrupt_file(tmp_path, monkeypatch):
    monkeypatch.setattr(ps, "_PROFILES_DIR", tmp_path)
    (tmp_path / "bad.json").write_text("not json", encoding="utf-8")
    save_profile("Good", _minimal_schema(), [])
    profiles = list_profiles()
    assert len(profiles) == 1 and profiles[0]["name"] == "Good"


def test_list_profiles_nonexistent_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(ps, "_PROFILES_DIR", tmp_path / "no_such_dir")
    assert list_profiles() == []


def test_delete_profile_removes_file(tmp_path, monkeypatch):
    monkeypatch.setattr(ps, "_PROFILES_DIR", tmp_path)
    path = save_profile("To Delete", _minimal_schema(), [])
    delete_profile(path)
    assert not path.exists()


def test_delete_profile_silent_on_missing(tmp_path):
    delete_profile(tmp_path / "ghost.json")   # must not raise


# ── match_score ───────────────────────────────────────────────────────────────

def test_match_score_full_match():
    assert match_score(["שם פרטי", "אימייל", "עיר"], ["שם פרטי", "אימייל", "עיר"]) == 3


def test_match_score_partial():
    assert match_score(["שם פרטי", "אימייל", "עיר"], ["שם פרטי", "טלפון"]) == 1


def test_match_score_no_match():
    assert match_score(["שם פרטי", "אימייל"], ["טלפון", "כתובת"]) == 0


def test_match_score_strips_whitespace():
    assert match_score([" שם פרטי "], ["שם פרטי"]) == 1


def test_match_score_empty_profile():
    assert match_score([], ["שם פרטי"]) == 0


def test_match_score_empty_input():
    assert match_score(["שם פרטי"], []) == 0
