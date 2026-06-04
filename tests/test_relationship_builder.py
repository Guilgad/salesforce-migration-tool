"""בדיקות relationship_builder — גזירה, סינון, contact_id_map, db_pairs, גריד."""
from modules import dedup_engine, mapper, splitter, relationship_builder
from config.template_config import (
    CONTACT_BLOCK_PRIMARY, CONTACT_BLOCK_SECONDARY, RELATIONSHIP_OBJECT,
    TEMPLATE_DATA_START_ROW,
)

# ===== עוזרי-בדיקה =====

def _sr(source_row, block, values=None):
    return splitter.SplitRecord(
        object_api="Contact", block=block, source_row=source_row,
        values=values or {},
    )


def _person(local_key, indices):
    return dedup_engine.PersonResult(
        local_key=local_key, record_indices=indices,
        action="Insert", sf_id=None, found_by=None,
        ambiguous=False, unkeyed=False,
    )


def _dedup(*persons):
    return dedup_engine.DedupResult(persons=list(persons), counts={})


def _type_col(index=5):
    return mapper.TemplateColumn(
        index=index, block=CONTACT_BLOCK_PRIMARY, label="סוג הקשר",
        proposed_api="npe4__Type__c", object_api=RELATIONSHIP_OBJECT,
        clean_api="npe4__Type__c", status=mapper.STATUS_VALID,
    )


# שורות-טמפלייט: 4 שורות-כותרת + שורת-דאטה אחת (סוג הקשר בעמודה 5)
def _tmpl(type_val="חבר", extra_rows=0):
    header_rows = [[] for _ in range(TEMPLATE_DATA_START_ROW)]
    data_row = [""] * 6
    if type_val:
        data_row[5] = type_val
    rows = header_rows + [data_row]
    rows += [[] for _ in range(extra_rows)]
    return rows


def _derive(
    split_records=None,
    dedup_result=None,
    contact_id_map=None,
    db_rel_pairs=None,
    tmpl_rows=None,
    columns=None,
):
    """קיצור לקריאת derive_relationships עם ברירות-מחדל נוחות."""
    if split_records is None:
        split_records = [
            _sr(TEMPLATE_DATA_START_ROW, CONTACT_BLOCK_PRIMARY, {"FirstName": "דן", "LastName": "לוי"}),
            _sr(TEMPLATE_DATA_START_ROW, CONTACT_BLOCK_SECONDARY, {"FirstName": "ענת", "LastName": "לוי"}),
        ]
    if dedup_result is None:
        dedup_result = _dedup(_person("C1", [0]), _person("C2", [1]))
    if contact_id_map is None:
        contact_id_map = {"C1": "a001", "C2": "a002"}
    if db_rel_pairs is None:
        db_rel_pairs = set()
    if tmpl_rows is None:
        tmpl_rows = _tmpl()
    if columns is None:
        columns = [_type_col()]

    return relationship_builder.derive_relationships(
        tmpl_rows, columns, split_records, dedup_result,
        contact_id_map, db_rel_pairs,
        data_start_row=TEMPLATE_DATA_START_ROW,
        block_primary=CONTACT_BLOCK_PRIMARY,
        block_secondary=CONTACT_BLOCK_SECONDARY,
        relationship_object=RELATIONSHIP_OBJECT,
    )


# ===== derive_relationships =====

def test_basic_derivation_produces_one_record():
    """שורה עם שני אנשי-קשר → RelRecord אחד עם הנתונים הנכונים."""
    recs = _derive()
    assert len(recs) == 1
    r = recs[0]
    assert r.source_row == TEMPLATE_DATA_START_ROW
    assert r.local_key_a == "C1" and r.local_key_b == "C2"
    assert r.sf_id_a == "a001" and r.sf_id_b == "a002"
    assert r.type_val == "חבר"
    assert r.name_a == "דן לוי" and r.name_b == "ענת לוי"
    assert r.warning is None and r.exists_in_db is False


def test_row_without_secondary_is_skipped():
    """שורה עם ראשי בלבד (ללא 'נוסף') → לא נגזר קשר."""
    split_records = [_sr(TEMPLATE_DATA_START_ROW, CONTACT_BLOCK_PRIMARY)]
    dedup_result = _dedup(_person("C1", [0]))
    recs = _derive(split_records=split_records, dedup_result=dedup_result,
                   contact_id_map={"C1": "a001"})
    assert recs == []


def test_pair_is_symmetric_a_b_equals_b_a():
    """זוג (A,B) = (B,A) — exists_in_db נכון גם כש-DB שמר בסדר הפוך."""
    db_rel_pairs = {("a001", "a002")}  # ממוין: a001 < a002
    recs = _derive(db_rel_pairs=db_rel_pairs)
    assert recs[0].exists_in_db is True


def test_pair_reversed_in_db_still_recognized():
    """DB שמר את הצמד בכיוון B→A — עדיין מזוהה כקיים (ממיון)."""
    # a002 > a001 → sorted pair = ("a001","a002")
    db_rel_pairs = {(min("a002", "a001"), max("a002", "a001"))}
    recs = _derive(db_rel_pairs=db_rel_pairs)
    assert recs[0].exists_in_db is True


