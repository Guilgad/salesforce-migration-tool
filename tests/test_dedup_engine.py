"""בדיקות מנוע ה-dedup — קיבוץ פנימי, מפל-DB, צירוף-מדורג, ambiguous/unkeyed, מונים."""
from modules import dedup_engine

# מנגנונים סטנדרטיים לבדיקות: מנגנון 1 = ת"ז, מנגנון 2 = שם פרטי+משפחה
MECHS = [["ID_Number__c"], ["FirstName", "LastName"]]


def _one(persons, local_key):
    return next(p for p in persons if p.local_key == local_key)


# ===== קיבוץ פנימי =====

def test_internal_chaining_transitive():
    """A↔B חולקים ת"ז, B↔C חולקים אימייל → כל השלושה אדם אחד (שרשור טרנזיטיבי)."""
    records = [
        {"ID_Number__c": "1"},                  # A
        {"ID_Number__c": "1", "Email": "x@x"},  # B
        {"Email": "x@x"},                        # C
    ]
    res = dedup_engine.deduplicate(records, [["ID_Number__c"], ["Email"]], [])
    assert len(res.persons) == 1
    assert sorted(res.persons[0].record_indices) == [0, 1, 2]


def test_internal_direct_same_id_merges():
    """שתי שורות עם אותה ת"ז → אדם אחד."""
    records = [{"ID_Number__c": "5"}, {"ID_Number__c": "5"}]
    res = dedup_engine.deduplicate(records, MECHS, [])
    assert len(res.persons) == 1


def test_internal_no_shared_field_stays_separate():
    """שורות שלא חולקות שום מפתח → אנשים נפרדים."""
    records = [{"ID_Number__c": "1"}, {"ID_Number__c": "2"}]
    res = dedup_engine.deduplicate(records, MECHS, [])
    assert len(res.persons) == 2


# ===== הצלבה מול DB =====

def test_upsert_by_mechanism_1_green():
    """התאמה לפי מנגנון 1 → Upsert, found_by=0 (יוצג 🟢)."""
    records = [{"ID_Number__c": "1"}]
    db = [{"Id": "a", "ID_Number__c": "1"}]
    res = dedup_engine.deduplicate(records, MECHS, db)
    p = res.persons[0]
    assert p.action == dedup_engine.ACTION_UPSERT and p.sf_id == "a" and p.found_by == 0


def test_upsert_by_mechanism_2_yellow():
    """מנגנון 1 לא תפס אך מנגנון 2 (שם) כן → Upsert, found_by=1 (יוצג 🟡)."""
    records = [{"ID_Number__c": "999", "FirstName": "דנה", "LastName": "כהן"}]
    db = [{"Id": "b", "ID_Number__c": "111", "FirstName": "דנה", "LastName": "כהן"}]
    res = dedup_engine.deduplicate(records, MECHS, db)
    p = res.persons[0]
    assert p.action == dedup_engine.ACTION_UPSERT and p.sf_id == "b" and p.found_by == 1


def test_insert_when_keyed_but_no_db_match():
    """רשומה עם מפתח אך ללא התאמה ב-DB → Insert (לא ambiguous, לא unkeyed)."""
    records = [{"ID_Number__c": "9"}]
    db = [{"Id": "a", "ID_Number__c": "1"}]
    res = dedup_engine.deduplicate(records, MECHS, db)
    p = res.persons[0]
    assert p.action == dedup_engine.ACTION_INSERT
    assert p.sf_id is None and not p.ambiguous and not p.unkeyed


def test_digits_only_normalization_matches():
    """ת"ז עם מקפים בקלט מתאימה לת"ז ספרות-בלבד ב-DB (נירמול פנימי)."""
    records = [{"ID_Number__c": "123-456"}]
    db = [{"Id": "z", "ID_Number__c": "123456"}]
    res = dedup_engine.deduplicate(records, MECHS, db, digits_only_fields={"ID_Number__c"})
    assert res.persons[0].action == dedup_engine.ACTION_UPSERT
    assert res.persons[0].sf_id == "z"


# ===== צירוף-מדורג וריבוי-התאמות =====

def test_combined_mechanisms_narrow_to_single():
    """עוגן עם >1 התאמה שמצטמצם ל-Id יחיד דרך מנגנון-המשך → Upsert בשילוב, לא עיוור."""
    records = [{"ID_Number__c": "1", "FirstName": "דנה", "LastName": "כהן"}]
    db = [
        {"Id": "x", "ID_Number__c": "1", "FirstName": "דנה", "LastName": "כהן"},
        {"Id": "y", "ID_Number__c": "1", "FirstName": "בני", "LastName": "לוי"},
    ]
    res = dedup_engine.deduplicate(records, MECHS, db)
    p = res.persons[0]
    assert p.action == dedup_engine.ACTION_UPSERT and p.sf_id == "x"
    assert p.combined_mechs == [0, 1] and not p.ambiguous


def test_true_ambiguous_when_combine_cannot_narrow():
    """עוגן עם >1 שלא מצטמצם → ambiguous, match_ids מאוכלס, בלי Id עיוור."""
    records = [{"ID_Number__c": "1"}]  # אין שם לצמצום
    db = [
        {"Id": "x", "ID_Number__c": "1"},
        {"Id": "y", "ID_Number__c": "1"},
    ]
    res = dedup_engine.deduplicate(records, MECHS, db)
    p = res.persons[0]
    assert p.ambiguous and p.sf_id is None
    assert p.action == dedup_engine.ACTION_INSERT  # לא נטען — אין Id
    assert p.match_ids == ["x", "y"]


def test_regression_ambiguous_not_blind_insert():
    """רגרסיית פרוסה 7: רשומה דו-משמעית לא נספרת כ-Insert עיוור."""
    records = [{"ID_Number__c": "1"}]
    db = [{"Id": "x", "ID_Number__c": "1"}, {"Id": "y", "ID_Number__c": "1"}]
    res = dedup_engine.deduplicate(records, MECHS, db)
    assert res.counts["ambiguous"] == 1
    assert res.counts["inserts"] == 0


# ===== unkeyed =====

def test_unkeyed_when_no_mechanism_fills():
    """רשומה שאף מנגנון לא תפס (אין שדה רלוונטי) → unkeyed."""
    records = [{"SomeOtherField": "ערך"}]
    res = dedup_engine.deduplicate(records, MECHS, [])
    p = res.persons[0]
    assert p.unkeyed and p.sf_id is None


# ===== מונים =====

def test_counts_are_mutually_exclusive_and_sum_to_persons():
    """כל אדם נספר בדיוק בקטגוריה אחת; הסכום = מספר האנשים."""
    records = [
        {"ID_Number__c": "1"},                                   # Upsert (יחיד ב-DB)
        {"ID_Number__c": "8"},                                   # Insert (אין ב-DB)
        {"ID_Number__c": "2"},                                   # ambiguous (כפול ב-DB)
        {"SomeOtherField": "ערך"},                               # unkeyed
    ]
    db = [
        {"Id": "a", "ID_Number__c": "1"},
        {"Id": "x", "ID_Number__c": "2"},
        {"Id": "y", "ID_Number__c": "2"},
    ]
    res = dedup_engine.deduplicate(records, MECHS, db)
    c = res.counts
    assert c == {"inserts": 1, "upserts": 1, "ambiguous": 1, "unkeyed": 1}
    assert sum(c.values()) == len(res.persons)
