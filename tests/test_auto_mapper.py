# tests/test_auto_mapper.py
from modules.auto_mapper import suggest_field, _norm
from modules.field_dictionary import FieldInfo


def _f(label, api, dt="Text"):
    return FieldInfo(label=label, api=api, datatype=dt)


_FIELDS = [
    _f("שם פרטי", "FirstName"),
    _f("שם משפחה", "LastName"),
    _f("Email", "Email", "Email"),
    _f("טלפון נייד", "MobilePhone", "Phone"),
]


def test_norm_strips_case_spaces_separators():
    assert _norm("First Name") == "firstname"
    assert _norm("first_name") == "firstname"
    assert _norm("First-Name") == "firstname"


def test_exact_hebrew_label_match_is_confident():
    s = suggest_field("שם פרטי", _FIELDS)
    assert s.confident is True
    assert s.field_api == "FirstName"


def test_exact_api_match_case_insensitive():
    s = suggest_field("email", _FIELDS)
    assert s.confident is True
    assert s.field_api == "Email"


def test_two_exact_matches_not_confident():
    fields = [_f("טלפון", "Phone"), _f("טלפון", "HomePhone")]
    s = suggest_field("טלפון", fields)
    assert s.confident is False
    assert set(s.candidates) == {"Phone", "HomePhone"}


def test_fuzzy_unique_above_threshold_is_confident():
    # "mobilephone1" vs "mobilephone" → ratio ≈ 0.956 ≥ 0.9, יחיד
    s = suggest_field("MobilePhone1", _FIELDS)
    assert s.confident is True
    assert s.field_api == "MobilePhone"


def test_fuzzy_two_close_matches_ambiguous():
    fields = [_f("Test Field1", "TestField1"), _f("Test Field2", "TestField2")]
    s = suggest_field("TestField", fields)
    assert s.confident is False
    assert set(s.candidates) == {"TestField1", "TestField2"}


def test_no_match_returns_empty():
    s = suggest_field("צבע אהוב", _FIELDS)
    assert s.confident is False
    assert s.field_api == ""
    assert s.candidates == []


def test_empty_label_or_fields():
    assert suggest_field("", _FIELDS).confident is False
    assert suggest_field("שם", []).confident is False
