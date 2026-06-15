# tests/test_v2_mapping_ui.py
"""מסך-המיפוי (שלב 2) — בדיקת-מצב אמיתית: מפת-ערכים משפיעה על התצוגה-המקדימה.

(בדיקות ה-render-בלי-קריסה עברו ל-test_v2_screens_smoke.py.)
"""
from streamlit.testing.v1 import AppTest

from config.runtime_schema import RuntimeSchema, ValueMap, ValueMapEntry

_INPUT_DATED = [
    ["Contact", "", ""],
    ["שם פרטי", "אימייל", "Birthdate"],
    ["", "", ""],
    ["יוסי", "a@b.com", "15/03/2024"],
]
_FD_DATED = [
    ["EntityDefinition.QualifiedApiName", "EntityDefinition.Label",
     "Label", "QualifiedApiName", "DataType"],
    ["Contact", "Contact", "Birthdate", "Birthdate", "Date"],
]


def test_value_map_preview_integration():
    """מפת-ערכים שמורה בסכמה משפיעה על התצוגה-המקדימה (כולל שם-תצוגה)."""
    at = AppTest.from_file("main.py")
    at.session_state["step"] = 2
    schema = RuntimeSchema(input_sheet_id="x", input_tab="t")
    # עמודה 2 = Birthdate (ממופה אוטומטית); המפה גוברת על פירמוט ה-Date
    schema.value_maps[2] = ValueMap(
        entries=[ValueMapEntry("15/03/2024", "MAPPED", "מתורגם")]
    )
    at.session_state["schema"] = schema
    at.session_state["input_rows"] = _INPUT_DATED
    at.session_state["fielddict_rows"] = _FD_DATED
    at.run()
    assert not at.exception
    caps = " ".join(c.value for c in at.caption)
    assert "MAPPED (מתורגם)" in caps
