"""
בדיקת-אינטגרציה מקצה-לקצה לצינור-הבנייה של v2 (רשת-הביטחון).

בניגוד לבדיקות-היחידה (שמזינות לכל מנוע נתונים-מושלמים ביד), הבדיקה הזו בונה
`RuntimeSchema` **בדיוק כמו שה-UI בונה** (mappings, identity, db_tabs) ומריצה את כל
הרצף דרך `orchestrator.build_object_core` — adapt_columns → split → value_maps →
extra_fields → deduplicate → build_contacts_grid → 15→18 — ובודקת **נכונות-פלט**:
insert מול upsert, ו-backfill מה-DB.

זו הבדיקה שהייתה תופסת את באג ה-`db_tabs` (DB ריק → הכל נראה כ-Insert): ראה
`test_empty_db_makes_everything_insert` שמנעיל את ההתנהגות בשני הכיוונים.
"""
from config.runtime_schema import (
    RuntimeSchema, ColumnMapping, IdentityConfig, ExtraField, LookupConfig,
    ROLE_FIELD, ST_OK,
)
from modules.orchestrator import build_object_core


# Id של 18 תווים — לא עובר המרת 15→18, כך שההשוואה ישירה
_DB_ID = "003ID0000001AAAAAA"


def _contact_schema() -> RuntimeSchema:
    """Schema לאובייקט Contact, כמו שה-UI היה בונה אחרי מיפוי + זיהוי + חיבור-DB."""
    s = RuntimeSchema()
    s.mappings = {
        0: ColumnMapping(col_index=0, object_api="Contact", field_api="FirstName",
                         role=ROLE_FIELD, status=ST_OK, instance=1),
        1: ColumnMapping(col_index=1, object_api="Contact", field_api="LastName",
                         role=ROLE_FIELD, status=ST_OK, instance=1),
        2: ColumnMapping(col_index=2, object_api="Contact", field_api="ID_Number__c",
                         role=ROLE_FIELD, status=ST_OK, instance=1),
        3: ColumnMapping(col_index=3, object_api="Contact", field_api="Email",
                         role=ROLE_FIELD, status=ST_OK, instance=1),
    }
    # זיהוי לפי תעודת-זהות
    s.identity = {"Contact": IdentityConfig(mechanisms=[["ID_Number__c"]])}
    # חיבור-DB: לשונית לכל אובייקט (התיקון של db_tabs)
    s.db_sheet_id = "db_sheet"
    s.db_tabs = {"Contact": "Contact"}
    s.input_sheet_id = "in_sheet"
    s.input_tab = "data"
    return s


def _input_rows() -> list:
    """3 שורות-כותרת (object/label/api) ואז 2 שורות-נתונים."""
    return [
        ["Contact", "Contact", "Contact", "Contact"],          # object_row
        ["שם פרטי", "שם משפחה", "ת״ז", "אימייל"],               # label_row
        ["FirstName", "LastName", "ID_Number__c", "Email"],    # api_row
        ["יוסי", "כהן", "111", ""],        # קיים ב-DB (ת״ז 111) + אימייל ריק → backfill
        ["דנה", "לוי", "222", "dana@x.com"],                   # לא ב-DB → Insert
    ]


def _db_recs() -> list:
    """רשומות-ה-DB כפי ש-rows_to_dicts היה מחזיר מהלשונית של Contact."""
    return [
        {"Id": _DB_ID, "ID_Number__c": "111",
         "FirstName": "יוסי", "LastName": "כהן", "Email": "yossi@db.com"},
    ]


def _row_by_idnum(out, idnum: str) -> dict:
    """מחזיר את שורת-הפלט (כ-{api: value}) שה-ID_Number__c שלה = idnum."""
    api_header = out.grid[1]
    for row in out.grid[2:]:
        rec = dict(zip(api_header, row))
        if rec.get("ID_Number__c") == idnum:
            return rec
    raise AssertionError(f"לא נמצאה שורת-פלט עם ת״ז {idnum}")


def test_record_matching_db_becomes_upsert():
    """רשומה שת״ז שלה קיימת ב-DB → הגריד נושא את ה-Id מה-DB (Upsert, לא Insert)."""
    out = build_object_core(_contact_schema(), "Contact", _input_rows(), _db_recs())
    yossi = _row_by_idnum(out, "111")
    assert yossi["Id"] == _DB_ID  # ← Upsert: ה-Id מה-DB נכנס לגריד


