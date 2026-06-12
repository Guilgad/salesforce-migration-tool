"""
פרופיל-טבלה: שמירה וטעינה של RuntimeSchema לקובץ JSON מקומי.
כל פרופיל = קובץ נפרד בתיקיית .profiles/ ב-PROJECT_ROOT.
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

from config import settings
from config.runtime_schema import (
    RuntimeSchema, ObjectDef, ColumnMapping, ValueMap, ValueMapEntry,
    IdentityConfig, LookupConfig, JunctionConfig, ExtraField,
    ROLE_FIELD, ST_CHECK,
)

_PROFILES_DIR: Path = settings.PROFILES_DIR


def _ensure_dir() -> None:
    _PROFILES_DIR.mkdir(parents=True, exist_ok=True)


def _slug(name: str) -> str:
    safe = re.sub(r"[^\wא-ת\-]", "_", name)
    return f"{safe}_{int(time.time() * 1000)}"   # ms-level — no collision


# ── serialisation ─────────────────────────────────────────────────────────────

def schema_to_dict(schema: RuntimeSchema) -> dict:
    """Convert RuntimeSchema to a plain JSON-serialisable dict."""
    return {
        "input_sheet_id":     schema.input_sheet_id,
        "input_tab":          schema.input_tab,
        "table_type":         schema.table_type,
        "single_object_api":  schema.single_object_api,
        "object_row":         schema.object_row,
        "label_row":          schema.label_row,
        "api_row":            schema.api_row,
        "data_start_row":     schema.data_start_row,
        "fielddict_sheet_id": schema.fielddict_sheet_id,
        "fielddict_tab":      schema.fielddict_tab,
        "fielddict_objects":  schema.fielddict_objects,
        "db_sheet_id":        schema.db_sheet_id,
        "db_tabs":            schema.db_tabs,
        "objects": [
            {"api_name": o.api_name, "display_name": o.display_name, "instance_count": o.instance_count}
            for o in schema.objects
        ],
        # int keys → str keys in JSON (restored on load)
        "mappings": {
            str(k): {
                "col_index":  v.col_index,
                "object_api": v.object_api,
                "field_api":  v.field_api,
                "role":       v.role,
                "source":     v.source,
                "status":     v.status,
                "instance":   v.instance,
                "candidates": v.candidates,
            }
            for k, v in schema.mappings.items()
        },
        "value_maps": {
            str(k): {
                "entries": [
                    {"source": e.source, "target": e.target, "display": e.display}
                    for e in v.entries
                ],
                "default": v.default,
            }
            for k, v in schema.value_maps.items()
        },
        "extra_fields": [
            {"object_api": ef.object_api, "field_api": ef.field_api, "constant_value": ef.constant_value}
            for ef in schema.extra_fields
        ],
        "multi_instance": schema.multi_instance,
        "identity": {
            k: {"mechanisms": v.mechanisms, "dedup_internal": v.dedup_internal}
            for k, v in schema.identity.items()
        },
        "extra_objects": schema.extra_objects,
        "lookups": [
            {
                "source_object":    lc.source_object,
                "source_col_index": lc.source_col_index,
                "target_object":    lc.target_object,
                "target_field":     lc.target_field,
                "identified_by":    lc.identified_by,
            }
            for lc in schema.lookups
        ],
        "junctions": [
            {
                "object_a":          jc.object_a,
                "block_a":           jc.block_a,
                "object_b":          jc.object_b,
                "block_b":           jc.block_b,
                "junction_object":   jc.junction_object,
                "id_field_a":        jc.id_field_a,
                "id_field_b":        jc.id_field_b,
                "control_col_index": jc.control_col_index,
                # tuples → lists (JSON); deserialiser converts back
                "field_mappings": [[f, i] for f, i in jc.field_mappings],
                "symmetric":         jc.symmetric,
            }
            for jc in schema.junctions
        ],
        # set not JSON-serialisable → sorted list
        "digits_only_fields": sorted(schema.digits_only_fields),
    }


def schema_from_dict(d: dict) -> RuntimeSchema:
    """Reconstruct RuntimeSchema from a plain dict (loaded from JSON)."""
    s = RuntimeSchema()
    s.input_sheet_id     = d.get("input_sheet_id", "")
    s.input_tab          = d.get("input_tab", "")
    s.table_type         = d.get("table_type", "multi")
    s.single_object_api  = d.get("single_object_api", "")
    s.object_row         = int(d.get("object_row", 0))
    s.label_row          = int(d.get("label_row", 1))
    s.api_row            = int(d.get("api_row", 2))
    s.data_start_row     = int(d.get("data_start_row", 3))
    s.fielddict_sheet_id = d.get("fielddict_sheet_id", "")
    s.fielddict_tab      = d.get("fielddict_tab", "")
    s.fielddict_objects  = list(d.get("fielddict_objects", []))
    s.db_sheet_id        = d.get("db_sheet_id", "")
    s.db_tabs            = dict(d.get("db_tabs", {}))
    s.objects = [
        ObjectDef(
            api_name=o["api_name"],
            display_name=o.get("display_name", o["api_name"]),
            instance_count=int(o.get("instance_count", 1)),
        )
        for o in d.get("objects", [])
    ]
    s.mappings = {
        int(k): ColumnMapping(
            col_index=int(v["col_index"]),
            object_api=v.get("object_api", ""),
            field_api=v.get("field_api", ""),
            role=v.get("role", ROLE_FIELD),
            source=v.get("source", ""),
            status=v.get("status", ST_CHECK),
            instance=int(v.get("instance", 1)),
            candidates=list(v.get("candidates", [])),
        )
        for k, v in d.get("mappings", {}).items()
    }
    s.value_maps = {
        int(k): ValueMap(
            entries=[
                ValueMapEntry(source=e["source"], target=e["target"], display=e.get("display", ""))
                for e in v.get("entries", [])
            ],
            default=v.get("default", ""),
        )
        for k, v in d.get("value_maps", {}).items()
    }
    s.extra_fields = [
        ExtraField(
            object_api=ef["object_api"],
            field_api=ef["field_api"],
            constant_value=ef.get("constant_value", ""),
        )
        for ef in d.get("extra_fields", [])
    ]
    s.multi_instance = dict(d.get("multi_instance", {}))
    s.identity = {
        k: IdentityConfig(
            mechanisms=list(v.get("mechanisms", [])),
            dedup_internal=bool(v.get("dedup_internal", False)),
        )
        for k, v in d.get("identity", {}).items()
    }
    s.extra_objects = list(d.get("extra_objects", []))
    s.lookups = [
        LookupConfig(
            source_object=lc["source_object"],
            source_col_index=int(lc["source_col_index"]),
            target_object=lc["target_object"],
            target_field=lc["target_field"],
            identified_by=list(lc.get("identified_by", [])),
        )
        for lc in d.get("lookups", [])
    ]
    s.junctions = [
        JunctionConfig(
            object_a=jc["object_a"],
            block_a=jc.get("block_a", ""),
            object_b=jc["object_b"],
            block_b=jc.get("block_b", ""),
            junction_object=jc["junction_object"],
            id_field_a=jc["id_field_a"],
            id_field_b=jc["id_field_b"],
            control_col_index=jc.get("control_col_index"),
            # JSON list-of-lists → list-of-tuples
            field_mappings=[(item[0], int(item[1])) for item in jc.get("field_mappings", [])],
            symmetric=bool(jc.get("symmetric", False)),
        )
        for jc in d.get("junctions", [])
    ]
    s.digits_only_fields = set(d.get("digits_only_fields", []))
    return s


# ── public API ────────────────────────────────────────────────────────────────

def save_profile(name: str, schema: RuntimeSchema, column_labels: list[str]) -> Path:
    """Save a named profile. Returns the file path written."""
    if not name.strip():
        raise ValueError("שם פרופיל לא יכול להיות ריק.")
    _ensure_dir()
    path = _PROFILES_DIR / f"{_slug(name.strip())}.json"
    payload = {
        "name":          name.strip(),
        "ts":            time.time(),
        "column_labels": list(column_labels),
        "schema":        schema_to_dict(schema),
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return path


def load_profile(path: Path) -> tuple[str, RuntimeSchema, list[str]]:
    """Load a profile file → (name, RuntimeSchema, column_labels)."""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return (
        data.get("name", path.stem),
        schema_from_dict(data.get("schema", {})),
        list(data.get("column_labels", [])),
    )


def list_profiles() -> list[dict]:
    """All saved profiles, newest first. Each entry: {name, ts, path, column_labels}."""
    if not _PROFILES_DIR.exists():
        return []
    result = []
    for p in _PROFILES_DIR.glob("*.json"):
        try:
            with open(p, encoding="utf-8") as f:
                data = json.load(f)
            result.append({
                "name":          data.get("name", p.stem),
                "ts":            float(data.get("ts", 0)),
                "path":          p,
                "column_labels": list(data.get("column_labels", [])),
            })
        except (json.JSONDecodeError, OSError):
            continue
    result.sort(key=lambda x: x["ts"], reverse=True)
    return result


def delete_profile(path: Path) -> None:
    """Delete a profile file silently if missing."""
    try:
        path.unlink()
    except FileNotFoundError:
        pass


def match_score(profile_labels: list[str], input_labels: list[str]) -> int:
    """
    Count how many profile column labels appear in the input label set.
    Both sides are stripped. Returns 0 if either list is empty.
    """
    if not profile_labels or not input_labels:
        return 0
    input_set = {s.strip() for s in input_labels}
    return sum(1 for lbl in profile_labels if lbl.strip() in input_set)
