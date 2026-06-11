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


from config.runtime_schema import IdentityConfig


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
