"""מסך-קשרים (שלב 4): בדיקות-לוגיקה ל-_load_order + טענות-תוכן אמיתיות.

(בדיקות ה-render-בלי-קריסה עברו ל-test_v2_screens_smoke.py.)
"""
from streamlit.testing.v1 import AppTest
from config.runtime_schema import (
    RuntimeSchema, ObjectDef, IdentityConfig, LookupConfig, JunctionConfig,
)
import main as main_module


# ── _load_order — בדיקות-לוגיקה טהורות (סדר-טעינה טופולוגי) ───────────────────

def test_load_order_junction_after_parents():
    """אובייקט-junction נטען אחרי שני ההורים."""
    schema = RuntimeSchema(
        objects=[ObjectDef("Contact", "אנשי קשר"), ObjectDef("Campaign", "קמפיינים")],
        junctions=[JunctionConfig(
            object_a="Contact", block_a="C", object_b="Campaign", block_b="K",
            junction_object="CampaignMember", id_field_a="ContactId", id_field_b="CampaignId",
        )],
    )
    flat = [o for tier in main_module._load_order(schema) for o in tier]
    assert flat.index("CampaignMember") > flat.index("Contact")
    assert flat.index("CampaignMember") > flat.index("Campaign")


def test_load_order_junction_object_included():
    schema = RuntimeSchema(
        objects=[ObjectDef("Contact", "אנשי קשר")],
        junctions=[JunctionConfig(
            object_a="Contact", block_a="C", object_b="Contact", block_b="D",
            junction_object="npe4__Relationship__c",
            id_field_a="npe4__Contact__c", id_field_b="npe4__RelatedContact__c",
            symmetric=True,
        )],
    )
    flat = [o for tier in main_module._load_order(schema) for o in tier]
    assert "npe4__Relationship__c" in flat


def test_load_order_lookup_target_before_source():
    """יעד-Lookup נטען לפני אובייקט-המקור."""
    schema = RuntimeSchema(
        objects=[ObjectDef("Contact", "אנשי קשר"), ObjectDef("Account", "חשבונות")],
        lookups=[LookupConfig("Contact", 3, "Account", "AccountId", ["Name"])],
    )
    flat = [o for tier in main_module._load_order(schema) for o in tier]
    assert flat.index("Account") < flat.index("Contact")


# ── טענות-תוכן אמיתיות במסך (לא render-בלבד) ─────────────────────────────────

def _at_step4(schema) -> AppTest:
    at = AppTest.from_file("main.py", default_timeout=10)
    at.session_state["step"] = 4
    at.session_state["schema"] = schema
    at.run()
    return at


def test_existing_lookup_shown_in_screen():
    schema = RuntimeSchema(
        objects=[ObjectDef("Contact", "אנשי קשר"), ObjectDef("Account", "חשבונות")],
        identity={"Contact": IdentityConfig(mechanisms=[["Email"]]),
                  "Account": IdentityConfig(mechanisms=[["Name"]])},
        lookups=[LookupConfig("Contact", 3, "Account", "AccountId", ["Name"])],
    )
    at = _at_step4(schema)
    assert not at.exception
    text = " ".join(str(e.value) for e in list(at.markdown) + list(at.caption))
    assert "AccountId" in text or "Account" in text


def test_existing_junction_shown_in_screen():
    schema = RuntimeSchema(
        objects=[ObjectDef("Contact", "אנשי קשר"), ObjectDef("Campaign", "קמפיינים")],
        junctions=[JunctionConfig(
            object_a="Contact", block_a="C", object_b="Campaign", block_b="K",
            junction_object="CampaignMember", id_field_a="ContactId", id_field_b="CampaignId",
        )],
    )
    at = _at_step4(schema)
    assert not at.exception
    text = " ".join(str(e.value) for e in list(at.markdown))
    assert "CampaignMember" in text  # מופיע גם ברשימת-הקשרים וגם בסדר-הטעינה


# ── טופס-Junction חכם: בורר-מופע + dropdown-Id + הוספה מודעת-מופע ──────────────

_FD_JUNCTION = [
    ["EntityDefinition.QualifiedApiName", "EntityDefinition.Label",
     "Label", "QualifiedApiName", "DataType"],
    ["Contact", "Contact", "Last Name", "LastName", "Text"],
    ["npe4__Relationship__c", "Relationship", "Contact", "npe4__Contact__c", "Lookup()"],
    ["npe4__Relationship__c", "Relationship", "Related", "npe4__RelatedContact__c", "Lookup()"],
    ["npe4__Relationship__c", "Relationship", "Type", "npe4__Type__c", "Picklist"],
]


def test_junction_form_instance_picker_and_smart_id_fields():
    """אובייקט רב-מופע (Contact×2) → בורר-מופע; אובייקט-Junction ושדות-Id כ-dropdown;
    הוספת קשר בעל↔אישה שומרת block_a='1'/block_b='2' (מודעות-מופע)."""
    schema = RuntimeSchema(
        objects=[ObjectDef("Contact", "אנשי קשר", instance_count=2)],
        multi_instance={"Contact": True},
    )
    at = AppTest.from_file("main.py", default_timeout=20)
    at.session_state["step"] = 4
    at.session_state["schema"] = schema
    at.session_state["fielddict_rows"] = _FD_JUNCTION
    at.run()
    assert not at.exception

    # בורר-מופע מופיע לשני הצדדים (Contact רב-מופע)
    assert at.selectbox(key="jnc_inst_a")
    assert at.selectbox(key="jnc_inst_b")

    # אובייקט-Junction = dropdown מהמילון (לא text_input)
    jobj = at.selectbox(key="jnc_junction_obj")
    assert "npe4__Relationship__c" in jobj.options
    jobj.set_value("npe4__Relationship__c").run()

    # שדות-Id = dropdown משדות אובייקט-ה-Junction
    id_a = at.selectbox(key="jnc_id_a")
    assert any("npe4__Contact__c" in o for o in id_a.options)

    # קשר בעל↔אישה: מופע 1 ↔ מופע 2
    at.selectbox(key="jnc_inst_a").set_value("1").run()
    at.selectbox(key="jnc_inst_b").set_value("2").run()
    at.button(key="jnc_add").click().run()
    assert not at.exception

    js = at.session_state["schema"].junctions
    assert len(js) == 1
    assert js[0].block_a == "1" and js[0].block_b == "2"
    assert js[0].junction_object == "npe4__Relationship__c"
    assert js[0].id_field_a == "npe4__Contact__c"
