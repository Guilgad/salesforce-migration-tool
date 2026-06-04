"""בדיקות validator — validate_mapping, validate_dates, validate_ids, build_issues_grid."""
from modules import mapper, validator
from modules.field_dictionary import FieldInfo, ObjectInfo

DATA_START = 4  # 4 שורות-כותרת ואז דאטה (כמו TEMPLATE_DATA_START_ROW)


# ===== עוזרי-בדיקה =====

def _col(index, status, *, label="עמודה", object_api="Contact", clean_api="Field__c"):
    return mapper.TemplateColumn(
        index=index, block="פרטי איש הקשר ראשי", label=label,
        proposed_api=clean_api, object_api=object_api,
        clean_api=clean_api, status=status,
    )

def _dict(object_api="Contact", fields=None):
    fields = fields or [FieldInfo(label="תאריך לידה", api="Birthdate", datatype="Date")]
    return {object_api: ObjectInfo(api=object_api, label=object_api, fields=fields)}

def _rows(*data_rows):
    """4 שורות-כותרת ריקות ואז שורות-דאטה."""
    return [[] for _ in range(DATA_START)] + list(data_rows)


# ===== validate_mapping =====

def test_invalid_api_is_error():
    issues = validator.validate_mapping([_col(2, mapper.STATUS_INVALID)])
    assert len(issues) == 1
    assert issues[0].severity == validator.SEVERITY_ERROR
    assert issues[0].kind == validator.KIND_INVALID_API
    assert issues[0].location == "C"  # index 2 → C

def test_missing_is_warning():
    issues = validator.validate_mapping([_col(0, mapper.STATUS_MISSING)])
    assert issues[0].severity == validator.SEVERITY_WARNING
    assert issues[0].kind == validator.KIND_UNMAPPED

def test_no_dict_is_warning():
    issues = validator.validate_mapping([_col(0, mapper.STATUS_NO_DICT)])
    assert issues[0].kind == validator.KIND_NO_DICT

def test_valid_ignore_control_produce_no_issues():
    cols = [
        _col(0, mapper.STATUS_VALID),
        _col(1, mapper.STATUS_IGNORE),
        _col(2, mapper.STATUS_CONTROL),
    ]
    assert validator.validate_mapping(cols) == []


# ===== validate_dates =====

def test_valid_date_cell_no_issue():
    cols = [_col(0, mapper.STATUS_VALID, clean_api="Birthdate")]
    rows = _rows(["04.06.2026"])
    assert validator.validate_dates(cols, rows, _dict(), data_start_row=DATA_START) == []

def test_bad_date_cell_flagged():
    cols = [_col(0, mapper.STATUS_VALID, clean_api="Birthdate")]
    rows = _rows(["לא-תאריך"])
    issues = validator.validate_dates(cols, rows, _dict(), data_start_row=DATA_START)
    assert len(issues) == 1
    assert issues[0].kind == validator.KIND_BAD_DATE
    assert issues[0].severity == validator.SEVERITY_ERROR
    assert issues[0].location == "A5"  # עמודה A, שורת-גיליון 5 (index 4 + 1)

def test_empty_date_cell_no_issue():
    cols = [_col(0, mapper.STATUS_VALID, clean_api="Birthdate")]
    rows = _rows([""])
    assert validator.validate_dates(cols, rows, _dict(), data_start_row=DATA_START) == []

def test_non_date_column_skipped():
    # שדה Text — גם ערך-זבל לא נבדק כתאריך
    fields = [FieldInfo(label="שם", api="LastName", datatype="Text(80)")]
    cols = [_col(0, mapper.STATUS_VALID, clean_api="LastName")]
    rows = _rows(["לא-תאריך"])
    assert validator.validate_dates(cols, rows, _dict(fields=fields), data_start_row=DATA_START) == []

def test_datetime_column_detected():
    fields = [FieldInfo(label="נוצר", api="CreatedDate", datatype="Date/Time")]
    cols = [_col(0, mapper.STATUS_VALID, clean_api="CreatedDate")]
    rows = _rows(["זבל"])
    issues = validator.validate_dates(cols, rows, _dict(fields=fields), data_start_row=DATA_START)
    assert len(issues) == 1 and issues[0].kind == validator.KIND_BAD_DATE


# ===== validate_ids =====

