"""
RuntimeSchema — סכמת-ריצה דינמית של v2.

מחליפה את config/template_config.py: כל מה שהיה קשיח-ללקוח (שם-לשונית, אינדקסי-שורות,
בלוקים, אובייקטים) כעת נבנה בזמן-ריצה מהקלט ומבחירות-ה-UI.
"""
from __future__ import annotations

from dataclasses import dataclass, field


# ── step-2 mapping: roles & statuses ──────────────────────────────────────────
ROLE_FIELD = "field"      # עמודה רגילה — נטענת כשדה
ROLE_CONTROL = "control"  # עמודת-בקרה (דגל) — נצרכת ע"י קשרים/junction, לא נטענת
ROLE_SKIP = "skip"        # לא רלוונטי — לא נטענת

ST_OK = "ok"              # תקין (אוטומטי/ידני/מהקובץ)
ST_CHECK = "check"        # בדוק התאמה — ממתין לאישור המשתמש


@dataclass
class ValueMapEntry:
    """שורה אחת במפת-ערכים: ערך-מקור → ערך-יעד (נטען) + שם לתצוגה."""
    source: str
    target: str
    display: str = ""


@dataclass
class ValueMap:
    """מפת-ערכים לעמודה (תרגום פיקליסט ידני). default ריק = ערך-לא-ממופה יסומן כבעיה."""
    entries: list[ValueMapEntry] = field(default_factory=list)
    default: str = ""

    def apply(self, raw: str) -> tuple[str, bool]:
        """(ערך-מתורגם, נמצא?). לא-נמצא → (default, False)."""
        key = (raw or "").strip()
        for e in self.entries:
            if e.source == key:
                return e.target, True
        return self.default, False


@dataclass
class ColumnMapping:
    """החלטת-מיפוי לעמודת-קלט אחת (לפי אינדקס עמודה)."""
    col_index: int
    object_api: str = ""
    field_api: str = ""
    role: str = ROLE_FIELD            # ROLE_FIELD | ROLE_CONTROL | ROLE_SKIP
    source: str = ""                  # "file" | "auto" | "manual" | ""
    status: str = ST_CHECK            # ST_OK | ST_CHECK (רלוונטי רק ל-ROLE_FIELD)
    instance: int = 1                 # מופע בשורה (1 = רגיל); ראה multi_instance
    candidates: list[str] = field(default_factory=list)  # מועמדים ל"בדוק התאמה"


@dataclass
class IdentityConfig:
    """מנגנוני-זיהוי לאובייקט אחד (שלב 3): מדורגים לפי עדיפות, כל מנגנון = צירוף AND."""
    mechanisms: list[list[str]] = field(default_factory=list)
    dedup_internal: bool = False   # זיהוי כפילויות פנימיות — כבוי כברירת-מחדל


@dataclass
class ExtraField:
    """שדה-יעד ללא עמודת-מקור — ערך קבוע לכל הרשומות (למשל LeadSource)."""
    object_api: str
    field_api: str
    constant_value: str = ""


@dataclass
class ObjectDef:
    """Salesforce object to be loaded, as discovered at runtime."""
    api_name: str
    display_name: str
    instance_count: int = 1   # >1 = same object appears N times per row (block mechanism)


@dataclass
class RuntimeSchema:
    """
    All v2 runtime configuration — single source of truth.
    Built progressively: connection info in step 1, columns in step 2, etc.
    """
    # ── Input sheet ──────────────────────────────────────────────────────────
    input_sheet_id: str = ""
    input_tab: str = ""
    table_type: str = "multi"       # "single" | "multi"
    single_object_api: str = ""     # only when table_type == "single"

    # ── 3-row header convention ───────────────────────────────────────────────
    object_row: int = 0             # row 0: SF object name / block name
    label_row: int = 1              # row 1: customer column label
    api_row: int = 2                # row 2: SF API field name (usually empty → mapping fills it)
    data_start_row: int = 3

    # ── Field-dictionary sheet ────────────────────────────────────────────────
    fielddict_sheet_id: str = ""
    fielddict_tab: str = ""
    fielddict_objects: list[str] = field(default_factory=list)

    # ── DB export sheet ───────────────────────────────────────────────────────
    db_sheet_id: str = ""
    db_tabs: dict[str, str] = field(default_factory=dict)   # {api_name: tab_name}

    # ── Derived from input sheet (populated by schema_reader) ────────────────
    objects: list[ObjectDef] = field(default_factory=list)

    # ── Step-2 mapping state ──────────────────────────────────────────────────
    mappings: dict[int, ColumnMapping] = field(default_factory=dict)   # {col_index: …}
    value_maps: dict[int, ValueMap] = field(default_factory=dict)      # {col_index: …}
    extra_fields: list[ExtraField] = field(default_factory=list)
    multi_instance: dict[str, bool] = field(default_factory=dict)      # {object_api: shown?}

    # ── Step-3 identity state ─────────────────────────────────────────────────
    identity: dict[str, IdentityConfig] = field(default_factory=dict)  # {object_api: …}
    extra_objects: list[str] = field(default_factory=list)             # זיהוי-בלבד (לא נטענים)
