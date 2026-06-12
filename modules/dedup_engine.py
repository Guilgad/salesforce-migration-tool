"""
מנוע dedup — קיבוץ רשומות לאנשים והכרעת Insert/Upsert מול ה-DB.

טהור (בלי I/O): מקבל רשומות, מנגנונים וייצוא-DB, ומחזיר החלטה לכל אדם.
גנרי — מבוסס-מנגנונים בלבד (ישמש גם Campaigns עם מנגנון-שם); ספציפיות-לקוח
נשארת ב-config/בקורא.

שני שלבים, שניהם קוראים ל-identity.compute_key **מנגנון-בכל-פעם** (כפי שסוכם):
  1. קיבוץ פנימי (שרשור): רשומות שחולקות מפתח לא-ריק באותו מנגנון = אותו אדם
     (טרנזיטיבי). מי שלא נתפס באף מנגנון → אדם בודד, מסומן ל-טיפול ידני.
  2. הצלבה מול DB עם **צירוף-מנגנונים מדורג**: העוגן = המנגנון הראשון שתפס.
     תפס בדיוק 1 → Upsert. תפס >1 → מצרפים את מנגנוני-ההמשך לצמצום (חיתוך); הצטמצם
     ל-1 → Upsert בשילוב (לא בוחר עיוור). עדיין >1 → ambiguous (טיפול ידני).
     אף מנגנון לא תפס → Insert.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

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
    ambiguous: bool             # >1 התאמת-DB גם אחרי צירוף → טיפול ידני, בלי Id עיוור
    unkeyed: bool               # אף מנגנון לא תפס את הרשומות → סימון ידני
    match_ids: list[str] = field(default_factory=list)      # מועמדי-DB כש-ambiguous (לטיפול ידני)
    combined_mechs: list[int] = field(default_factory=list)  # מנגנונים שצורפו בהכרעה-בשילוב (לתווית/צבע)


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
) -> tuple[str | None, int | None, bool, list[str], list[int]]:
    """
    התאמה מול ה-DB עבור אדם אחד, עם **צירוף-מנגנונים מדורג** לשבירת ריבוי.
    מחזיר (sf_id, found_by, ambiguous, match_ids, combined_mechs).

    1. אוספים לכל מנגנון את קבוצת ה-ids התואמים (רק מנגנונים עם ≥1 התאמה).
    2. אין אף התאמה → Insert: (None, None, False, [], []).
    3. ה**עוגן** = המנגנון הראשון שתפס. אם תפס בדיוק 1 → Upsert נקי
       (id, anchor, False, [], []).
    4. עוגן עם >1 → צירוף מדורג: מחתכים את המועמדים עם כל מנגנון-המשך שמצמצם אותם
       *בפועל* (חיתוך לא-ריק וקטן יותר). הצטמצם ל-1 → Upsert בשילוב
       (id, anchor, False, [], combined). מנגנון מתנגש (חיתוך ריק) מדולג כרעש.
    5. נגמרו המנגנונים ועדיין >1 → ambiguous: (None, anchor, True, union_ids, []).
       match_ids = איחוד כל המועמדים (לתצוגה בלשונית הידנית).
    """
    matched_sets: list[tuple[int, set[str]]] = []
    for i, mech in enumerate(mechanisms):
        matched: set[str] = set()
        for mi in member_indices:
            key = _mechanism_key(prepped[mi], mech)
            if key is not None:
                matched |= db_indices[i].get(key, set())
        if matched:
            matched_sets.append((i, matched))

    if not matched_sets:
        return None, None, False, [], []  # Insert — אף מנגנון לא תפס

    anchor, anchor_set = matched_sets[0]
    if len(anchor_set) == 1:
        return next(iter(anchor_set)), anchor, False, [], []  # Upsert נקי

    # עוגן דו-משמעי (>1) → צירוף מדורג עם מנגנוני-ההמשך
    current = set(anchor_set)
    combined = [anchor]
    for i, mset in matched_sets[1:]:
        narrowed = current & mset
        if narrowed and len(narrowed) < len(current):  # מצמצם בפועל (לא רעש מתנגש)
            current = narrowed
            combined.append(i)
            if len(current) == 1:
                return next(iter(current)), anchor, False, [], combined

    union_ids: set[str] = set().union(*(m for _, m in matched_sets))
    return None, anchor, True, sorted(union_ids), []  # ambiguous → טיפול ידני


def deduplicate(
    records: list[dict],
    mechanisms: list[list[str]],
    db_records: list[dict],
    *,
    digits_only_fields: set[str] | None = None,
    local_key_prefix: str = "C",
    dedup_internal: bool = True,
) -> DedupResult:
    """
    מקבץ רשומות לאנשים ומכריע Insert/Upsert מול ה-DB.

    records:    רשומות-קלט כ-{api: value}.
    mechanisms: מנגנונים מסודרים לפי עדיפות (כל מנגנון = רשימת שמות-API), מופעלים בלבד.
    db_records: ייצוא ה-DB כ-{api: value}, כולל "Id".
    digits_only_fields: שדות לנירמול ספרות-בלבד (פנימי; לא נוגע בדאטה הנטענת).
    local_key_prefix: קידומת ה-local_key ("C" לאנשי-קשר, "K" לקמפיינים).
    """
    digit_fields = digits_only_fields or set()
    prepped = [_prep(r, digit_fields) for r in records]
    db_prepped = [_prep(r, digit_fields) for r in db_records]

    if dedup_internal:
        groups = _group_internal(prepped, mechanisms)
    else:
        groups = [[i] for i in range(len(prepped))]
    db_indices = _build_db_indices(db_prepped, mechanisms)

    persons: list[PersonResult] = []
    counts = {"inserts": 0, "upserts": 0, "ambiguous": 0, "unkeyed": 0}

    for n, member_indices in enumerate(groups, start=1):
        unkeyed = all(
            _mechanism_key(prepped[mi], mech) is None
            for mi in member_indices
            for mech in mechanisms
        )
        sf_id, found_by, ambiguous, match_ids, combined_mechs = _match_db(
            member_indices, prepped, mechanisms, db_indices
        )
        action = ACTION_UPSERT if sf_id is not None else ACTION_INSERT

        persons.append(
            PersonResult(
                local_key=f"{local_key_prefix}{n}",
                record_indices=member_indices,
                action=action,
                sf_id=sf_id,
                found_by=found_by,
                ambiguous=ambiguous,
                unkeyed=unkeyed,
                match_ids=match_ids,
                combined_mechs=combined_mechs,
            )
        )
        # ספירה הדדית-בלעדית כדי שהמונים יתאמו למה שבאמת ייטען:
        # unkeyed/ambiguous עוברים לטיפול ידני (לא נספרים כ"חדשים").
        if unkeyed:
            counts["unkeyed"] += 1
        elif ambiguous:
            counts["ambiguous"] += 1
        elif action == ACTION_UPSERT:
            counts["upserts"] += 1
        else:
            counts["inserts"] += 1

    return DedupResult(persons=persons, counts=counts)