def test_record_not_in_db_becomes_insert():
    """רשומה שאינה ב-DB → עמודת ה-Id ריקה (Insert חדש)."""
    out = build_object_core(_contact_schema(), "Contact", _input_rows(), _db_recs())
    dana = _row_by_idnum(out, "222")
    assert dana["Id"] == ""  # ← Insert: אין Id


def test_upsert_backfills_empty_field_from_db():
    """תא-ריק ברשומת-Upsert → מתמלא מהערך ב-DB (חובת-נכונות: לא מוחק דאטה ב-SF)."""
    out = build_object_core(_contact_schema(), "Contact", _input_rows(), _db_recs())
    yossi = _row_by_idnum(out, "111")
    assert yossi["Email"] == "yossi@db.com"  # אימייל היה ריק בקלט → backfill מה-DB


def test_empty_db_makes_everything_insert():
    """
    **רשת-הביטחון של db_tabs:** אם רשומות-ה-DB ריקות (כפי שקרה כשהמיפוי לא אוכלס) —
    אפילו רשומה שאמורה להתאים נראית כחדשה (Id ריק). הבדיקה מנעילה את ההבדל: עם DB →
    Upsert; בלי DB → Insert. נפילה כאן = חזרת הבאג.
    """
    out = build_object_core(_contact_schema(), "Contact", _input_rows(), [])
    yossi = _row_by_idnum(out, "111")
    assert yossi["Id"] == ""  # בלי DB — אין Upsert (זה היה הבאג בייצור)


# ── digits_only_fields wiring (צעד 2) ────────────────────────────────────────

def _phone_schema(digits: bool) -> RuntimeSchema:
    """Schema לזיהוי-Contact לפי טלפון; digits=True → השדה בנירמול-ספרות."""
    s = RuntimeSchema()
    s.mappings = {
        0: ColumnMapping(col_index=0, object_api="Contact", field_api="MobilePhone",
                         role=ROLE_FIELD, status=ST_OK, instance=1),
    }
    s.identity = {"Contact": IdentityConfig(mechanisms=[["MobilePhone"]])}
    s.digits_only_fields = {"MobilePhone"} if digits else set()
    s.db_sheet_id = "db"
    s.db_tabs = {"Contact": "Contact"}
    s.input_sheet_id = "in"
    s.input_tab = "data"
    return s


def _phone_rows() -> list:
    return [
        ["Contact"],
        ["נייד"],
        ["MobilePhone"],
        ["050-1234567"],   # אותו מספר כמו ב-DB, פורמט שונה
    ]


def _phone_db() -> list:
    return [{"Id": _DB_ID, "MobilePhone": "0501234567"}]


def test_digits_only_field_matches_across_formats():
    """כשהשדה ב-digits_only — '050-1234567' מתאים ל-'0501234567' שב-DB → Upsert."""
    out = build_object_core(_phone_schema(digits=True), "Contact", _phone_rows(), _phone_db())
    data = out.grid[2]
    id_col = out.grid[1].index("Id")
    assert data[id_col] == _DB_ID  # ← נירמול-ספרות אִפשר את ההתאמה


def test_without_digits_only_formats_do_not_match():
    """בקרה: בלי digits_only, הפורמטים שונים → אין התאמה → Insert (Id ריק)."""
    out = build_object_core(_phone_schema(digits=False), "Contact", _phone_rows(), _phone_db())
    data = out.grid[2]
    id_col = out.grid[1].index("Id")
    assert data[id_col] == ""  # פורמט שונה ללא נירמול → לא מתאים


# ── Lookups + derived columns (צעד 3) ────────────────────────────────────────

def _lookup_schema() -> RuntimeSchema:
    s = RuntimeSchema()
    s.mappings = {
        0: ColumnMapping(col_index=0, object_api="Contact", field_api="FirstName",
                         role=ROLE_FIELD, status=ST_OK, instance=1),
        1: ColumnMapping(col_index=1, object_api="Contact", field_api="ID_Number__c",
                         role=ROLE_FIELD, status=ST_OK, instance=1),
        2: ColumnMapping(col_index=2, object_api="Contact", field_api="AccountName",
                         role=ROLE_FIELD, status=ST_OK, instance=1),
    }
    s.identity = {"Contact": IdentityConfig(mechanisms=[["ID_Number__c"]])}
    s.lookups = [
        LookupConfig(source_object="Contact", source_col_index=2,
                     target_object="Account", target_field="AccountId",
                     identified_by=["Name"]),
    ]
    return s


