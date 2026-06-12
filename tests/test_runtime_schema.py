import os
from config.runtime_schema import RuntimeSchema, ObjectDef


def test_default_schema_empty_objects():
    s = RuntimeSchema()
    assert s.objects == []


def test_default_table_type_is_multi():
    s = RuntimeSchema()
    assert s.table_type == "multi"


def test_default_header_rows():
    s = RuntimeSchema()
    assert s.object_row == 0
    assert s.label_row == 1
    assert s.api_row == 2
    assert s.data_start_row == 3


def test_connection_fields_default_empty():
    s = RuntimeSchema()
    assert s.input_sheet_id == ""
    assert s.fielddict_sheet_id == ""
    assert s.db_sheet_id == ""


def test_schema_stores_connection_info():
    s = RuntimeSchema(
        input_sheet_id="abc",
        input_tab="Sheet1",
        fielddict_sheet_id="def",
        db_sheet_id="ghi",
    )
    assert s.input_sheet_id == "abc"
    assert s.input_tab == "Sheet1"
    assert s.fielddict_sheet_id == "def"
    assert s.db_sheet_id == "ghi"


def test_object_def_default_instance_count():
    obj = ObjectDef(api_name="Contact", display_name="Contact")
    assert obj.instance_count == 1


def test_schema_add_object():
    s = RuntimeSchema()
    s.objects.append(ObjectDef("Contact", "Contact"))
    s.objects.append(ObjectDef("Campaign", "Campaign"))
    assert len(s.objects) == 2
    assert s.objects[0].api_name == "Contact"


def test_schema_fielddict_objects_default_empty():
    s = RuntimeSchema()
    assert s.fielddict_objects == []


def test_schema_db_tabs_default_empty_dict():
    s = RuntimeSchema()
    assert s.db_tabs == {}


def test_single_object_api_field():
    s = RuntimeSchema(table_type="single", single_object_api="Lead")
    assert s.single_object_api == "Lead"


from config.runtime_schema import (
    ColumnMapping, ExtraField, ValueMap, ValueMapEntry,
    ROLE_FIELD, ROLE_CONTROL, ROLE_SKIP, ST_OK, ST_CHECK,
)


def test_column_mapping_defaults():
    m = ColumnMapping(col_index=3)
    assert m.role == ROLE_FIELD
    assert m.status == ST_CHECK
    assert m.source == ""
    assert m.field_api == ""
    assert m.instance == 1
    assert m.candidates == []


def test_value_map_apply_found():
    vm = ValueMap(entries=[ValueMapEntry("חברתי", "012A", "חברתי")])
    assert vm.apply("חברתי") == ("012A", True)


def test_value_map_apply_strips_input():
    vm = ValueMap(entries=[ValueMapEntry("חברתי", "012A")])
    assert vm.apply("  חברתי ") == ("012A", True)


def test_value_map_apply_not_found_with_default():
    vm = ValueMap(entries=[ValueMapEntry("א", "1")], default="0")
    assert vm.apply("ב") == ("0", False)


def test_value_map_apply_not_found_no_default():
    vm = ValueMap(entries=[ValueMapEntry("א", "1")])
    assert vm.apply("ב") == ("", False)


def test_extra_field():
    x = ExtraField(object_api="Contact", field_api="LeadSource", constant_value="Web")
    assert x.constant_value == "Web"


def test_schema_mapping_fields_default_empty():
    s = RuntimeSchema()
    assert s.mappings == {}
    assert s.value_maps == {}
    assert s.extra_fields == []
    assert s.multi_instance == {}


from config.runtime_schema import IdentityConfig, LookupConfig


def test_identity_config_defaults():
    cfg = IdentityConfig()
    assert cfg.mechanisms == []
    assert cfg.dedup_internal is False  # ברירת-מחדל כבוי — שום רשומה לא נעלמת


def test_identity_config_stores_ranked_mechanisms():
    cfg = IdentityConfig(mechanisms=[["ID_Number__c"], ["LastName", "Email"]])
    assert cfg.mechanisms[0] == ["ID_Number__c"]
    assert cfg.mechanisms[1] == ["LastName", "Email"]


