"""בדיקות-יחידה ל-modules/lookup_resolver.resolve_lookups."""
from config.runtime_schema import RuntimeSchema, ColumnMapping, LookupConfig, ROLE_FIELD, ST_OK
from modules.splitter import SplitRecord
from modules.lookup_resolver import resolve_lookups


def _schema() -> RuntimeSchema:
    s = RuntimeSchema()
    s.mappings = {
        3: ColumnMapping(col_index=3, object_api="Contact", field_api="AccountName",
                         role=ROLE_FIELD, status=ST_OK, instance=1),
    }
    s.lookups = [
        LookupConfig(source_object="Contact", source_col_index=3,
                     target_object="Account", target_field="AccountId",
                     identified_by=["Name"]),
    ]
    return s


def _records(account_name: str):
    return [SplitRecord(object_api="Contact", block="1", source_row=3,
                        values={"FirstName": "Yossi", "AccountName": account_name})]


def _provider(rows):
    return lambda target: rows if target == "Account" else []


def test_resolves_matching_target_to_id():
    s = _schema()
    recs = _records("Acme")
    out, stats = resolve_lookups(recs, "Contact", s.lookups, s,
                                 _provider([{"Name": "Acme", "Id": "001ACME"}]))
    assert out[0].values["AccountId"] == "001ACME"
    assert stats == {"resolved": 1, "unresolved": 0}


def test_unmatched_value_left_blank_and_counted():
    s = _schema()
    out, stats = resolve_lookups(_records("Nope"), "Contact", s.lookups, s,
                                 _provider([{"Name": "Acme", "Id": "001ACME"}]))
    assert out[0].values["AccountId"] == ""
    assert stats == {"resolved": 0, "unresolved": 1}


def test_empty_source_value_not_counted():
    s = _schema()
    out, stats = resolve_lookups(_records(""), "Contact", s.lookups, s,
                                 _provider([{"Name": "Acme", "Id": "001ACME"}]))
    assert out[0].values.get("AccountId", "") == ""
    assert stats == {"resolved": 0, "unresolved": 0}


def test_match_is_case_and_whitespace_insensitive():
    s = _schema()
    out, stats = resolve_lookups(_records("  acme "), "Contact", s.lookups, s,
                                 _provider([{"Name": "Acme", "Id": "001ACME"}]))
    assert out[0].values["AccountId"] == "001ACME"
    assert stats["resolved"] == 1


def test_no_lookups_for_object_is_noop():
    s = _schema()
    out, stats = resolve_lookups(_records("Acme"), "Campaign", s.lookups, s,
                                 _provider([{"Name": "Acme", "Id": "001ACME"}]))
    assert "AccountId" not in out[0].values
    assert stats == {"resolved": 0, "unresolved": 0}