def _lookup_rows() -> list:
    return [
        ["Contact", "Contact", "Contact"],
        ["שם", "ת״ז", "חשבון"],
        ["FirstName", "ID_Number__c", "AccountName"],
        ["יוסי", "111", "Acme"],
    ]


def test_lookup_fills_target_field_in_grid():
    """עמודת-מקור 'Acme' → היעד AccountId מתמלא ב-Id של החשבון, ומופיע בגריד."""
    provider = lambda t: [{"Name": "Acme", "Id": "001ACMEID"}] if t == "Account" else []
    out = build_object_core(_lookup_schema(), "Contact", _lookup_rows(), [],
                            lookup_db_provider=provider)
    assert "AccountId" in out.grid[1]          # עמודה נגזרת קיימת בפלט
    acct_col = out.grid[1].index("AccountId")
    assert out.grid[2][acct_col] == "001ACMEID"   # מולא ב-Id מהיעד
    assert out.lookup_stats == {"resolved": 1, "unresolved": 0}


def test_extra_field_appears_in_grid():
    """תיקון-בונוס: ערך-קבוע (ExtraField) הופך לעמודת-פלט (היה מוזרק ל-values אך לא לגריד)."""
    s = RuntimeSchema()
    s.mappings = {
        0: ColumnMapping(col_index=0, object_api="Contact", field_api="ID_Number__c",
                         role=ROLE_FIELD, status=ST_OK, instance=1),
    }
    s.identity = {"Contact": IdentityConfig(mechanisms=[["ID_Number__c"]])}
    s.extra_fields = [ExtraField("Contact", "LeadSource", "Web")]
    rows = [["Contact"], ["ת״ז"], ["ID_Number__c"], ["111"]]
    out = build_object_core(s, "Contact", rows, [])
    assert "LeadSource" in out.grid[1]
    ls_col = out.grid[1].index("LeadSource")
    assert out.grid[2][ls_col] == "Web"


def test_per_mechanism_dedup_flows_through_build_core():
    """
    חוזה-בדיקות: dedup פר-מנגנון מחווט מ-`schema.identity` דרך build_object_core.
    מנגנון 1 (ת״ז) מאחד; מנגנון 2 (שם-משפחה) לא. שתי שורות עם אותה ת״ז מתאחדות לשורת-פלט
    אחת, אבל שורה שלישית שרק חולקת שם-משפחה (ת״ז שונה) נשארת נפרדת.
    """
    from config.runtime_schema import ColumnMapping, ROLE_FIELD, ST_OK
    s = RuntimeSchema()
    s.mappings = {
        0: ColumnMapping(col_index=0, object_api="Contact", field_api="LastName",
                         role=ROLE_FIELD, status=ST_OK, instance=1),
        1: ColumnMapping(col_index=1, object_api="Contact", field_api="ID_Number__c",
                         role=ROLE_FIELD, status=ST_OK, instance=1),
    }
    s.identity = {"Contact": IdentityConfig(
        mechanisms=[["ID_Number__c"], ["LastName"]],
        dedup_mechanisms=[True, False],   # מאחד לפי ת״ז בלבד
    )}
    rows = [
        ["Contact", "Contact"],
        ["שם משפחה", "ת״ז"],
        ["LastName", "ID_Number__c"],
        ["כהן", "111"],   # מתאחד עם הבא (אותה ת״ז)
        ["לוי", "111"],   # אותה ת״ז → מאוחד
        ["כהן", "222"],   # אותו שם-משפחה כמו שורה 1, ת״ז שונה → נשאר נפרד
    ]
    out = build_object_core(s, "Contact", rows, [])
    data_rows = out.grid[2:]
    assert len(data_rows) == 2   # {111 מאוחד} + {222 נפרד}

    # אם dedup פר-מנגנון לא היה מחווט (היה מאחד גם לפי שם) → היו פחות/יותר שורות
    s.identity["Contact"].dedup_mechanisms = [False, False]
    out2 = build_object_core(s, "Contact", rows, [])
    assert len(out2.grid[2:]) == 3   # ללא איחוד כלל → 3 שורות
