# tests/test_v2_identity_ui.py
"""מסך-הזיהוי (שלב 3) — בדיקות-מצב אמיתיות (לא smoke).

טענות-נכונות: טוגל-ה-dedup כבוי כברירת-מחדל, ומנגנונים שמורים שורדים rerun.
(בדיקת ה-render-בלי-קריסה עברה ל-test_v2_screens_smoke.py.)
"""
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


def _app() -> AppTest:
    at = AppTest.from_file("main.py")
    at.session_state["step"] = 3
    at.session_state["schema"] = _schema()
    at.session_state["fielddict_rows"] = _FD
    at.run()
    return at


def test_dedup_toggle_defaults_off():
    """טוגל 'זיהוי כפילויות פנימיות' קיים וכבוי כברירת-מחדל (שום רשומה לא נעלמת)."""
    at = _app()
    assert not at.exception
    toggles = [t for t in at.toggle if "כפילויות" in t.label]
    assert toggles and toggles[0].value is False


def test_saved_mechanisms_survive_rerun():
    at = _app()
    schema: RuntimeSchema = at.session_state["schema"]
    schema.identity["Contact"] = IdentityConfig(mechanisms=[["Email"], ["LastName"]])
    at.run()
    assert not at.exception
    schema = at.session_state["schema"]
    assert schema.identity["Contact"].mechanisms[0] == ["Email"]
