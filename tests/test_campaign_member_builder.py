"""בדיקות campaign_member_builder — _is_participating, גזירה, גריד."""
from modules import dedup_engine, mapper, splitter, campaign_member_builder
from config.template_config import (
    CONTACT_BLOCK_PRIMARY, CONTACT_BLOCK_SECONDARY,
    CM_OBJECT, CM_PARTICIPATING_LABEL, TEMPLATE_DATA_START_ROW,
)

CAMPAIGN_BLOCK = "פרטי האירוע"

# ===== עוזרי-בדיקה =====

def _sr_contact(source_row, block, values=None):
    return splitter.SplitRecord("Contact", block, source_row, values=values or {})

def _sr_campaign(source_row):
    return splitter.SplitRecord("Campaign", CAMPAIGN_BLOCK, source_row, values={"Name": "מחנה פסח"})

def _person(local_key, indices):
    return dedup_engine.PersonResult(
        local_key=local_key, record_indices=indices,
        action="Insert", sf_id=None, found_by=None,
        ambiguous=False, unkeyed=False,
    )

def _dedup(*persons):
    return dedup_engine.DedupResult(persons=list(persons), counts={})

def _ctrl_col(block, index=5):
    """עמודת-בקרה STATUS_CONTROL ("משתתף באירוע") לבלוק נתון."""
    return mapper.TemplateColumn(
        index=index, block=block, label=CM_PARTICIPATING_LABEL,
        proposed_api="", object_api=CM_OBJECT,
        clean_api="", status=mapper.STATUS_CONTROL,
    )

def _field_col(block, clean_api="Status", label="סטטוס", index=6):
    return mapper.TemplateColumn(
        index=index, block=block, label=label,
        proposed_api=clean_api, object_api=CM_OBJECT,
        clean_api=clean_api, status=mapper.STATUS_VALID,
    )

# שורות טמפלייט: 4 שורות-כותרת + שורת-דאטה (בקרה בעמודה 5, Status בעמודה 6)
def _tmpl(ctrl_val="TRUE", status_val="Sent"):
    header_rows = [[] for _ in range(TEMPLATE_DATA_START_ROW)]
    row = [""] * 7
    row[5] = ctrl_val
    row[6] = status_val
    return header_rows + [row]

def _derive(
    contact_split=None,
    contact_dedup=None,
    campaign_split=None,
    campaign_dedup=None,
    contact_id_map=None,
    campaign_id_map=None,
    tmpl_rows=None,
    columns=None,
):
    R = TEMPLATE_DATA_START_ROW
    if contact_split is None:
        contact_split = [
            _sr_contact(R, CONTACT_BLOCK_PRIMARY, {"FirstName": "דן", "LastName": "לוי"}),
        ]
    if contact_dedup is None:
        contact_dedup = _dedup(_person("C1", [0]))
    if campaign_split is None:
        campaign_split = [_sr_campaign(R)]
    if campaign_dedup is None:
        campaign_dedup = _dedup(_person("K1", [0]))
    if contact_id_map is None:
        contact_id_map = {"C1": "ctc001"}
    if campaign_id_map is None:
        campaign_id_map = {"K1": "camp001"}
    if tmpl_rows is None:
        tmpl_rows = _tmpl()
    if columns is None:
        columns = [_ctrl_col(CONTACT_BLOCK_PRIMARY), _field_col(CONTACT_BLOCK_PRIMARY)]

    return campaign_member_builder.derive_campaign_members(
        tmpl_rows, columns, contact_split, contact_dedup,
        campaign_split, campaign_dedup, contact_id_map, campaign_id_map,
        data_start_row=TEMPLATE_DATA_START_ROW,
        block_primary=CONTACT_BLOCK_PRIMARY,
        block_secondary=CONTACT_BLOCK_SECONDARY,
        cm_object=CM_OBJECT,
        cm_participating_label=CM_PARTICIPATING_LABEL,
    )


# ===== _is_participating =====

def test_participating_true_values():
    for v in ("TRUE", "True", "true", "1", "כן", "YES", "yes", "X"):
        assert campaign_member_builder._is_participating(v), f"expected True for {v!r}"

def test_not_participating_false_values():
    for v in ("", "0", "False", "false", "לא", "no", "NO"):
        assert not campaign_member_builder._is_participating(v), f"expected False for {v!r}"


