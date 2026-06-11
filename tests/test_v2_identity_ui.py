# tests/test_v2_identity_ui.py
"""AppTest — בדיקות-עשן למסך-הזיהוי של v2 (שלב 3)."""
from streamlit.testing.v1 import AppTest

from config.runtime_schema import (
    RuntimeSchema, ObjectDef, ColumnMapping, IdentityConfig, ROLE_FIELD, ST_OK,
)

_FD = [
    ["EntityDefinition.QualifiedApiName", "EntityDefinition.Label",
     "Label", "QualifiedApiName", "DataType"],
    ["Contact", "Contact", "Email", "Email", "Email"],
    ["Contact", "Contact", "Last Name", "LastName", "Text"],
    ["Account", "Account", "Account Name", "Name", "Text"],
]


def _schema() -> RuntimeSchema:
    s = RuntimeSchema(input_sheet_id="x", input_tab="t")
    s.objects.append(ObjectDef("Contact", "Contact"))
    s.mappings[0] = ColumnMapping(
        col_index=0, object_api="Contact", field_api="Email",
        role=ROLE_FIELD, status=ST_OK,
    )
    s.mappings[1] = ColumnMapping(
        col_index=1, object_api="Contact", field_api="LastName",
        role=ROLE_FIELD, status=ST_OK,
    )
    return s


def _app(with_data: bool = True) -> AppTest:
    at = AppTest.from_file("main.py")
    at.session_state["step"] = 3
    if with_data:
        at.session_state["schema"] = _schema()
        at.session_state["fielddict_rows"] = _FD
    at.run()
    return at


def test_identity_screen_renders_without_exception():
    at = _app()
    assert not at.exception
    # טוגל-dedup קיים וכבוי כברירת-מחדל
    toggles = [t for t in at.toggle if "כפילויות" in t.label]
    assert toggles and toggles[0].value is False


def test_identity_screen_guard_without_data():
    at = _app(with_data=False)
    assert not at.exception


def test_identity_saved_mechanisms_survive_rerun():
    at = _app()
    schema: RuntimeSchema = at.session_state["schema"]
    schema.identity["Contact"] = IdentityConfig(mechanisms=[["Email"], ["LastName"]])
    at.run()
    assert not at.exception
    schema = at.session_state["schema"]
    assert schema.identity["Contact"].mechanisms[0] == ["Email"]
