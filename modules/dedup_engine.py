"""
מנוע dedup — קיבוץ רשומות לאנשים והכרעת Insert/Upsert מול ה-DB.

טהור (בלי I/O): מקבל רשומות, מנגנונים וייצוא-DB, ומחזיר החלטה לכל אדם.
גנרי — מבוסס-מנגנונים בלבד (ישמש גם Campaigns עם מנגנון-שם); ספציפיות-לקוח
נשארת ב-config/בקורא.

שני שלבים, שניהם קוראים ל-identity.compute_key **מנגנון-בכל-פעם** (כפי שסוכם):
  1. קיבוץ פנימי (שרשור): רשומות שחולקות מפתח לא-ריק באותו מנגנון = אותו אדם
     (טרנזיטיבי). מי שלא נתפס באף מנגנון → אדם בודד, מסומן ל-טיפול ידני.
  2. הצלבה מול DB (מפל מדורג): לכל אדם מנסים מנגנונים לפי עדיפות; הראשון שמביא
     בדיוק התאמה אחת → Upsert (עם ה-Id). יותר מהתאמה אחת → ambiguous (לא בוחר עיוור).
     אף מנגנון לא תפס → Insert.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from modules import identity

ACTION_INSERT = "Insert"
ACTION_UPSERT = "Upsert"

_NON_DIGITS = re.compile(r"\D")


@dataclass
class PersonResult:
    """החלטת dedup לאדם אחד (קבוצת רשומות-קלט שהתמזגו)."""
    local_key: str              # מזהה פנימי יציב (סדר-הופעה: "C1", "C2", ...)
    record_indices: list[int]   # אילו רשומות-קלט התמזגו לאדם הזה
    action: str                 # ACTION_INSERT | ACTION_UPSERT
    sf_id: str | None           # ה-Id מה-DB (Upsert); None ל-Insert
    found_by: int | None        # אינדקס המנגנון שתפס ב-DB (ל-__נמצא_לפי)
    ambiguous: bool             # >1 התאמת-DB → דורש טיפול ידני, בלי Id עיוור
    unkeyed: bool               # אף מנגנון לא תפס את הרשומות → סימון ידני


@dataclass
class DedupResult:
    persons: list[PersonResult]
    counts: dict[str, int]      # inserts / upserts / ambiguous / unkeyed


def _prep(record: dict, digits_only_fields: set[str]) -> dict:
    """עותק-עבודה לנירמול-קדם: שדות-ספרות → ספרות בלבד (לא נוגע בדאטה המקורית)."""
    if not digits_only_fields:
        return record
    out = dict(record)
    for f in digits_only_fields:
        if f in out and out[f] is not None:
            out[f] = _NON_DIGITS.sub("", str(out[f]))
    return out


def _mechanism_key(record: dict, mechanism: list[str]) -> str | None:
    """מפתח של מנגנון בודד לרשומה (None אם לא כל שדותיו מלאים) — דרך compute_key."""
    return identity.compute_key(record, [mechanism]).key


class _UnionFind:
    """איחוד-מציאה לקיבוץ רשומות שחולקות מנגנון (שרשור טרנזיטיבי)."""

    def __init__(self, n: int) -> None:
        self.parent = list(range(n))

    def find(self, x: int) -> int:
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]  # דחיסת-נתיב
            x = self.parent[x]
        return x

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[max(ra, rb)] = min(ra, rb)  # שמירת סדר-הופעה (שורש = מוקדם)


def _group_internal(
    prepped: list[dict], mechanisms: list[list[str]]
) -> list[list[int]]:
    """קיבוץ פנימי בשרשור. מחזיר קבוצות אינדקסים, ממוינות לפי הופעה ראשונה."""
    uf = _UnionFind(len(prepped))
    for mech in mechanisms:
        seen: dict[str, int] = {}  # key → אינדקס הרשומה הראשונה עם המפתח הזה
        for idx, rec in enumerate(prepped):
            key = _mechanism_key(rec, mech)  # מנגנון-בכל-פעם
            if key is None:
                continue
            if key in seen:
                uf.union(seen[key], idx)
            else:
                seen[key] = idx

    groups: dict[int, list[int]] = {}
    for idx in range(len(prepped)):
        groups.setdefault(uf.find(idx), []).append(idx)
    # מיון לפי האינדקס המוקדם בכל קבוצה → local_key דטרמיניסטי לפי סדר-הופעה
    return [groups[root] for root in sorted(groups)]


def _build_db_indices(
    db_prepped: list[dict], mechanisms: list[list[str]]
) -> list[dict[str, set[str]]]:
    """לכל מנגנון: {key → קבוצת db-ids}. רשומת-DB בלי Id מושמטת מהאינדקס."""
    indices: list[dict[str, set[str]]] = []
    for mech in mechanisms:
        index: dict[str, set[str]] = {}
        for rec in db_prepped:
            sid = str(rec.get("Id", "") or "").strip()
            if not sid:
                continue
            key = _mechanism_key(rec, mech)
            if key is not None:
                index.setdefault(key, set()).add(sid)
        indices.append(index)
    return indices


def _match_db(
    member_indices: list[int],
    prepped: list[dict],
    mechanisms: list[list[str]],
    db_indices: list[dict[str, set[str]]],
) -> tuple[str | None, int | None, bool]:
    """
    מפל מדורג מול ה-DB עבור אדם אחד. מחזיר (sf_id, found_by, ambiguous).
    לכל מנגנון לפי הסדר: אוסף את מפתחות חברי-הקבוצה ומאחד את ה-ids התואמים.
      - בדיוק id אחד → (id, i, False)
      - יותר מ-id אחד → (None, i, True)
      - אפס → המנגנון הבא
    בלי פגיעה בכל המנגנונים → (None, None, False).
    """
    for i, mech in enumerate(mechanisms):
        matched: set[str] = set()
        for mi in member_indices:
            key = _mechanism_key(prepped[mi], mech)
            if key is not None:
                matched |= db_indices[i].get(key, set())
        if len(matched) == 1:
            return next(iter(matched)), i, False
        if len(matched) > 1:
            return None, i, True
    return None, None, False


def deduplicate(
    records: list[dict],
    mechanisms: list[list[str]],
    db_records: list[dict],
    *,
    digits_only_fields: set[str] | None = None,
) -> DedupResult:
    """
    מקבץ רשומות לאנשים ומכריע Insert/Upsert מול ה-DB.

    records:    רשומות-קלט כ-{api: value}.
    mechanisms: מנגנונים מסודרים לפי עדיפות (כל מנגנון = רשימת שמות-API), מופעלים בלבד.
    db_records: ייצוא ה-DB כ-{api: value}, כולל "Id".
    digits_only_fields: שדות לנירמול ספרות-בלבד (פנימי; לא נוגע בדאטה הנטענת).
    """
    digit_fields = digits_only_fields or set()
    prepped = [_prep(r, digit_fields) for r in records]
    db_prepped = [_prep(r, digit_fields) for r in db_records]

    groups = _group_internal(prepped, mechanisms)
    db_indices = _build_db_indices(db_prepped, mechanisms)

    persons: list[PersonResult] = []
    counts = {"inserts": 0, "upserts": 0, "ambiguous": 0, "unkeyed": 0}

    for n, member_indices in enumerate(groups, start=1):
        unkeyed = all(
            _mechanism_key(prepped[mi], mech) is None
            for mi in member_indices
            for mech in mechanisms
        )
        sf_id, found_by, ambiguous = _match_db(
            member_indices, prepped, mechanisms, db_indices
        )
        action = ACTION_UPSERT if sf_id is not None else ACTION_INSERT

        persons.append(
            PersonResult(
                local_key=f"C{n}",
                record_indices=member_indices,
                action=action,
                sf_id=sf_id,
                found_by=found_by,
                ambiguous=ambiguous,
                unkeyed=unkeyed,
            )
        )
        if ambiguous:
            counts["ambiguous"] += 1
        if unkeyed:
            counts["unkeyed"] += 1
        counts["upserts" if action == ACTION_UPSERT else "inserts"] += 1

    return DedupResult(persons=persons, counts=counts)