def test_id_18_no_issue():
    db = {"Contact": [{"Id": "003000000000000AAA"}]}  # 18 תווים
    assert validator.validate_ids(db) == []

def test_id_15_flagged():
    db = {"Contact": [{"Id": "003000000000000"}]}  # 15 תווים
    issues = validator.validate_ids(db)
    assert len(issues) == 1
    assert issues[0].kind == validator.KIND_BAD_ID
    assert issues[0].severity == validator.SEVERITY_WARNING

def test_empty_id_no_issue():
    db = {"Contact": [{"Id": ""}, {"Id": None}, {}]}
    assert validator.validate_ids(db) == []


# ===== validate_output_grid (בדיקת גריד-פלט מוכן-לטעינה) =====

def _grid(*data_rows, he=None, api=None):
    """גריד-פלט: 2 שורות-כותרת (עברית מעל API) ואז דאטה."""
    he = he or ["מפתח פנימי", "נמצא לפי", "מזהה", "תאריך לידה"]
    api = api or ["local_key", "", "Id", "Birthdate"]
    return [he, api] + list(data_rows)


def test_output_grid_bad_date_flagged_with_mark():
    grid = _grid(["C1", "", "", "לא-תאריך"])
    issues, marks = validator.validate_output_grid(grid, "Contact", _dict())
    assert len(issues) == 1 and issues[0].kind == validator.KIND_BAD_DATE
    assert issues[0].location == "D3"          # עמודה D (אינדקס 3), שורה 3 (אינדקס 2)
    assert marks == [(2, 3, issues[0].message)]  # (row0, col0, message) לצביעה+הערה


def test_output_grid_valid_date_no_issue():
    grid = _grid(["C1", "", "", "04.06.2026"])
    issues, marks = validator.validate_output_grid(grid, "Contact", _dict())
    assert issues == [] and marks == []


def test_output_grid_bad_id_length_flagged():
    grid = _grid(["C1", "", "003000000000000", "04.06.2026"])  # Id 15 תווים
    issues, marks = validator.validate_output_grid(grid, "Contact", _dict())
    assert len(issues) == 1 and issues[0].kind == validator.KIND_BAD_ID
    assert issues[0].severity == validator.SEVERITY_WARNING
    assert marks == [(2, 2, issues[0].message)]  # עמודת Id (אינדקס 2)


def test_output_grid_good_id_18_no_issue():
    grid = _grid(["C1", "", "003000000000000AAA", ""])  # Id 18 תווים
    issues, _ = validator.validate_output_grid(grid, "Contact", _dict())
    assert issues == []


def test_output_grid_headers_only_no_issues():
    issues, marks = validator.validate_output_grid(_grid(), "Contact", _dict())
    assert issues == [] and marks == []


def test_output_grid_object_not_in_dict_only_id_checked():
    # אובייקט שאינו במילון → אין בדיקת-תאריכים, אך אורך-Id עדיין נבדק
    grid = _grid(["C1", "", "123", "זבל"])
    issues, _ = validator.validate_output_grid(grid, "UnknownObj", _dict())
    kinds = {i.kind for i in issues}
    assert kinds == {validator.KIND_BAD_ID}  # התאריך לא נבדק (אין סוג-שדה)


# ===== build_issues_grid =====

def test_grid_two_headers_and_row_per_issue():
    issues = [
        validator.Issue("invalid_api", validator.SEVERITY_ERROR, "ל", "C", "msg1"),
        validator.Issue("unmapped", validator.SEVERITY_WARNING, "ל", "D", "msg2"),
    ]
    grid, colors = validator.build_issues_grid(issues)
    assert len(grid) == 4  # 2 כותרות + 2 בעיות
    assert grid[0] == ["סוג", "חומרה", "עמודה", "מיקום", "הסבר"]

def test_grid_error_row_colored():
    issues = [validator.Issue("bad_date", validator.SEVERITY_ERROR, "ל", "A5", "msg")]
    _, colors = validator.build_issues_grid(issues)
    assert colors == [(2, 0, "red")]  # שורת-נתון ראשונה (index 2), עמודה 0

def test_grid_warning_not_colored():
    issues = [validator.Issue("unmapped", validator.SEVERITY_WARNING, "ל", "D", "msg")]
    _, colors = validator.build_issues_grid(issues)
    assert colors == []

def test_empty_issues_only_headers():
    grid, colors = validator.build_issues_grid([])
    assert len(grid) == 2 and colors == []
