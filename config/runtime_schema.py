"""
RuntimeSchema — סכמת-ריצה דינמית של v2.

מחליפה את config/template_config.py: כל מה שהיה קשיח-ללקוח (שם-לשונית, אינדקסי-שורות,
בלוקים, אובייקטים) כעת נבנה בזמן-ריצה מהקלט ומבחירות-ה-UI.
"""
from __future__ import annotations

from dataclasses import dataclass, field


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
