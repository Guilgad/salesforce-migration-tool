"""בדיקות splitter — שני בלוקי Contact, דילוג ריק, source_row אבסולוטי, שדות תקפים בלבד."""
from modules import mapper, splitter


def _col(index, clean_api, label, block, object_api="Contact", status=mapper.STATUS_VALID):
    """עוזר לבניית עמודה ממופה (מדמה את פלט mapper.validate_columns)."""
    return mapper.TemplateColumn(
        index=index, block=block, label=label, proposed_api=clean_api,
        object_api=object_api, clean_api=clean_api, status=status,
    )


# שני בלוקי Contact (ראשי + נוסף) + עמודה INVALID + עמודה של אובייקט אחר
_COLUMNS = [
    _col(1, "FirstName", "שם פרטי", "ראשי"),
    _col(2, "LastName", "שם משפחה", "ראשי"),
    _col(3, "FirstName", "שם פרטי", "נוסף"),
    _col(4, "LastName", "שם משפחה", "נוסף"),
    _col(5, "Bogus__c", "שדה לא תקין", "ראשי", status=mapper.STATUS_INVALID),
    _col(6, "Status", "סטטוס", "ראשי", object_api="CampaignMember"),
]

# 4 שורות-כותרת (0-3) ואז דאטה משורה 4
_HEADERS = [["h"] * 7 for _ in range(4)]


def test_two_blocks_produce_two_records_per_row():
    """לשורת-דאטה אחת עם שני בלוקי Contact → שתי רשומות Contact."""
    rows = _HEADERS + [["", "דנה", "כהן", "יוסי", "לוי", "x", "y"]]
    recs = splitter.split_object("Contact", rows, _COLUMNS, data_start_row=4)
    assert len(recs) == 2
    blocks = {r.block for r in recs}
    assert blocks == {"ראשי", "נוסף"}


def test_only_valid_fields_of_object_included():
    """נכללים רק שדות STATUS_VALID של האובייקט — INVALID ואובייקט אחר מסוננים."""
    rows = _HEADERS + [["", "דנה", "כהן", "יוסי", "לוי", "x", "y"]]
    main = next(r for r in splitter.split_object("Contact", rows, _COLUMNS, data_start_row=4)
                if r.block == "ראשי")
    assert set(main.values.keys()) == {"FirstName", "LastName"}
    assert "Bogus__c" not in main.values  # INVALID לא נכנס
    assert "Status" not in main.values     # שדה CampaignMember לא נכנס


def test_empty_record_skipped():
    """בלוק שכל תאיו ריקים בשורה → אותה רשומה מדולגת (לא נוצרת רשומה ריקה)."""
    # בלוק 'נוסף' (אינדקסים 3,4) ריק → רק רשומת 'ראשי' אמורה להיווצר
    rows = _HEADERS + [["", "דנה", "כהן", "", "", "", ""]]
    recs = splitter.split_object("Contact", rows, _COLUMNS, data_start_row=4)
    assert len(recs) == 1
    assert recs[0].block == "ראשי"


def test_source_row_is_absolute_sheet_index():
    """source_row = אינדקס השורה בגיליון (0-based), אבסולוטי כולל שורות-הכותרת."""
    rows = _HEADERS + [
        ["", "דנה", "כהן", "", "", "", ""],   # שורה 4
        ["", "מיכל", "אבן", "", "", "", ""],  # שורה 5
    ]
    recs = splitter.split_object("Contact", rows, _COLUMNS, data_start_row=4)
    assert [r.source_row for r in recs] == [4, 5]
