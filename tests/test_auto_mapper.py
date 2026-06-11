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


from config.runtime_schema import ROLE_SKIP, ROLE_FIELD, ST_OK, ST_CHECK
from modules.auto_mapper import build_mappings
from modules.field_dictionary import ObjectInfo
from modules.mapper import TemplateColumn


def _col(index, object_api, label, proposed_api=""):
    return TemplateColumn(
        index=index, block=object_api, label=label,
        proposed_api=proposed_api, object_api=object_api,
    )


def _dict():
    return {
        "Contact": ObjectInfo(api="Contact", label="Contact", fields=[
            _f("שם פרטי", "FirstName"),
            _f("Email", "Email", "Email"),
        ]),
        "Campaign": ObjectInfo(api="Campaign", label="Campaign", fields=[
            _f("Campaign Name", "Name"),
        ]),
    }


def test_file_api_valid_is_ok_file():
    cols = [_col(0, "Contact", "אימייל", "Email")]
    m = build_mappings(cols, _dict())[0]
    assert (m.status, m.source, m.field_api) == (ST_OK, "file", "Email")


def test_file_api_decorated_is_cleaned():
    cols = [_col(0, "Campaign", "שם", "Name (Campaign Name)")]
    m = build_mappings(cols, _dict())[0]
    assert (m.status, m.field_api) == (ST_OK, "Name")


def test_file_api_invalid_is_check_with_candidates():
    cols = [_col(0, "Contact", "Email", "EmialTypo__c")]
    m = build_mappings(cols, _dict())[0]
    assert (m.status, m.source) == (ST_CHECK, "file")
    assert "Email" in m.candidates


def test_known_standard_field_is_valid():
    # FirstName הוא רכיב של שדה מורכב — תקף גם אם לא במילון (KNOWN_STANDARD_FIELDS)
    d = {"Contact": ObjectInfo(api="Contact", label="Contact", fields=[])}
    cols = [_col(0, "Contact", "שם פרטי", "FirstName")]
    m = build_mappings(cols, d)[0]
    assert m.status == ST_OK


def test_empty_api_confident_label_automaps():
    cols = [_col(0, "Contact", "שם פרטי")]
    m = build_mappings(cols, _dict())[0]
    assert (m.status, m.source, m.field_api) == (ST_OK, "auto", "FirstName")


def test_empty_api_ambiguous_is_check():
    d = {"Contact": ObjectInfo(api="Contact", label="Contact", fields=[
        _f("טלפון", "Phone"), _f("טלפון", "HomePhone"),
    ])}
    cols = [_col(0, "Contact", "טלפון")]
    m = build_mappings(cols, d)[0]
    assert m.status == ST_CHECK
    assert set(m.candidates) == {"Phone", "HomePhone"}


def test_empty_api_no_match_is_check_empty():
    cols = [_col(0, "Contact", "צבע אהוב")]
    m = build_mappings(cols, _dict())[0]
    assert (m.status, m.field_api, m.candidates) == (ST_CHECK, "", [])


def test_spacer_column_is_skip():
    cols = [_col(2, "Contact", "", "")]
    m = build_mappings(cols, _dict())[2]
    assert m.role == ROLE_SKIP


def test_no_object_column_is_skip():
    cols = [_col(0, "", "הערות כלליות")]
    m = build_mappings(cols, _dict())[0]
    assert m.role == ROLE_SKIP


def test_object_missing_from_dict_is_check_no_candidates():
    cols = [_col(0, "Lead", "שם", "LastName")]
    m = build_mappings(cols, _dict())[0]
    assert (m.status, m.candidates) == (ST_CHECK, [])
