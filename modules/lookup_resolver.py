"""
מנוע יישוב-Lookups: ממלא שדה-Id-יעד על רשומות-המקור לפי זיהוי-היעד.

Lookup = עמודה באובייקט-מקור שערכה הוא מפתח-טבעי של אובייקט-יעד (למשל שם-חשבון),
וצריך לתרגם אותו ל-Id של רשומת-היעד (למשל `AccountId`). היישוב מתבצע מול רשומות-ה-DB
של אובייקט-היעד — שדה-הזיהוי (`identified_by`) מותאם case/whitespace-insensitive
(אותו נירמול כמו מנוע-הזיהוי, `identity.normalize`).

מקרה-בסיס (היחיד הנתמך כרגע): היעד **קיים כבר ב-Salesforce** (DB/extra_objects). יעד
שנוצר באותה טעינה (Id מ-paste-back) — follow-up מתועד; אינו מכוסה כאן.
"""
from __future__ import annotations

from typing import Callable

from modules import identity
from modules.splitter import SplitRecord


def _target_index(db_recs: list[dict], match_field: str) -> dict[str, str]:
    """אינדקס {ערך-מנורמל-של-match_field: Id} מרשומות-ה-DB של היעד (ראשון מנצח)."""
    idx: dict[str, str] = {}
    for r in db_recs:
        key = identity.normalize(r.get(match_field, ""))
        sf_id = r.get("Id")
        if key and sf_id:
            idx.setdefault(key, sf_id)
    return idx


def resolve_lookups(
    records: list[SplitRecord],
    source_object: str,
    lookups: list,
    schema,
    target_db_provider: Callable[[str], list[dict]],
) -> tuple[list[SplitRecord], dict[str, int]]:
    """
    ממלא `target_field` על כל רשומת-מקור לפי התאמת ערך-עמודת-המקור מול זיהוי-היעד.

    records:             רשומות אובייקט-המקור (SplitRecord).
    source_object:       שם-ה-API של אובייקט-המקור (מסננים lookups לפיו).
    lookups:             schema.lookups (כל ה-LookupConfig; מסוננים ל-source_object).
    schema:              לתרגום source_col_index → field_api דרך schema.mappings.
    target_db_provider:  callable(target_object_api) → list[dict] רשומות-DB של היעד.

    מחזיר (records_חדשים, stats) כאשר stats = {"resolved": n, "unresolved": m}.
    רשומה עם ערך-מקור שלא נמצא → target_field="" (נספר כ-unresolved). ערך-מקור ריק
    → לא נחשב (אין מה לפתור).
    """
    relevant = [lc for lc in lookups if lc.source_object == source_object]
    if not relevant:
        return list(records), {"resolved": 0, "unresolved": 0}

    # תוכנית פר-lookup: (target_field, source_field_api, אינדקס-יעד)
    plans = []
    for lc in relevant:
        cm = schema.mappings.get(lc.source_col_index)
        src_field = cm.field_api if cm else None
        match_field = lc.identified_by[0] if lc.identified_by else "Name"
        index = _target_index(target_db_provider(lc.target_object), match_field)
        plans.append((lc.target_field, src_field, index))

    resolved = unresolved = 0
    out: list[SplitRecord] = []
    for rec in records:
        vals = dict(rec.values)
        for target_field, src_field, index in plans:
            if not src_field:
                continue
            raw = vals.get(src_field, "")
            if not str(raw).strip():
                vals.setdefault(target_field, "")
                continue
            sf_id = index.get(identity.normalize(raw), "")
            vals[target_field] = sf_id
            if sf_id:
                resolved += 1
            else:
                unresolved += 1
        out.append(SplitRecord(
            object_api=rec.object_api,
            block=rec.block,
            source_row=rec.source_row,
            values=vals,
        ))
    return out, {"resolved": resolved, "unresolved": unresolved}
