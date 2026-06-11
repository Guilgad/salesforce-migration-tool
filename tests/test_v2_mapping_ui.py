# tests/test_v2_mapping_ui.py
"""AppTest — בדיקות-עשן למסך-המיפוי של v2 (שלב 2)."""
from streamlit.testing.v1 import AppTest

from config.runtime_schema import RuntimeSchema

_INPUT = [
    ["Contact", "", "Campaign"],
    ["שם פרטי", "אימייל", "שם קמפיין"],
    ["", "", ""],
    ["יוסי", "a@b.com", "כנס 2025"],
]
_FD = [
    ["EntityDefinition.QualifiedApiName", "EntityDefinition.Label",
     "Label", "QualifiedApiName", "DataType"],
    ["Contact", "Contact", "שם פרטי", "FirstName", "Text"],
    ["Contact", "Contact", "Email", "Email", "Email"],
    ["Campaign", "Campaign", "Campaign Name", "Name", "Text"],
]


def _app(with_data: bool = True) -> AppTest:
    at = AppTest.from_file("main.py")
    at.session_state["step"] = 2
    if with_data:
        at.session_state["schema"] = RuntimeSchema(input_sheet_id="x", input_tab="t")
        at.session_state["input_rows"] = _INPUT
        at.session_state["fielddict_rows"] = _FD
    at.run()
    return at


def test_mapping_screen_renders_without_exception():
    at = _app()
    assert not at.exception


def test_mapping_screen_guard_without_connections():
    at = _app(with_data=False)
    assert not at.exception
