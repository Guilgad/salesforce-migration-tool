"""בדיקות Campaigns — dedup לפי שם, Insert/Upsert, backfill, טיפול ידני, local_key "K"."""
from modules import dedup_engine, mapper, output_writer

MECHS = [["Name"]]  # מנגנון יחיד לפי שם (כמו template_config.CAMPAIGN_MECHANISMS)


def _col(index, clean_api, label):
    return mapper.TemplateColumn(
        index=index, block="פרטי האירוע", label=label, proposed_api=clean_api,
        object_api="Campaign", clean_api=clean_api, status=mapper.STATUS_VALID,
    )


COLUMNS = [
    _col(1, "Name", "שם האירוע"),
    _col(2, "StartDate", "תאריך התחלה"),
    _col(3, "Status", "סטטוס"),
]
FIELDS = ["Name", "StartDate", "Status"]


def _grid(res, records, db_by_id, **kw):
    return output_writer.build_campaigns_grid(
        res, records, COLUMNS, db_by_id, object_api="Campaign", **kw
    )


def _data_rows(grid):
    """שורות-הנתונים בלבד (אחרי 2 שורות-הכותרת)."""
    return grid[2:]


# ===== dedup לפי שם =====

def test_same_name_collapses_to_one_campaign():
    """שתי שורות עם אותו שם → קמפיין אחד, local_key "K1"."""
    records = [
        {"Name": "מחנה פסח", "StartDate": "2026-04-01"},
        {"Name": "מחנה פסח", "StartDate": "2026-04-01"},
    ]
    res = dedup_engine.deduplicate(records, MECHS, [], local_key_prefix="K")
    assert len(res.persons) == 1
    assert res.persons[0].local_key == "K1"
    assert res.counts["inserts"] == 1


def test_name_normalization_groups_despite_spaces_and_case():
    """רווחים מובילים/עוקבים/כפולים + אותיות שונות → אותו קמפיין."""
    records = [
        {"Name": "Pesach Camp"},
        {"Name": "  pesach   camp  "},
    ]
    res = dedup_engine.deduplicate(records, MECHS, [], local_key_prefix="K")
    assert len(res.persons) == 1


def test_different_names_stay_separate():
    """שמות שונים → קמפיינים נפרדים, local_key רץ K1/K2."""
    records = [{"Name": "מחנה פסח"}, {"Name": "מחנה קיץ"}]
    res = dedup_engine.deduplicate(records, MECHS, [], local_key_prefix="K")
    assert [p.local_key for p in res.persons] == ["K1", "K2"]
    assert res.counts["inserts"] == 2


# ===== Insert / Upsert מול DB =====

def test_upsert_when_name_matches_db():
    """שם שקיים ב-DB → Upsert עם ה-Id, תא "נמצא לפי" = "קיים" 🟢."""
    records = [{"Name": "מחנה פסח", "Status": "מתוכנן"}]
    db = [{"Id": "c1", "Name": "מחנה פסח", "Status": "פעיל"}]
    res = dedup_engine.deduplicate(records, MECHS, db, local_key_prefix="K")
    grid, colors = _grid(res, records, {"c1": db[0]})
    row = _data_rows(grid)[0]
    # [local_key, נמצא-לפי, Id, Name, StartDate, Status]
    assert row[0] == "K1" and row[1] == "קיים" and row[2] == "c1"
    assert colors == [(2, 1, "green")]
    assert res.counts["upserts"] == 1


def test_insert_when_no_db_match():
    """שם שאינו ב-DB → Insert, Id ריק, תא "נמצא לפי" ריק וללא צבע."""
    records = [{"Name": "מחנה חדש"}]
    res = dedup_engine.deduplicate(records, MECHS, [], local_key_prefix="K")
    grid, colors = _grid(res, records, {})
    row = _data_rows(grid)[0]
    assert row[1] == "" and row[2] == ""
    assert colors == []


def test_backfill_fills_empty_from_db_template_wins():
    """Upsert: שדה ריק מתמלא מה-DB; ערך-טמפלייט קיים גובר ולא נדרס."""
    records = [{"Name": "מחנה פסח", "StartDate": "", "Status": "מתוכנן"}]
    db = [{"Id": "c1", "Name": "מחנה פסח", "StartDate": "2026-04-01", "Status": "ישן"}]
    res = dedup_engine.deduplicate(records, MECHS, db, local_key_prefix="K")
    grid, _ = _grid(res, records, {"c1": db[0]})
    row = _data_rows(grid)[0]
    # Name, StartDate(מה-DB), Status(טמפלייט גובר)
    assert row[3:] == ["מחנה פסח", "2026-04-01", "מתוכנן"]


# ===== טיפול ידני: ambiguous / unkeyed =====

def test_ambiguous_two_db_same_name_excluded_and_manual():
    """שני קמפייני-DB עם אותו שם → מוחרג מהגריד הראשי, מופיע בטיפול-ידני."""
    records = [{"Name": "מחנה פסח"}]
    db = [{"Id": "x", "Name": "מחנה פסח"}, {"Id": "y", "Name": "מחנה פסח"}]
    res = dedup_engine.deduplicate(records, MECHS, db, local_key_prefix="K")
    db_by_id = {"x": db[0], "y": db[1]}
    grid, _ = _grid(res, records, db_by_id)
    assert len(_data_rows(grid)) == 0  # מוחרג מהטעינה
    assert res.counts["ambiguous"] == 1

    manual, _ = output_writer.build_manual_grid(
        res, records, COLUMNS, db_by_id, source_rows=[4], object_api="Campaign"
    )
    # כותרת + שורת-מקור + 2 מועמדים
    assert len(manual) == 1 + 1 + 2
    assert [r[4] for r in manual[1:]] == ["מקור", "מאגר", "מאגר"]


def test_unkeyed_empty_name_excluded_and_manual():
    """שם ריק (אך יש שדה אחר) → unkeyed: מוחרג + טיפול-ידני."""
    records = [{"Name": "", "Status": "מתוכנן"}]
    res = dedup_engine.deduplicate(records, MECHS, [], local_key_prefix="K")
    grid, _ = _grid(res, records, {})
    assert len(_data_rows(grid)) == 0
    assert res.counts["unkeyed"] == 1
    manual, _ = output_writer.build_manual_grid(
        res, records, COLUMNS, {}, source_rows=[4], object_api="Campaign"
    )
    assert len(manual) == 1 + 1  # כותרת + שורת-מקור בלבד (אין מועמדי-DB)


def test_manual_choice_becomes_upsert():
    """בחירה ידנית של מועמד → Upsert עם ה-Id הנבחר, תווית "נבחר ידנית" 🟠."""
    records = [{"Name": "מחנה פסח"}]
    db = [{"Id": "x", "Name": "מחנה פסח"}, {"Id": "y", "Name": "מחנה פסח"}]
    res = dedup_engine.deduplicate(records, MECHS, db, local_key_prefix="K")
    db_by_id = {"x": db[0], "y": db[1]}
    grid, colors = _grid(res, records, db_by_id, manual_choices={"K1": "y"})
    row = _data_rows(grid)[0]
    assert row[0] == "K1" and row[1] == "נבחר ידנית" and row[2] == "y"
    assert colors == [(2, 1, "orange")]