def test_schema_identity_fields_default_empty():
    s = RuntimeSchema()
    assert s.identity == {}
    assert s.extra_objects == []


# ── Task 1: LookupConfig ──────────────────────────────────────────────────────

def test_lookup_config_defaults():
    lc = LookupConfig(
        source_object="Contact",
        source_col_index=3,
        target_object="Account",
        target_field="AccountId",
        identified_by=["Name"],
    )
    assert lc.source_object == "Contact"
    assert lc.source_col_index == 3
    assert lc.target_object == "Account"
    assert lc.target_field == "AccountId"
    assert lc.identified_by == ["Name"]


def test_runtime_schema_lookups_default_empty():
    schema = RuntimeSchema()
    assert schema.lookups == []


def test_runtime_schema_lookups_stored():
    lc = LookupConfig("Contact", 3, "Account", "AccountId", ["Name"])
    schema = RuntimeSchema()
    schema.lookups.append(lc)
    assert len(schema.lookups) == 1
    assert schema.lookups[0].target_field == "AccountId"


# ── Task 2: _load_order ───────────────────────────────────────────────────────

def _get_load_order_fn():
    """Import _load_order from main without triggering the full Streamlit app."""
    import importlib.util, sys
    spec = importlib.util.spec_from_file_location(
        "main",
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "main.py"),
    )
    mod = importlib.util.module_from_spec(spec)
    # Prevent Streamlit from running at import time
    sys.modules.setdefault("streamlit", __import__("unittest.mock", fromlist=["MagicMock"]).MagicMock())
    spec.loader.exec_module(mod)
    return mod._load_order


def test_load_order_no_lookups():
    schema = RuntimeSchema()
    schema.objects = [ObjectDef("Contact", "אנשי קשר"), ObjectDef("Campaign", "קמפיינים")]
    schema.lookups = []
    result = _get_load_order_fn()(schema)
    assert len(result) == 1
    assert set(result[0]) == {"Contact", "Campaign"}


def test_load_order_with_lookup():
    schema = RuntimeSchema()
    schema.objects = [ObjectDef("Contact", "אנשי קשר"), ObjectDef("Account", "חשבונות")]
    schema.extra_objects = []
    schema.lookups = [LookupConfig("Contact", 3, "Account", "AccountId", ["Name"])]
    result = _get_load_order_fn()(schema)
    assert result[0] == ["Account"]
    assert result[1] == ["Contact"]


def test_load_order_chain():
    schema = RuntimeSchema()
    schema.objects = [
        ObjectDef("Contact", "אנשי קשר"),
        ObjectDef("Account", "חשבונות"),
        ObjectDef("Opportunity", "הזדמנויות"),
    ]
    schema.extra_objects = []
    schema.lookups = [
        LookupConfig("Contact", 3, "Account", "AccountId", ["Name"]),
        LookupConfig("Opportunity", 5, "Account", "AccountId", ["Name"]),
    ]
    result = _get_load_order_fn()(schema)
    assert result[0] == ["Account"]
    assert set(result[1]) == {"Contact", "Opportunity"}


# ── Task 1: JunctionConfig ───────────────────────────────────────────────────

from config.runtime_schema import JunctionConfig, RuntimeSchema


def test_junction_config_defaults():
    jc = JunctionConfig(
        object_a="Contact",
        block_a="איש קשר",
        object_b="Campaign",
        block_b="פרטי האירוע",
        junction_object="CampaignMember",
        id_field_a="ContactId",
        id_field_b="CampaignId",
    )
    assert jc.control_col_index is None
    assert jc.field_mappings == []
    assert jc.symmetric is False


def test_runtime_schema_junctions_field():
    schema = RuntimeSchema()
    assert schema.junctions == []
    jc = JunctionConfig(
        object_a="Contact", block_a="A", object_b="Contact", block_b="B",
        junction_object="npe4__Relationship__c",
        id_field_a="npe4__Contact__c", id_field_b="npe4__RelatedContact__c",
        symmetric=True,
    )
    schema.junctions.append(jc)
    assert len(schema.junctions) == 1
    assert schema.junctions[0].symmetric is True
