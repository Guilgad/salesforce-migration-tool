"""
כלי מיגרציה לסיילספורס v2 — wizard (Streamlit).
הרצה: streamlit run main.py
"""
from __future__ import annotations

import streamlit as st

from config.runtime_schema import RuntimeSchema, ObjectDef  # noqa: F401 — ObjectDef used in Task 4
from modules import (  # noqa: F401 — all used in Tasks 4–7
    sheets_io, query_builder, field_dictionary, mapper, recent_sheets,
    schema_reader, validator, notes_store,
)

st.set_page_config(
    page_title="כלי מיגרציה לסיילספורס v2",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown(
    "<style>"
    ".stApp, .stMarkdown, .stTextInput, .stTextArea, .stButton, .stSelectbox,"
    ' [data-testid="stHeading"], h1, h2, h3, h4 {direction: rtl; text-align: right;}'
    '[data-testid="stCode"], [data-testid="stCode"] * {direction: ltr; text-align: left;}'
    " .st-key-query_editor textarea {direction: ltr; text-align: left;}"
    ' [data-testid="stSidebar"] {min-width: 240px; max-width: 260px;}'
    ' [data-testid="stAppDeployButton"] {display: none;}'
    ' [data-testid="stSidebarCollapseButton"] {display: none;}'
    ' [data-testid="stHeader"] {display: none;}'
    " .block-container {padding-top: 1rem;}"
    # top-bar card styles
    " .v2-card {border-radius:6px; padding:10px 14px; cursor:pointer;"
    "  font-size:0.82rem; line-height:1.35; min-height:64px;"
    "  display:flex; flex-direction:column; justify-content:center;}"
    " .v2-card-done {background:#1a6b3c; color:#fff;}"
    " .v2-card-current {background:#fff; color:#1a1a1a;"
    "  border-top:3px solid #0068b2; box-shadow:0 1px 4px rgba(0,0,0,.15);}"
    " .v2-card-pending {background:#e8e8e8; color:#555;}"
    " .v2-card-error {background:#b30000; color:#fff;}"
    "</style>",
    unsafe_allow_html=True,
)

# ─── session state ────────────────────────────────────────────────────────────
if "schema" not in st.session_state:
    st.session_state["schema"] = RuntimeSchema()
if "step" not in st.session_state:
    st.session_state["step"] = 1
if "step_status" not in st.session_state:
    st.session_state["step_status"] = {}   # {step_num: "done"|"error"|"pending"}

schema: RuntimeSchema = st.session_state["schema"]

# ─── step definitions ─────────────────────────────────────────────────────────
STEPS = [
    (1, "חיבור + שאילתות"),
    (2, "מיפוי"),
    (3, "מנגנוני זיהוי"),
    (4, "קשרים ו-Lookups"),
    (5, "בנייה ופלט"),
]

_CARD_COLORS = {
    "done":    "v2-card-done",
    "error":   "v2-card-error",
    "current": "v2-card-current",
    "pending": "v2-card-pending",
}


def _set_status(step: int, status: str) -> None:
    """Set step status: 'done' | 'error' | 'pending'."""
    st.session_state["step_status"][step] = status


def _get_status(step: int) -> str:
    return st.session_state["step_status"].get(step, "pending")


def _status_icon(status: str) -> str:
    return {"done": "🟢", "error": "🔴", "pending": "⬜", "current": "🔵"}.get(status, "⬜")


def _topbar() -> None:
    """Sticky top navigation bar — 5 colored cards."""
    current = st.session_state["step"]
    cols = st.columns(5, gap="small")
    for col, (num, label) in zip(cols, STEPS):
        status = _get_status(num)
        css_class = "current" if num == current else status
        icon = _status_icon(css_class)
        if col.button(
            f"{icon} {num}. {label}",
            key=f"nav_{num}",
            use_container_width=True,
        ):
            st.session_state["step"] = num
            st.rerun()
    st.divider()


# ─── screens ──────────────────────────────────────────────────────────────────


def _screen_queries() -> None:
    """Query builder — right column of step 1."""
    fd_label = "מילון שדות (FieldDefinition)"
    query_options: list[str] = [fd_label] + [
        f"ייצוא DB — {o.api_name}" for o in schema.objects
    ]

    if len(query_options) == 1 and not schema.objects:
        st.info("חבר גיליון-קלט כדי לראות שאילתות.")
        return

    selected = st.selectbox("בחר שאילתה", query_options, key="query_pick")

    generated = ""
    if selected == fd_label:
        all_objects = [o.api_name for o in schema.objects]
        default_sel = schema.fielddict_objects or all_objects
        chosen_objs = st.multiselect(
            "אובייקטים לכלול",
            options=all_objects,
            default=[o for o in default_sel if o in all_objects],
            key="fd_obj_select",
        )
        schema.fielddict_objects = chosen_objs
        if not chosen_objs:
            st.warning("בחר לפחות אובייקט אחד.")
        generated = query_builder.build_field_definition_query(chosen_objs)
    elif selected.startswith("ייצוא DB — "):
        obj_api = selected[len("ייצוא DB — "):]
        st.caption(f"💡 שמור תוצאה ללשונית: **{obj_api}** בגיליון ה-DB")
        generated = query_builder.build_data_query(obj_api, [])

    seed_key = (selected, generated)
    if st.session_state.get("_query_seed") != seed_key:
        st.session_state["query_editor"] = generated
        st.session_state["_query_seed"] = seed_key

    st.text_area("שאילתה (ניתנת לעריכה)", key="query_editor", height=200)

    if st.button("📋 העתק", key="copy_query"):
        query_text = st.session_state.get("query_editor", "")
        escaped = query_text.replace("\\", "\\\\").replace("`", "\\`")
        st.markdown(
            f"<script>navigator.clipboard.writeText(`{escaped}`)</script>",
            unsafe_allow_html=True,
        )
        st.success("הועתק ללוח!")


def _parse_sheet_id(raw: str) -> str:
    """Extract Google Sheets ID from URL or return as-is if it looks like an ID."""
    if not raw:
        return ""
    import re
    m = re.search(r"/spreadsheets/d/([A-Za-z0-9_-]+)", raw)
    if m:
        return m.group(1)
    if "/" not in raw and len(raw) > 20:
        return raw
    return raw


def _sheet_connector(
    role: str,
    label: str,
    *,
    needs_write: bool = False,
) -> tuple[str, str, list[list[str]] | None]:
    """
    Renders a sheet connector widget (URL input + tab selector).
    Returns (sheet_id, selected_tab, rows_or_None).
    Persists sheet_id and tab choice to session state under keys:
      f"{role}_sheet_id", f"{role}_tab".
    """
    sid_key = f"{role}_sheet_id"
    tab_key = f"{role}_tab"

    st.markdown(f"**{label}**" + (" ✍️" if needs_write else ""))
    col_url, col_btn = st.columns([5, 1])

    raw_url = col_url.text_input(
        "קישור / מזהה גיליון",
        value=st.session_state.get(sid_key, ""),
        key=f"{role}_url_input",
        label_visibility="collapsed",
        placeholder="הדבק URL של Google Sheets...",
    )
    sheet_id = _parse_sheet_id(raw_url.strip())

    if col_btn.button("🔄", key=f"{role}_refresh"):
        for k in [f"{role}_tabs", f"{role}_rows"]:
            st.session_state.pop(k, None)

    if not sheet_id:
        return "", "", None

    st.session_state[sid_key] = sheet_id

    if f"{role}_tabs" not in st.session_state:
        try:
            tabs = sheets_io.list_tabs(sheet_id)
            st.session_state[f"{role}_tabs"] = tabs
            recent_sheets.save_recent(role, sheet_id)
        except Exception as e:
            st.error(f"שגיאה בחיבור: {e}")
            return sheet_id, "", None
    else:
        tabs = st.session_state[f"{role}_tabs"]

    if not tabs:
        st.warning("הגיליון ריק מלשוניות.")
        return sheet_id, "", None

    default_tab = st.session_state.get(tab_key, tabs[0])
    selected_tab = st.selectbox(
        "לשונית",
        tabs,
        index=tabs.index(default_tab) if default_tab in tabs else 0,
        key=f"{role}_tab_select",
    )
    st.session_state[tab_key] = selected_tab

    rows_key = f"{role}_rows"
    if rows_key not in st.session_state:
        try:
            rows = sheets_io.read_sheet(sheet_id, selected_tab)
            st.session_state[rows_key] = rows
            st.success(f"🟢 מחובר · {len(rows)} שורות")
        except Exception as e:
            st.error(f"שגיאת קריאה: {e}")
            return sheet_id, selected_tab, None
    else:
        rows = st.session_state[rows_key]
        st.success(f"🟢 מחובר · {len(rows)} שורות")

    return sheet_id, selected_tab, rows


def _db_freshness_label(sheet_id: str) -> str:
    """Returns a freshness string like '⚠️ עודכן לפני 8 ימים' or '🟢 עודכן היום'."""
    if not sheet_id:
        return ""
    try:
        meta = sheets_io.get_spreadsheet_meta(sheet_id)
        from datetime import datetime, timezone
        modified = meta.get("modifiedTime", "")
        if modified:
            dt = datetime.fromisoformat(modified.replace("Z", "+00:00"))
            days = (datetime.now(timezone.utc) - dt).days
            if days == 0:
                return "🟢 עודכן היום"
            elif days <= 3:
                return f"🟡 עודכן לפני {days} ימים"
            else:
                return f"⚠️ עודכן לפני {days} ימים — מומלץ לרענן"
    except Exception:
        pass
    return ""


def screen_step1() -> None:
    """Step 1: Connect 3 sheets + queries."""
    col_connect, col_queries = st.columns([1, 1], gap="large")

    with col_connect:
        st.subheader("חיבור גיליונות")

        st.markdown("---")
        st.markdown("#### 📄 גיליון קלט")
        input_id, input_tab, input_rows = _sheet_connector(
            "input", "גיליון הנתונים של הלקוח", needs_write=False
        )

        if input_rows:
            tt = st.radio(
                "סוג הטבלה",
                ["טבלה מרובת אובייקטים", "טבלת אובייקט יחיד"],
                index=0 if schema.table_type == "multi" else 1,
                horizontal=True,
                key="table_type_radio",
            )
            schema.table_type = "multi" if tt.startswith("טבלה מרו") else "single"

            if schema.table_type == "single":
                single_obj = st.text_input(
                    "שם אובייקט SF (API)",
                    value=schema.single_object_api,
                    key="single_obj_input",
                    placeholder="לדוגמה: Contact",
                )
                schema.single_object_api = single_obj.strip()

            schema.input_sheet_id = input_id
            schema.input_tab = input_tab

            if schema.table_type == "multi":
                detected = schema_reader.detect_objects(
                    input_rows, object_row=schema.object_row
                )
                existing_apis = {o.api_name for o in schema.objects}
                for api in detected:
                    if api not in existing_apis:
                        schema.objects.append(ObjectDef(api_name=api, display_name=api))
                if detected:
                    st.caption(f"אובייקטים שזוהו: {' · '.join(detected)}")

        st.markdown("---")
        st.markdown("#### 📚 מילון שדות (FieldDefinition)")
        fd_id, fd_tab, _ = _sheet_connector("fielddict", "גיליון תוצאות שאילתת FieldDefinition")
        if fd_id:
            schema.fielddict_sheet_id = fd_id
            schema.fielddict_tab = fd_tab

        st.markdown("---")
        st.markdown("#### 🗄️ ייצוא DB")
        db_id, _, _ = _sheet_connector("db", "גיליון ייצוא הנתונים הקיימים מ-Salesforce")
        if db_id:
            schema.db_sheet_id = db_id
            freshness = _db_freshness_label(db_id)
            if freshness:
                st.caption(freshness)

    with col_queries:
        st.subheader("שאילתות ל-Inspector")
        _screen_queries()


def screen_stub(step: int, label: str) -> None:
    st.info(f"שלב {step} ({label}) — בפרוסה הבאה")


# ─── main router ──────────────────────────────────────────────────────────────

def main() -> None:
    _topbar()
    step = st.session_state["step"]
    if step == 1:
        screen_step1()
    elif step == 2:
        screen_stub(2, "מיפוי")
    elif step == 3:
        screen_stub(3, "מנגנוני זיהוי")
    elif step == 4:
        screen_stub(4, "קשרים ו-Lookups")
    elif step == 5:
        screen_stub(5, "בנייה ופלט")


main()
