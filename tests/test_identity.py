"""בדיקות מנוע הזיהוי (identity.compute_key) — עדיפות, צירוף-AND, דרישת-שדות, נירמול."""
from modules import identity


def test_priority_first_full_mechanism_wins():
    """המנגנון הראשון שכל שדותיו מלאים מנצח — גם אם מנגנון מאוחר יותר גם מלא."""
    rec = {"ID_Number__c": "123", "FirstName": "דנה", "LastName": "כהן"}
    res = identity.compute_key(rec, [["ID_Number__c"], ["FirstName", "LastName"]])
    assert res.mechanism_index == 0
    assert res.key == "123"
    assert res.fields_used == ["ID_Number__c"]


def test_falls_to_next_mechanism_when_first_incomplete():
    """מנגנון 1 חסר שדה → נופלים למנגנון 2."""
    rec = {"ID_Number__c": "", "FirstName": "דנה", "LastName": "כהן"}
    res = identity.compute_key(rec, [["ID_Number__c"], ["FirstName", "LastName"]])
    assert res.mechanism_index == 1
    assert res.fields_used == ["FirstName", "LastName"]


def test_and_combine_requires_all_fields():
    """צירוף-AND: אם רק חלק משדות המנגנון מלאים — המנגנון לא תופס."""
    rec = {"FirstName": "דנה", "LastName": ""}
    res = identity.compute_key(rec, [["FirstName", "LastName"]])
    assert res.key is None
    assert res.mechanism_index is None


def test_no_mechanism_matches_returns_none():
    """אף מנגנון לא תפס → key=None (סימון לטיפול ידני)."""
    rec = {"Email": "a@b.com"}
    res = identity.compute_key(rec, [["ID_Number__c"], ["FirstName", "LastName"]])
    assert res.key is None


def test_normalization_trims_collapses_and_casefolds():
    """נירמול: חיתוך קצוות, כיווץ רווחים פנימיים, ו-casefold — מפתחות זהים."""
    a = identity.compute_key({"FirstName": "  Dana   Cohen "}, [["FirstName"]])
    b = identity.compute_key({"FirstName": "dana cohen"}, [["FirstName"]])
    assert a.key == b.key


def test_composite_key_combines_fields():
    """מפתח מורכב = צירוף הערכים המנורמלים של כל שדות המנגנון."""
    res = identity.compute_key(
        {"FirstName": "דנה", "LastName": "כהן"}, [["FirstName", "LastName"]]
    )
    # שני רכיבים → מכיל את שניהם, מופרדים במפריד הפנימי
    assert "דנה" in res.key and "כהן" in res.key
    assert res.mechanism_index == 0