def test_missing_sf_id_produces_warning():
    """Id חסר לאחד מאנשי-הקשר → warning לא-None."""
    recs = _derive(contact_id_map={"C1": "a001"})  # C2 חסר
    assert recs[0].warning is not None
    assert recs[0].sf_id_b == ""


def test_no_type_column_gives_empty_type():
    """אין עמודת-סוג ב-columns → type_val ריק, אין קריסה."""
    recs = _derive(columns=[])
    assert recs[0].type_val == ""


def test_name_falls_back_to_local_key_when_no_name():
    """ערכי-הרשומה ריקים (אין שם) → name = local_key."""
    split_records = [
        _sr(TEMPLATE_DATA_START_ROW, CONTACT_BLOCK_PRIMARY, {}),
        _sr(TEMPLATE_DATA_START_ROW, CONTACT_BLOCK_SECONDARY, {}),
    ]
    recs = _derive(split_records=split_records)
    assert recs[0].name_a == "C1"
    assert recs[0].name_b == "C2"


# ===== build_relationship_grid =====

def _grid(recs):
    return relationship_builder.build_relationship_grid(recs)


def test_grid_has_two_header_rows_and_one_data_row():
    """גריד בסיסי: 2 שורות-כותרת + שורת-נתונים לקשר תקין."""
    recs = _derive()
    grid, _ = _grid(recs)
    assert len(grid) == 3  # 2 כותרות + 1 נתון


def test_grid_skips_existing_in_db():
    """קשר שכבר ב-DB לא נכנס לגריד."""
    recs = _derive(db_rel_pairs={("a001", "a002")})
    grid, _ = _grid(recs)
    assert len(grid) == 2  # רק כותרות


def test_grid_skips_missing_id():
    """קשר עם Id חסר לא נכנס לגריד."""
    recs = _derive(contact_id_map={"C1": "a001"})
    grid, _ = _grid(recs)
    assert len(grid) == 2  # רק כותרות


def test_grid_data_row_contains_correct_ids_and_type():
    """תוכן שורת-הנתונים: sf_id_a, sf_id_b, type_val."""
    recs = _derive()
    grid, _ = _grid(recs)
    row = grid[2]  # שורת-נתונים ראשונה (אחרי 2 כותרות)
    assert row[2] == "a001"   # npe4__Contact__c
    assert row[3] == "a002"   # npe4__RelatedContact__c
    assert row[4] == "חבר"    # npe4__Type__c


def test_grid_display_columns_have_red_color():
    """עמודות-תצוגה (שמות) מקבלות צבע אדום-בהיר."""
    recs = _derive()
    _, colors = _grid(recs)
    colored_cols = {c for _, c, _ in colors}
    assert 0 in colored_cols and 1 in colored_cols
    assert all(color == "red" for _, _, color in colors)


# ===== contact_id_map_from_grid =====

def test_contact_id_map_reads_2header_grid():
    """קריאת לשונית פלט-Contacts: local_key בעמודה 0, Id בעמודה 2."""
    grid_rows = [
        ["מפתח פנימי", "נמצא לפי", "מזהה", "שם"],   # כותרת עברית
        ["local_key", "", "Id", "Name"],               # כותרת API
        ["C1", "1", "a001", "דן"],
        ["C2", "", "a002", "ענת"],
    ]
    result = relationship_builder.contact_id_map_from_grid(grid_rows)
    assert result == {"C1": "a001", "C2": "a002"}


def test_contact_id_map_skips_empty_id():
    """שורה עם Id ריק (Contacts שטרם נטענו) לא נכנסת למפה."""
    grid_rows = [
        ["מפתח פנימי", "נמצא לפי", "מזהה"],
        ["local_key", "", "Id"],
        ["C1", "", "a001"],
        ["C2", "", ""],   # Id ריק
    ]
    result = relationship_builder.contact_id_map_from_grid(grid_rows)
    assert result == {"C1": "a001"}
    assert "C2" not in result


# ===== db_rel_pairs_from_records =====

def test_db_rel_pairs_builds_sorted_pairs():
    """זוגות מ-DB: ממוינים, שני כיוונים = זוג אחד."""
    db = [
        {"npe4__Contact__c": "b002", "npe4__RelatedContact__c": "a001"},
        {"npe4__Contact__c": "a001", "npe4__RelatedContact__c": "b002"},  # כיוון הפוך
    ]
    pairs = relationship_builder.db_rel_pairs_from_records(db)
    assert pairs == {("a001", "b002")}


def test_db_rel_pairs_skips_incomplete_records():
    """רשומות עם שדה ריק מושמטות."""
    db = [{"npe4__Contact__c": "a001", "npe4__RelatedContact__c": ""}]
    pairs = relationship_builder.db_rel_pairs_from_records(db)
    assert pairs == set()
