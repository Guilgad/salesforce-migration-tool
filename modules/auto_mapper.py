"""
auto_mapper — מיפוי-אוטומטי של עמודות-לקוח לשדות סיילספורס (שלב 2 של v2).

דטרמיניסטי, ללא LLM: התאמת-שם מנורמלת (label/API) + דמיון-מחרוזות (difflib).
התאמה חד-משמעית → ok (אוטומטי); עמומה → "בדוק התאמה" עם מועמדים; אין → "בדוק התאמה" ריק.
"""
from __future__ import annotations

from dataclasses import dataclass, field as dc_field
from difflib import SequenceMatcher

from config.runtime_schema import (
    ColumnMapping, ValueMap, ROLE_FIELD, ROLE_SKIP, ST_OK, ST_CHECK,  # noqa: F401
)
from modules import formatter, mapper
from modules.field_dictionary import FieldInfo

# רף-ביטחון: התאמה יחידה מעל העליון → אוטומטי; מעל התחתון → מועמד ל"בדוק התאמה"
CONFIDENT = 0.90
CANDIDATE = 0.70
MAX_CANDIDATES = 5


def _norm(s: str) -> str:
    """נירמול להשוואה: אותיות קטנות, ללא רווחים/קו-תחתון/מקף."""
    return "".join(ch for ch in (s or "").lower() if ch not in " _-")


@dataclass
class Suggestion:
    """תוצאת הצעת-מיפוי לעמודה אחת."""
    field_api: str = ""
    confident: bool = False
    candidates: list[str] = dc_field(default_factory=list)


def suggest_field(label: str, fields: list[FieldInfo]) -> Suggestion:
    """
    מציע שדה לעמודה לפי שם-התווית של הלקוח.
    1) התאמה מדויקת (אחרי נירמול) על label או api — יחידה → בטוחה.
    2) אחרת difflib: הטוב-ביותר ≥ CONFIDENT ויחיד ברמתו → בטוחה; אחרת מועמדים.
    """
    target = _norm(label)
    if not target or not fields:
        return Suggestion()

    exact = [f for f in fields if _norm(f.label) == target or _norm(f.api) == target]
    if len(exact) == 1:
        return Suggestion(exact[0].api, True, [exact[0].api])
    if len(exact) > 1:
        return Suggestion("", False, [f.api for f in exact[:MAX_CANDIDATES]])

    scored: list[tuple[float, str]] = []
    for f in fields:
        score = max(
            SequenceMatcher(None, target, _norm(f.label)).ratio(),
            SequenceMatcher(None, target, _norm(f.api)).ratio(),
        )
        if score >= CANDIDATE:
            scored.append((score, f.api))
    scored.sort(reverse=True)
    candidates = [api for _, api in scored[:MAX_CANDIDATES]]
    if scored and scored[0][0] >= CONFIDENT and (
        len(scored) == 1 or scored[1][0] < CONFIDENT
    ):
        return Suggestion(scored[0][1], True, candidates)
    return Suggestion("", False, candidates)
