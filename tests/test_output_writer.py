"""בדיקות output_writer — backfill, קונסולידציה, תא "נמצא לפי", טיפול ידני, אידמפוטנטיות."""
from modules import dedup_engine, mapper, output_writer

MECHS = [["ID_Number__c"], ["FirstName", "LastName"]]


def _col(index, clean_api, label):
    return mapper.TemplateColumn(
        index=index, block="ראשי", label=label, proposed_api=clean_api,
        object_api="Contact", clean_api=clean_api, status=mapper.STATUS_VALID,
    )


# סדר עמודות-השדה הנטענות (כפי שייכתבו לגריד)
COLUMNS = [
    _col(1, "ID_Number__c", "תעודת זהות"),
    _col(2, "FirstName", "שם פרטי"),
    _col(3, "LastName", "שם משפחה"),
    _col(4, "Email", "אימייל"),
]
FIELDS = ["ID_Number__c", "FirstName", "LastName", "Email"]


def _data_rows(grid):
    """שורות-הנתונים בלבד (אחרי 2 שורות-הכותרת)."""
    return grid[2:]


# ===== backfill + קונסולידציה =====

def test_backfill_fills_empty_fields_template_wins():
    """Upsert: שדה ריק מתמלא מה-DB; ערך-טמפלייט קיים גובר ולא נדרס."""
    records = [{"ID_Number__c": "1", "FirstName": "חדש", "LastName": "", "Email": ""}]
    db = [{"Id": "a", "ID_Number__c": "1", "FirstName": "ישן", "LastName": "כהן", "Email": "old@x"}]
    res = dedup_engine.deduplicate(records, MECHS, db)
    db_by_id = {"a": db[0]}
    grid, colors = output_writer.build_contacts_grid(res, records, COLUMNS, db_by_id)

    row = _data_rows(grid)[0]
    # [local_key, נמצא-לפי, Id, ID, FirstName, LastName, Email]
    assert row == ["C1", "1", "a", "1", "חדש", "כהן", "old@x"]
    assert colors == [(2, 1, "green")]  # תא "נמצא לפי" בשורה 0 → 🟢 (מנגנון 1)


def test_no_backfill_for_insert():
    """Insert: שדות ריקים נשארים ריקים (אין מקור ב-DB למלא מהם)."""
    records = [{"ID_Number__c": "9", "FirstName": "דנה", "LastName": "", "Email": ""}]
    res = dedup_engine.deduplicate(records, MECHS, [])
    grid, colors = output_writer.build_contacts_grid(res, records, COLUMNS, {})
    row = _data_rows(grid)[0]
    assert row == ["C1", "", "", "9", "דנה", "", ""]  # Id ריק, אין צבע
    assert colors == []


def test_consolidate_first_non_empty_across_members():
    """מיזוג רשומות-חבר: ראשון-לא-ריק פר-שדה."""
    records = [
        {"ID_Number__c": "1", "FirstName": "דנה", "LastName": ""},
        {"ID_Number__c": "1", "FirstName": "", "LastName": "כהן", "Email": "d@x"},
    ]
    res = dedup_engine.deduplicate(records, MECHS, [])  # מתמזגים לאדם אחד לפי ת"ז
    grid, _ = output_writer.build_contacts_grid(res, records, COLUMNS, {})
    row = _data_rows(grid)[0]
    assert row == ["C1", "", "", "1", "דנה", "כהן", "d@x"]


# ===== תא "נמצא לפי": צבעים =====

def test_found_by_mechanism_2_is_yellow():
    """התאמה לפי מנגנון 2 → תא "2" בצבע 🟡."""
    records = [{"ID_Number__c": "999", "FirstName": "דנה", "LastName": "כהן"}]
    db = [{"Id": "b", "ID_Number__c": "111", "FirstName": "דנה", "LastName": "כהן"}]
    res = dedup_engine.deduplicate(records, MECHS, db)
    grid, colors = output_writer.build_contacts_grid(res, records, COLUMNS, {"b": db[0]})
    assert _data_rows(grid)[0][1] == "2"
    assert colors == [(2, 1, "yellow")]


def test_combined_mechanisms_cell_is_orange():
    """הכרעה-בשילוב → תא "שילוב 1+2" בצבע 🟠."""
    records = [{"ID_Number__c": "1", "FirstName": "דנה", "LastName": "כהן"}]
    db = [
        {"Id": "x", "ID_Number__c": "1", "FirstName": "דנה", "LastName": "כהן"},
        {"Id": "y", "ID_Number__c": "1", "FirstName": "בני", "LastName": "לוי"},
    ]
    res = dedup_engine.deduplicate(records, MECHS, db)
    db_by_id = {"x": db[0], "y": db[1]}
    grid, colors = output_writer.build_contacts_grid(res, records, COLUMNS, db_by_id)
    assert _data_rows(grid)[0][1] == "שילוב 1+2"
    assert colors == [(2, 1, "orange")]