# ===== derive_campaign_members =====

def test_true_produces_one_record():
    """TRUE בשורה ובבלוק → CMRecord אחד עם ה-Ids הנכונים."""
    recs = _derive()
    assert len(recs) == 1
    r = recs[0]
    assert r.contact_id == "ctc001"
    assert r.campaign_id == "camp001"
    assert r.contact_local_key == "C1"
    assert r.campaign_local_key == "K1"
    assert r.warning is None


def test_false_skipped():
    """FALSE → שורה לא נגזרת."""
    recs = _derive(tmpl_rows=_tmpl(ctrl_val="FALSE"))
    assert recs == []


def test_two_blocks_both_true_produce_two_records():
    """שני בלוקים עם TRUE → 2 רשומות."""
    R = TEMPLATE_DATA_START_ROW
    # טמפלייט: עמודה 5 = בלוק ראשי, עמודה 8 = בלוק נוסף
    header = [[] for _ in range(TEMPLATE_DATA_START_ROW)]
    row = [""] * 9
    row[5] = "TRUE"   # ראשי
    row[8] = "TRUE"   # נוסף
    tmpl = header + [row]

    contact_split = [
        _sr_contact(R, CONTACT_BLOCK_PRIMARY, {"FirstName": "דן"}),
        _sr_contact(R, CONTACT_BLOCK_SECONDARY, {"FirstName": "ענת"}),
    ]
    contact_dedup = _dedup(_person("C1", [0]), _person("C2", [1]))
    cols = [
        _ctrl_col(CONTACT_BLOCK_PRIMARY, index=5),
        _ctrl_col(CONTACT_BLOCK_SECONDARY, index=8),
    ]
    recs = _derive(
        contact_split=contact_split, contact_dedup=contact_dedup,
        contact_id_map={"C1": "ctc001", "C2": "ctc002"},
        tmpl_rows=tmpl, columns=cols,
    )
    assert len(recs) == 2
    assert {r.contact_id for r in recs} == {"ctc001", "ctc002"}


def test_missing_contact_id_produces_warning():
    """Contact_id חסר → warning."""
    recs = _derive(contact_id_map={})  # C1 חסר במפה
    assert len(recs) == 1
    assert recs[0].warning is not None
    assert recs[0].contact_id == ""


def test_missing_campaign_id_produces_warning():
    """Campaign_id חסר → warning."""
    recs = _derive(campaign_id_map={})
    assert recs[0].warning is not None
    assert recs[0].campaign_id == ""


def test_no_control_col_for_block_skips_block():
    """אין עמודת-בקרה לבלוק → לא יוצרים CM לאותו בלוק."""
    recs = _derive(columns=[_field_col(CONTACT_BLOCK_PRIMARY)])  # בלי ctrl
    assert recs == []


def test_field_values_read_from_template():
    """ערכי שדות נוספים נקראים נכון מהטמפלייט."""
    recs = _derive()
    assert recs[0].field_values.get("Status") == "Sent"


def test_contact_name_from_split_values():
    """שם איש-הקשר נגזר מה-values של split_record."""
    recs = _derive()
    assert recs[0].contact_name == "דן לוי"


# ===== build_campaign_member_grid =====

def _grid(recs, field_cols=None):
    fc = field_cols or [("Status", "סטטוס")]
    return campaign_member_builder.build_campaign_member_grid(recs, fc)

def test_grid_has_two_header_rows_and_one_data_row():
    recs = _derive()
    grid, _ = _grid(recs)
    assert len(grid) == 3  # 2 כותרות + 1 נתון

def test_grid_skips_records_with_warning():
    recs = _derive(contact_id_map={})  # warning
    grid, _ = _grid(recs)
    assert len(grid) == 2  # רק כותרות

def test_grid_data_row_has_correct_ids():
    recs = _derive()
    grid, _ = _grid(recs)
    row = grid[2]
    assert row[1] == "ctc001"   # ContactId
    assert row[2] == "camp001"  # CampaignId

def test_grid_display_col_colored_red():
    recs = _derive()
    _, colors = _grid(recs)
    assert len(colors) == 1
    row0, col0, color = colors[0]
    assert col0 == 0 and color == "red"
