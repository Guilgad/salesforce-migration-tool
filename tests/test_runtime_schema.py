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