# ===== טיפול ידני =====

def _ambiguous_setup():
    """אדם דו-משמעי בודד: ת"ז 1 מתאימה לשני Id ב-DB, בלי שם לצמצום."""
    records = [{"ID_Number__c": "1"}]
    db = [{"Id": "x", "ID_Number__c": "1"}, {"Id": "y", "ID_Number__c": "1"}]
    res = dedup_engine.deduplicate(records, MECHS, db)
    db_by_id = {"x": db[0], "y": db[1]}
    return records, db, res, db_by_id


def test_ambiguous_excluded_from_main_grid():
    """רשומה דו-משמעית לא נכנסת לגריד הראשי (רק שורות-הכותרת)."""
    records, db, res, db_by_id = _ambiguous_setup()
    grid, _ = output_writer.build_contacts_grid(res, records, COLUMNS, db_by_id)
    assert len(_data_rows(grid)) == 0


def test_manual_grid_has_source_and_candidate_rows():
    """גריד הטיפול-הידני: שורת-מקור + שורת-מועמד לכל match_id; שורת-מקור 1-based."""
    records, db, res, db_by_id = _ambiguous_setup()
    manual = output_writer.build_manual_grid(res, records, COLUMNS, db_by_id, source_rows=[4])
    # כותרת + שורת-מקור + 2 מועמדים
    assert len(manual) == 1 + 1 + 2
    source_row = manual[1]
    assert source_row[2] == "5"   # source_row 4 (0-based) → מוצג 5
    types = [r[4] for r in manual[1:]]  # עמודת "סוג"
    assert types == ["מקור", "מאגר", "מאגר"]


def test_parse_manual_choices_reads_checkmark():
    """סימון ✓ בשורת-מאגר → בחירת ה-Id לאותו מפתח פנימי."""
    records, db, res, db_by_id = _ambiguous_setup()
    manual = output_writer.build_manual_grid(res, records, COLUMNS, db_by_id, source_rows=[4])
    # סימון המועמד הראשון (שורה 2 בגריד = מועמד "x")
    manual[2][3] = "✓"  # עמודת "בחר"
    choices, warnings = output_writer.parse_manual_choices(manual)
    assert choices == {"C1": "x"}
    assert warnings == []


def test_parse_manual_choices_multiple_marks_warns_takes_first():
    """ריבוי-סימונים לאותו מפתח → אזהרה, נלקח הראשון."""
    records, db, res, db_by_id = _ambiguous_setup()
    manual = output_writer.build_manual_grid(res, records, COLUMNS, db_by_id, source_rows=[4])
    manual[2][3] = "✓"
    manual[3][3] = "✓"
    choices, warnings = output_writer.parse_manual_choices(manual)
    assert choices == {"C1": "x"}
    assert len(warnings) == 1


def test_manual_choice_becomes_upsert_in_main_grid():
    """בחירה ידנית → האדם הדו-משמעי נכנס לגריד כ-Upsert עם ה-Id הנבחר, תווית "נבחר ידנית"."""
    records, db, res, db_by_id = _ambiguous_setup()
    grid, colors = output_writer.build_contacts_grid(
        res, records, COLUMNS, db_by_id, manual_choices={"C1": "y"}
    )
    row = _data_rows(grid)[0]
    assert row[0] == "C1" and row[1] == "נבחר ידנית" and row[2] == "y"
    assert colors == [(2, 1, "orange")]


def test_idempotency_marked_choice_preserved_in_manual_grid():
    """אידמפוטנטיות: בנייה-חוזרת עם marked משמרת את ה-✓ בשורת-המועמד הנבחר."""
    records, db, res, db_by_id = _ambiguous_setup()
    manual2 = output_writer.build_manual_grid(
        res, records, COLUMNS, db_by_id, source_rows=[4], marked={"C1": "y"}
    )
    # שורת המועמד "y" צריכה לשאת ✓ בעמודת "בחר"
    y_row = next(r for r in manual2[1:] if r[5] == "y")  # עמודת "מזהה"
    assert y_row[3] == "✓"
    x_row = next(r for r in manual2[1:] if r[5] == "x")
    assert x_row[3] == ""
