# tests/test_v2_mapping_ui.py
"""מסך-המיפוי (שלב 2) — בדיקת-מצב אמיתית: מפת-ערכים משפיעה על התצוגה-המקדימה.

(בדיקות ה-render-בלי-קריסה עברו ל-test_v2_screens_smoke.py.)
"""
from streamlit.testing.v1 import AppTest

from config.runtime_schema import RuntimeSchema, ObjectDef, ValueMap, ValueMapEntry

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


# ── בורר-אובייקט פר-שורה: הקצאה לאובייקט שאינו-בלוק (CampaignMember) ──────────

_INPUT_CM = [
    ["Campaign", "Campaign"],          # שורת-אובייקט: שתי העמודות תחת Campaign (אין בלוק CampaignMember)
    ["שם קמפיין", "סטטוס השתתפות"],
    ["", ""],
    ["כנס 2025", "Responded"],
]
_FD_CM = [
    ["EntityDefinition.QualifiedApiName", "EntityDefinition.Label",
     "Label", "QualifiedApiName", "DataType"],
    ["Campaign", "Campaign", "Name", "Name", "Text"],
    ["CampaignMember", "CampaignMember", "Status", "Status", "Picklist"],
]


def test_column_can_be_reassigned_to_junction_object():
    """עמודת 'סטטוס השתתפות' (תחת Campaign בכותרת) ניתנת-להקצאה ל-CampaignMember דרך בורר-האובייקט."""
    at = AppTest.from_file("main.py", default_timeout=15)
    at.session_state["step"] = 2
    at.session_state["schema"] = RuntimeSchema(input_sheet_id="x", input_tab="t")
    at.session_state["input_rows"] = _INPUT_CM
    at.session_state["fielddict_rows"] = _FD_CM
    at.run()
    assert not at.exception
    # בורר-האובייקט של עמודה 1 קיים ומציע CampaignMember
    sel = at.selectbox(key="mapobj_1")
    assert "CampaignMember" in sel.options
    sel.set_value("CampaignMember").run()
    assert not at.exception
    schema = at.session_state["schema"]
    assert schema.mappings[1].object_api == "CampaignMember"


# ── יישור-אות במקור: schema.objects api_name → קאנון המילון, ו-instance_count ──

_INPUT_2CONTACTS = [
    ["contact", "", "contact", ""],     # שורת-אובייקט: 2 בלוקים (בעל/אישה), אותיות-קטנות
    ["שם פרטי", "טלפון", "שם פרטי", "טלפון"],
    ["", "", "", ""],
    ["יוסי", "050", "שרה", "051"],
]
_FD_CONTACT = [
    ["EntityDefinition.QualifiedApiName", "EntityDefinition.Label",
     "Label", "QualifiedApiName", "DataType"],
    ["Contact", "Contact", "First Name", "FirstName", "Text"],
    ["Contact", "Contact", "Phone", "Phone", "Phone"],
]


def test_object_api_name_canonicalized_and_instance_count_set():
    """
    שם-אובייקט בקלט באותיות-קטנות ('contact') מיושר לקאנון-המילון ('Contact') **במקור**
    (`schema.objects[].api_name`), כך ש-`od.instance_count` נכתב נכון לאובייקט רב-מופע.
    זהו שורש באג-ה-case (בורר-מופע לא הופיע ב-Junction). נכשל לפני התיקון:
    schema.objects נשאר 'contact' → חיפוש ה-ObjectDef ב-screen_mapping לא תואם → instance_count=1.
    """
    at = AppTest.from_file("main.py", default_timeout=20)
    at.session_state["step"] = 2
    at.session_state["schema"] = RuntimeSchema(
        input_sheet_id="x", input_tab="t",
        objects=[ObjectDef("contact", "אנשי קשר")],   # אותיות-קטנות, כמו מהכותרת
    )
    at.session_state["input_rows"] = _INPUT_2CONTACTS
    at.session_state["fielddict_rows"] = _FD_CONTACT
    at.run()
    assert not at.exception

    # יישור-אות במקור
    od = at.session_state["schema"].objects[0]
    assert od.api_name == "Contact"

    # סימון "מופיע יותר מפעם אחת" → instance_count נכתב (2 בלוקים)
    at.checkbox(key="multi_Contact").check().run()
    assert not at.exception
    od = at.session_state["schema"].objects[0]
    assert od.instance_count == 2
    assert at.session_state["schema"].multi_instance.get("Contact") is True
