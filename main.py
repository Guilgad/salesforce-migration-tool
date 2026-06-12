"""
כלי מיגרציה לסיילספורס v2 — wizard (Streamlit).
הרצה: streamlit run main.py
"""
from __future__ import annotations

import streamlit as st

from config.runtime_schema import (
    RuntimeSchema, ObjectDef, ExtraField, IdentityConfig, LookupConfig, JunctionConfig, ValueMap, ValueMapEntry,
    ROLE_FIELD, ROLE_CONTROL, ROLE_SKIP, ST_OK, ST_CHECK,
)
from modules import (  # noqa: F401 — validator/notes_store used in later slices
    sheets_io, query_builder, field_dictionary, mapper, recent_sheets,
    schema_reader, auto_mapper, validator, notes_store, profile_store,
)
from modules.db_freshness import days_since_modified as _db_days, freshness_label as _db_label
from modules.orchestrator import (
    adapt_columns, apply_value_maps, apply_extra_fields,
    convert_id_15_to_18, read_ids_from_output_tab,
    OUTPUT_TAB, OUTPUT_TAB_MANUAL,
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
            try:
                name = sheets_io.get_spreadsheet_meta(sheet_id).get("name", sheet_id)
            except Exception:  # noqa: BLE001 — שם הוא רק לתצוגת "אחרונים"
                name = sheet_id
            recent_sheets.remember(role, sheet_id, name)
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
    if (
        rows_key not in st.session_state
        or st.session_state.get(f"{role}_rows_tab") != selected_tab
    ):
        try:
            rows = sheets_io.read_values(sheet_id, selected_tab)
            st.session_state[rows_key] = rows
            st.session_state[f"{role}_rows_tab"] = selected_tab
            st.success(f"🟢 מחובר · {len(rows)} שורות")
        except Exception as e:
            st.error(f"שגיאת קריאה: {e}")
            return sheet_id, selected_tab, None
    else:
        rows = st.session_state[rows_key]
        st.success(f"🟢 מחובר · {len(rows)} שורות")

    return sheet_id, selected_tab, rows


def _db_freshness_label(sheet_id: str) -> str:
    """Returns freshness label; also caches days in st.session_state['db_freshness_days']."""
    if not sheet_id:
        return ""
    try:
        meta = sheets_io.get_spreadsheet_meta(sheet_id)
        days = _db_days(meta.get("modifiedTime", ""))
        if days is not None:
            st.session_state["db_freshness_days"] = days
            return _db_label(days)
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
                # רשימת-האובייקטים משקפת את הלשונית הנוכחית (מחליפים — לא צוברים)
                keep = {o.api_name: o for o in schema.objects}
                schema.objects = [
                    keep.get(api) or ObjectDef(api_name=api, display_name=api)
                    for api in detected
                ]
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
            freshness = _db_freshness_label(db_id)   # also caches db_freshness_days
            if freshness:
                st.caption(freshness)

    with col_queries:
        st.subheader("שאילתות ל-Inspector")
        _screen_queries()


# ─── step 2: mapping ──────────────────────────────────────────────────────────

_SRC_TAG = {"file": "מהקובץ", "auto": "אוטומטי", "manual": "ידני", "": "—"}
_OPT_NONE = "— בחר שדה —"
_OPT_CONTROL = "🏳️ עמודת בקרה (דגל — לא נטענת כשדה)"
_OPT_SKIP = "⚪ לא רלוונטי (לא נטענת)"


def _field_dict_result():
    """שורות מילון-השדות מהסשן → ParseResult (במטמון כל עוד השורות לא התחלפו)."""
    rows = st.session_state.get("fielddict_rows")
    if not rows:
        return None
    cached = st.session_state.get("_fd_cache")
    if cached is not None and cached[0] is rows:
        return cached[1]
    result = field_dictionary.parse_field_dictionary(rows, schema.fielddict_objects)
    st.session_state["_fd_cache"] = (rows, result)
    return result


def _map_fingerprint(columns, dictionary) -> tuple:
    return (
        tuple((c.index, c.object_api, c.label, c.proposed_api) for c in columns),
        tuple(sorted((api, len(obj.fields)) for api, obj in dictionary.items())),
    )


def _ensure_mappings(columns, dictionary) -> None:
    """מיפוי-אוטומטי פעם אחת; נבנה מחדש רק כשהכותרות או המילון משתנים."""
    fp = _map_fingerprint(columns, dictionary)
    if st.session_state.get("_map_fp") != fp:
        schema.mappings = auto_mapper.build_mappings(columns, dictionary)
        st.session_state["_map_fp"] = fp


def _sample_value(input_rows: list[list[str]], col_index: int) -> str:
    """הערך הלא-ריק הראשון בעמודה (לדוגמה החיה)."""
    for row in input_rows[schema.data_start_row:]:
        if col_index < len(row) and str(row[col_index] or "").strip():
            return str(row[col_index]).strip()
    return ""


def _distinct_values(input_rows: list[list[str]], col_index: int, limit: int = 20) -> list[str]:
    """ערכים ייחודיים (לא-ריקים) בעמודת-דאטה — זריעת מפת-הערכים."""
    seen: set[str] = set()
    out: list[str] = []
    for row in input_rows[schema.data_start_row:]:
        v = (
            str(row[col_index]).strip()
            if col_index < len(row) and row[col_index] is not None else ""
        )
        if v and v not in seen:
            seen.add(v)
            out.append(v)
            if len(out) >= limit:
                break
    return out


def _mapping_row(c, m, fields, datatypes, input_rows, multi: bool = False) -> None:
    """שורת-מיפוי אחת: תווית · בורר-שדה · מקור · סטטוס · דוגמה (· מופע)."""
    widths = [3, 4, 1.2, 1.6, 3, 1] + ([1] if multi else [])
    cols = st.columns(widths)
    col_label, col_field, col_src, col_status, col_prev, col_vm = cols[:6]

    col_label.markdown(f"**{c.label or '—'}**")
    col_label.caption(f"עמ' {sheets_io.col_letter(c.index)}")

    # אפשרויות: מיוחדות → מועמדים → שאר השדות (Label (api))
    by_api = {f.api: f for f in fields}
    ordered = [api for api in m.candidates if api in by_api]
    ordered += [f.api for f in fields if f.api not in ordered]
    labels = {api: f"{by_api[api].label} ({api})" for api in ordered}
    if m.field_api and m.field_api not in labels:
        labels[m.field_api] = f"{m.field_api} (לא במילון)"
        ordered.append(m.field_api)
    options = [_OPT_NONE, _OPT_CONTROL, _OPT_SKIP] + [labels[a] for a in ordered]

    if m.role == ROLE_CONTROL:
        current = _OPT_CONTROL
    elif m.role == ROLE_SKIP:
        current = _OPT_SKIP
    elif m.field_api:
        current = labels[m.field_api]
    else:
        current = _OPT_NONE

    chosen = col_field.selectbox(
        "שדה", options, index=options.index(current),
        key=f"map_{c.index}", label_visibility="collapsed",
    )
    if chosen != current:
        m.source = "manual"
        if chosen == _OPT_CONTROL:
            m.role, m.field_api, m.status = ROLE_CONTROL, "", ST_OK
        elif chosen == _OPT_SKIP:
            m.role, m.field_api, m.status = ROLE_SKIP, "", ST_OK
        elif chosen == _OPT_NONE:
            m.role, m.field_api, m.status = ROLE_FIELD, "", ST_CHECK
        else:
            m.role = ROLE_FIELD
            m.field_api = next(a for a, lbl in labels.items() if lbl == chosen)
            m.status = ST_OK
        st.rerun()

    col_src.caption(_SRC_TAG.get(m.source, "—"))

    if m.role == ROLE_CONTROL:
        col_status.markdown("🏳️ בקרה")
    elif m.role == ROLE_SKIP:
        col_status.markdown("⚪ לא רלוונטי")
    elif m.status == ST_OK:
        col_status.markdown("✅ תקין")
    else:
        col_status.markdown("🟡 בדוק התאמה")

    vm = schema.value_maps.get(c.index)
    sample = _sample_value(input_rows, c.index)
    if sample and m.role == ROLE_FIELD and m.field_api:
        after = auto_mapper.preview_value(sample, datatypes.get(m.field_api, ""), vm)
        if after:
            shown = after
            if vm:
                entry = next((e for e in vm.entries if e.source == sample), None)
                if entry and entry.display:
                    shown = f"{after} ({entry.display})"
            col_prev.caption(f"{sample} → {shown}")
        else:
            col_prev.caption(f"{sample} → ⚠️ לא זוהה")
    elif sample:
        col_prev.caption(sample)

    # מפת-ערכים — חלונית-צפה במקום
    if m.role == ROLE_FIELD:
        with col_vm.popover("🗺️✓" if vm and vm.entries else "🗺️"):
            st.markdown(f"**מפת-ערכים — {c.label}**")
            st.caption("ערך-מקור → ערך-יעד (נטען) → שם (תצוגה בלבד). התאמה מדויקת.")
            seed = (
                [{"מקור": e.source, "יעד (נטען)": e.target, "שם (תצוגה)": e.display}
                 for e in vm.entries]
                if vm and vm.entries
                else [{"מקור": v, "יעד (נטען)": "", "שם (תצוגה)": ""}
                      for v in _distinct_values(input_rows, c.index)]
            )
            edited = st.data_editor(
                seed, num_rows="dynamic", key=f"vm_edit_{c.index}",
                use_container_width=True,
            )
            default = st.text_input(
                "ערך ברירת-מחדל (ריק = ערך-לא-ממופה יסומן כבעיה)",
                value=vm.default if vm else "",
                key=f"vm_def_{c.index}",
            )
            b1, b2 = st.columns(2)
            if b1.button("שמור מפה", key=f"vm_save_{c.index}"):
                entries = [
                    ValueMapEntry(
                        str(r.get("מקור", "")).strip(),
                        str(r.get("יעד (נטען)", "")).strip(),
                        str(r.get("שם (תצוגה)", "")).strip(),
                    )
                    for r in edited if str(r.get("מקור", "")).strip()
                ]
                schema.value_maps[c.index] = ValueMap(
                    entries=entries, default=default.strip()
                )
                st.rerun()
            if vm and vm.entries and b2.button("הסר מפה", key=f"vm_del_{c.index}"):
                schema.value_maps.pop(c.index, None)
                st.rerun()

    if multi and m.role == ROLE_FIELD:
        m.instance = int(cols[6].number_input(
            "מופע", min_value=1, max_value=9, value=m.instance,
            key=f"inst_{c.index}", label_visibility="collapsed",
        ))


def screen_mapping() -> None:
    """שלב 2 — מיפוי עמודות-הלקוח לשדות סיילספורס."""
    input_rows = st.session_state.get("input_rows")
    if not input_rows:
        st.warning("חבר גיליון-קלט בשלב 1 תחילה.")
        return
    fd = _field_dict_result()
    if fd is None:
        st.warning("חבר את גיליון מילון-השדות בשלב 1 תחילה.")
        return
    for w in fd.warnings:
        st.warning(w)
    dictionary = fd.objects
    if schema.table_type == "single" and not schema.single_object_api:
        st.warning("בטבלת אובייקט-יחיד יש להזין שם אובייקט בשלב 1.")
        return

    columns = schema_reader.read_header_columns(input_rows, schema)
    _ensure_mappings(columns, dictionary)

    # סיכום-נוריות + סטטוס לסרגל
    counts = {"ok": 0, "check": 0, "control": 0, "skip": 0}
    for c in columns:
        m = schema.mappings.get(c.index)
        if m is None or not c.object_api or c.object_api not in dictionary:
            continue
        if m.role == ROLE_CONTROL:
            counts["control"] += 1
        elif m.role == ROLE_SKIP:
            counts["skip"] += 1
        elif m.status == ST_OK:
            counts["ok"] += 1
        else:
            counts["check"] += 1
    st.markdown(
        f"✅ תקין ({counts['ok']}) · 🟡 בדוק התאמה ({counts['check']}) · "
        f"🏳️ בקרה ({counts['control']}) · ⚪ לא רלוונטי ({counts['skip']})"
    )
    _set_status(2, "done" if counts["check"] == 0 else "pending")

    obj_names: list[str] = []
    for c in columns:
        if c.object_api and c.object_api not in obj_names:
            obj_names.append(c.object_api)
    if not obj_names:
        st.error("לא זוהו אובייקטים בשורת-האובייקט של הקלט.")
        return

    tab_titles = [o if o in dictionary else f"{o} ⚠️ חסר מילון" for o in obj_names]
    for tab, obj in zip(st.tabs(tab_titles), obj_names):
        with tab:
            if obj not in dictionary:
                st.warning(
                    "האובייקט לא נמצא במילון-השדות — הוסף אותו לשאילתת המילון בשלב 1 והרץ שוב."
                )
            fields = mapper.candidates_for(obj, dictionary)
            datatypes = {f.api: f.datatype for f in fields}
            obj_cols = [c for c in columns if c.object_api == obj]

            multi = st.checkbox(
                "האובייקט מופיע יותר מפעם אחת בשורה (למשל בעל/אישה)",
                value=schema.multi_instance.get(obj, False),
                key=f"multi_{obj}",
            )
            schema.multi_instance[obj] = multi

            titles = ["עמודה מהלקוח", "שדה Salesforce", "מקור", "סטטוס",
                      "דוגמה → אחרי", "מפה"] + (["מופע"] if multi else [])
            hdr = st.columns([3, 4, 1.2, 1.6, 3, 1] + ([1] if multi else []))
            for hcol, title in zip(hdr, titles):
                hcol.markdown(f"**{title}**")
            for c in obj_cols:
                m = schema.mappings.get(c.index)
                if m is None or (m.role == ROLE_SKIP and not c.label and not c.proposed_api):
                    continue  # עמודת-מפריד — מוצגת ב"עמודות מוסתרות"
                _mapping_row(c, m, fields, datatypes, input_rows, multi)

            od = next((o for o in schema.objects if o.api_name == obj), None)
            if od is not None:
                inst = [
                    schema.mappings[c.index].instance
                    for c in obj_cols
                    if c.index in schema.mappings
                    and schema.mappings[c.index].role == ROLE_FIELD
                ]
                od.instance_count = max(inst) if (multi and inst) else 1

            with st.expander("➕ הוסף שדה (ערך קבוע לכל הרשומות)"):
                for i, x in [
                    (i, x) for i, x in enumerate(schema.extra_fields)
                    if x.object_api == obj
                ]:
                    c1, c2 = st.columns([5, 1])
                    c1.markdown(f"`{x.field_api}` = **{x.constant_value or '(ריק)'}**")
                    if c2.button("🗑️", key=f"xf_del_{obj}_{i}"):
                        schema.extra_fields.pop(i)
                        st.rerun()
                if fields:
                    opts = [f"{f.label} ({f.api})" for f in fields]
                    pick = st.selectbox("שדה", [_OPT_NONE] + opts, key=f"xf_pick_{obj}")
                    val = st.text_input("ערך קבוע", key=f"xf_val_{obj}")
                    if st.button("הוסף", key=f"xf_add_{obj}") and pick != _OPT_NONE:
                        api = pick[pick.rfind("(") + 1:-1]
                        schema.extra_fields.append(ExtraField(obj, api, val.strip()))
                        st.rerun()
                else:
                    st.caption("אין מילון לאובייקט זה — חבר מילון-שדות כדי להוסיף.")

    hidden = [
        c for c in columns
        if not c.object_api or (not c.label and not c.proposed_api)
    ]
    if hidden:
        with st.expander(f"⚪ עמודות מוסתרות ({len(hidden)}) — מפרידים/ללא אובייקט"):
            for c in hidden:
                st.markdown(f"- **{sheets_io.col_letter(c.index)}** · {c.label or '*(ריק)*'}")

    # ידני → כתיבה לקובץ-המקור (שורת ה-API). מקור-אמת יחיד, שורד איפוס.
    by_index = {c.index: c for c in columns}
    pending = {
        idx: m.field_api
        for idx, m in schema.mappings.items()
        if m.source == "manual" and m.role == ROLE_FIELD and m.field_api
        and idx in by_index
        and m.field_api != mapper.normalize_api(by_index[idx].proposed_api)
    }
    if pending:
        st.divider()
        st.markdown("**מיפויים ידניים שטרם נשמרו לקובץ-המקור:**")
        for idx, api in sorted(pending.items()):
            st.markdown(
                f"- עמ' {sheets_io.col_letter(idx)} · {by_index[idx].label} → `{api}`"
            )
        if st.button(f"💾 שמור {len(pending)} מיפויים לקובץ-המקור"):
            try:
                updates = [(schema.api_row, idx, api) for idx, api in pending.items()]
                sheets_io.write_cells(schema.input_sheet_id, schema.input_tab, updates)
                # עדכון העותק שבזיכרון — המסך משקף מיד, בלי קריאה חוזרת מ-Google
                rows_mem = st.session_state["input_rows"]
                while len(rows_mem) <= schema.api_row:
                    rows_mem.append([])
                api_row = rows_mem[schema.api_row]
                for idx, api in pending.items():
                    while len(api_row) <= idx:
                        api_row.append("")
                    api_row[idx] = api
                    schema.mappings[idx].source = "file"
                # טביעת-האצבע מתעדכנת כדי שהמיפוי לא ייבנה-מחדש (וישמור עריכות אחרות)
                new_cols = schema_reader.read_header_columns(rows_mem, schema)
                st.session_state["_map_fp"] = _map_fingerprint(new_cols, dictionary)
                st.success("נשמר לקובץ-המקור — יישאר גם אחרי איפוס.")
                st.rerun()
            except Exception as e:  # noqa: BLE001
                st.error(f"כשל בכתיבה לקובץ-המקור: {e}")


# ─── step 3: identity ─────────────────────────────────────────────────────────

_N_MECHANISMS = 5


def screen_identity() -> None:
    """שלב 3 — מנגנוני-זיהוי מדורגים פר-אובייקט + טוגל-dedup + הוסף-אובייקט."""
    fd = _field_dict_result()
    dictionary = fd.objects if fd else {}
    loaded = [o.api_name for o in schema.objects]
    if (
        schema.table_type == "single"
        and schema.single_object_api
        and schema.single_object_api not in loaded
    ):
        loaded = [schema.single_object_api]
    if not loaded and not schema.extra_objects:
        st.warning("חבר גיליון-קלט בשלב 1 ומפה שדות בשלב 2 תחילה.")
        return

    # מאגר-שדות פר-אובייקט: נטען — שדות ממופים משלב 2; זיהוי-בלבד — כל שדות-המילון
    pools: dict[str, list[str]] = {}
    for obj in loaded:
        pool: list[str] = []
        for m in sorted(schema.mappings.values(), key=lambda x: x.col_index):
            if (
                m.object_api == obj and m.role == ROLE_FIELD
                and m.field_api and m.field_api not in pool
            ):
                pool.append(m.field_api)
        pools[obj] = pool
    for obj in schema.extra_objects:
        pools[obj] = [f.api for f in dictionary[obj].fields] if obj in dictionary else []

    all_objs = loaded + [o for o in schema.extra_objects if o not in loaded]
    st.caption(
        "לכל אובייקט: מנגנונים מדורגים לפי עדיפות — כל מנגנון הוא צירוף-שדות (AND). "
        "אותם מנגנונים משמשים גם לזיהוי מול ה-DB וגם ליישוב Lookups."
    )

    done_all = bool(loaded)
    tabs = st.tabs([o if o in loaded else f"{o} 🔍" for o in all_objs])
    for tab, obj in zip(tabs, all_objs):
        with tab:
            cfg = schema.identity.setdefault(obj, IdentityConfig())
            if obj not in loaded:
                st.caption("🔍 זיהוי בלבד — האובייקט לא נטען; משמש ליישוב Lookups.")
            pool = pools.get(obj, [])
            if not pool:
                st.info(
                    "אין שדות זמינים — מפה שדות לאובייקט זה בשלב 2."
                    if obj in loaded else "האובייקט חסר במילון-השדות (שלב 1)."
                )
            cfg.dedup_internal = st.toggle(
                "זיהוי כפילויות פנימיות (איחוד שורות-קלט שחולקות מנגנון)",
                value=cfg.dedup_internal,
                key=f"dedup_{obj}",
                help="כבוי = כל שורה נטענת בנפרד, שום רשומה לא נעלמת.",
            )
            if not cfg.mechanisms:
                cfg.mechanisms.append([])
            n = len(cfg.mechanisms)   # חלק מהמפתח — מחיקה/הוספה מזריעות widgets מחדש
            del_idx = None
            for i, mech in enumerate(cfg.mechanisms):
                c1, c2 = st.columns([8, 1])
                cfg.mechanisms[i] = c1.multiselect(
                    f"מנגנון {i + 1} — צירוף שדות (AND)",
                    options=pool,
                    default=[f for f in mech if f in pool],
                    key=f"mech_{obj}_{n}_{i}",
                )
                if n > 1 and c2.button("🗑️", key=f"mech_del_{obj}_{i}"):
                    del_idx = i
            if del_idx is not None:
                cfg.mechanisms.pop(del_idx)
                st.rerun()
            if n < _N_MECHANISMS and st.button("➕ הוסף מנגנון", key=f"mech_add_{obj}"):
                cfg.mechanisms.append([])
                st.rerun()
            active = [m for m in cfg.mechanisms if m]
            if active:
                st.caption("סדר-עדיפות: " + " ← ".join("+".join(m) for m in active))
            elif obj in loaded:
                st.caption("ללא מנגנון — כל השורות ייטענו כחדשות (Insert), ללא הצלבה מול ה-DB.")
            if obj in loaded and not active:
                done_all = False

    with st.expander("➕ הוסף אובייקט (זיהוי בלבד — יעד Lookup שלא נטען)"):
        avail = [o for o in dictionary if o not in all_objs]
        if avail:
            pick = st.selectbox("אובייקט מהמילון", avail, key="extra_obj_pick")
            if st.button("הוסף", key="extra_obj_add"):
                schema.extra_objects.append(pick)
                st.rerun()
        else:
            st.caption("אין אובייקטים נוספים במילון-השדות.")
        for i, o in enumerate(schema.extra_objects):
            c1, c2 = st.columns([5, 1])
            c1.markdown(f"🔍 {o}")
            if c2.button("🗑️", key=f"extra_obj_del_{i}"):
                schema.extra_objects.pop(i)
                schema.identity.pop(o, None)
                st.rerun()

    _set_status(3, "done" if done_all else "pending")


def _load_order(schema: "RuntimeSchema") -> list[list[str]]:
    """Topological sort of objects (including junction objects) by dependencies.
    Returns list of tiers; each tier is a list of object api_names."""
    loaded_objs = [o.api_name for o in schema.objects]
    junction_objs = [jc.junction_object for jc in schema.junctions]
    all_objs = loaded_objs + [o for o in junction_objs if o not in loaded_objs]

    deps: dict[str, set[str]] = {o: set() for o in all_objs}

    # Lookup edges: source depends on target
    for lc in schema.lookups:
        if lc.source_object in deps and lc.target_object in all_objs:
            deps[lc.source_object].add(lc.target_object)

    # Junction edges: junction_object depends on both parents
    for jc in schema.junctions:
        jobj = jc.junction_object
        if jobj not in deps:
            deps[jobj] = set()
        if jc.object_a in all_objs:
            deps[jobj].add(jc.object_a)
        if jc.object_b in all_objs:
            deps[jobj].add(jc.object_b)

    tiers: list[list[str]] = []
    remaining = set(all_objs)
    placed: set[str] = set()
    while remaining:
        tier = sorted(o for o in remaining if deps[o] <= placed)
        if not tier:  # cycle guard
            tier = sorted(remaining)
        tiers.append(tier)
        placed |= set(tier)
        remaining -= set(tier)
    return tiers


def _lookup_col_label(schema: "RuntimeSchema", lc: "LookupConfig") -> str:
    cm = schema.mappings.get(lc.source_col_index)
    if cm:
        return cm.field_api or f"עמודה {lc.source_col_index}"
    return f"עמודה {lc.source_col_index}"


def screen_lookups() -> None:
    schema: RuntimeSchema = st.session_state.get("schema", RuntimeSchema())
    _set_status(4, "pending")

    st.subheader("קשרי Lookup")
    st.caption("עמודה שערכה צריך להתרגם ל-Id של אובייקט אחר (למשל AccountId).")

    # ── Existing lookups ──────────────────────────────────────────────────────
    for i, lc in enumerate(schema.lookups):
        col_label = _lookup_col_label(schema, lc)
        with st.container(border=True):
            c1, c2 = st.columns([8, 1])
            c1.markdown(
                f"**{lc.source_object}** · {col_label} → **{lc.target_object}** `{lc.target_field}`  \n"
                f"זוהה לפי: {', '.join(lc.identified_by) or '—'}"
            )
            if c2.button("🗑️", key=f"del_lookup_{i}"):
                schema.lookups.pop(i)
                st.rerun()

    # ── Add Lookup ────────────────────────────────────────────────────────────
    all_obj_apis = [o.api_name for o in schema.objects]
    all_obj_labels = {o.api_name: o.display_name for o in schema.objects}
    target_apis = all_obj_apis + [o.api_name for o in schema.extra_objects]
    target_labels = {**all_obj_labels, **{o.api_name: o.display_name for o in schema.extra_objects}}

    with st.expander("➕ הוסף Lookup"):
        src_obj = st.selectbox(
            "אובייקט מקור",
            options=all_obj_apis,
            format_func=lambda a: all_obj_labels.get(a, a),
            key="lkp_src_obj",
        )
        src_cols = [
            (idx, cm)
            for idx, cm in schema.mappings.items()
            if cm.object_api == src_obj and cm.role == ROLE_FIELD
        ]
        src_col_opts = [idx for idx, _ in src_cols]
        src_col_labels = {idx: cm.field_api or f"עמודה {idx}" for idx, cm in src_cols}

        src_col = st.selectbox(
            "עמודת מקור (הערך הגולמי)",
            options=src_col_opts,
            format_func=lambda i: src_col_labels.get(i, str(i)),
            key="lkp_src_col",
        ) if src_col_opts else None

        tgt_obj = st.selectbox(
            "אובייקט יעד",
            options=target_apis,
            format_func=lambda a: target_labels.get(a, a),
            key="lkp_tgt_obj",
        )
        tgt_field = st.text_input(
            "שדה יעד על האובייקט המקור (למשל AccountId)",
            key="lkp_tgt_field",
        )
        tgt_identity = schema.identity.get(tgt_obj, IdentityConfig())
        default_mech = tgt_identity.mechanisms[0] if tgt_identity.mechanisms else []
        identified_by = st.multiselect(
            "זוהה לפי (שדות הזיהוי של היעד)",
            options=default_mech or ["Name"],
            default=default_mech,
            key="lkp_id_by",
        )

        if st.button("הוסף", key="lkp_add") and src_col is not None and tgt_field.strip():
            schema.lookups.append(
                LookupConfig(
                    source_object=src_obj,
                    source_col_index=src_col,
                    target_object=tgt_obj,
                    target_field=tgt_field.strip(),
                    identified_by=identified_by,
                )
            )
            st.rerun()

    st.divider()

    # ── Load order ────────────────────────────────────────────────────────────
    st.subheader("סדר טעינה")
    tiers = _load_order(schema)
    if not tiers:
        st.info("אין אובייקטים לטעינה.")
    else:
        for i, tier in enumerate(tiers, 1):
            tier_labels = ", ".join(all_obj_labels.get(o, o) for o in tier)
            st.markdown(f"**{i}.** {tier_labels}")

    st.divider()

    # ── Junctions ─────────────────────────────────────────────────────────────
    st.subheader("קשרי Junction")
    st.caption("קשר בין שני אובייקטים דרך אובייקט-ביניים (למשל CampaignMember, npe4__Relationship__c).")

    for i, jc in enumerate(schema.junctions):
        with st.container(border=True):
            c1, c2 = st.columns([8, 1])
            c1.markdown(
                f"**{jc.object_a}** + **{jc.object_b}** → **{jc.junction_object}**  \n"
                f"Id A: `{jc.id_field_a}` · Id B: `{jc.id_field_b}`"
                + (f"  \nבקרה: עמודה {jc.control_col_index}" if jc.control_col_index is not None else "")
                + ("  \n🔄 סימטרי" if jc.symmetric else "")
            )
            if c2.button("🗑️", key=f"del_junction_{i}"):
                schema.junctions.pop(i)
                st.rerun()

    with st.expander("➕ הוסף Junction"):
        all_junction_obj_apis = [o.api_name for o in schema.objects]
        all_junction_obj_labels = {o.api_name: o.display_name for o in schema.objects}

        if not all_junction_obj_apis:
            st.info("אין אובייקטים — חבר קלט ומפה שדות קודם.")
        else:
            jnc_obj_a = st.selectbox(
                "אובייקט A",
                options=all_junction_obj_apis,
                format_func=lambda a: all_junction_obj_labels.get(a, a),
                key="jnc_obj_a",
            )
            jnc_block_a = st.text_input(
                "שם הבלוק של A (מהשורה הראשונה בטמפלייט)",
                value=all_junction_obj_labels.get(jnc_obj_a, jnc_obj_a),
                key="jnc_block_a",
            )
            jnc_obj_b = st.selectbox(
                "אובייקט B",
                options=all_junction_obj_apis,
                format_func=lambda a: all_junction_obj_labels.get(a, a),
                key="jnc_obj_b",
            )
            jnc_block_b = st.text_input(
                "שם הבלוק של B (מהשורה הראשונה בטמפלייט)",
                value=all_junction_obj_labels.get(jnc_obj_b, jnc_obj_b),
                key="jnc_block_b",
            )
            jnc_junction_obj = st.text_input(
                "אובייקט Junction (API name, למשל CampaignMember)",
                key="jnc_junction_obj",
            )
            jnc_id_a = st.text_input(
                "שדה Id של A על Junction (למשל ContactId)",
                key="jnc_id_a",
            )
            jnc_id_b = st.text_input(
                "שדה Id של B על Junction (למשל CampaignId)",
                key="jnc_id_b",
            )
            jnc_symmetric = st.checkbox(
                "סימטרי (NPSP — מונע כפילויות דו-כיווניות)",
                key="jnc_symmetric",
            )
            jnc_has_control = st.checkbox(
                "עמודת בקרה (צור רק כש=TRUE)",
                key="jnc_has_control",
            )
            jnc_ctrl_col = None
            if jnc_has_control:
                ctrl_col_opts = [
                    (idx, cm) for idx, cm in schema.mappings.items()
                    if cm.role == ROLE_CONTROL
                ]
                if ctrl_col_opts:
                    jnc_ctrl_col = st.selectbox(
                        "עמודת בקרה",
                        options=[idx for idx, _ in ctrl_col_opts],
                        format_func=lambda i: schema.mappings[i].field_api or f"עמודה {i}",
                        key="jnc_ctrl_col",
                    )
                else:
                    st.info("אין עמודות בקרה — מפה עמודה עם תפקיד 'בקרה' בשלב 2.")

            can_add = (
                jnc_junction_obj.strip()
                and jnc_id_a.strip()
                and jnc_id_b.strip()
                and jnc_block_a.strip()
                and jnc_block_b.strip()
            )
            if st.button("הוסף Junction", key="jnc_add", disabled=not can_add):
                schema.junctions.append(JunctionConfig(
                    object_a=jnc_obj_a,
                    block_a=jnc_block_a.strip(),
                    object_b=jnc_obj_b,
                    block_b=jnc_block_b.strip(),
                    junction_object=jnc_junction_obj.strip(),
                    id_field_a=jnc_id_a.strip(),
                    id_field_b=jnc_id_b.strip(),
                    control_col_index=jnc_ctrl_col,
                    symmetric=jnc_symmetric,
                ))
                st.rerun()

    _set_status(4, "done" if (schema.lookups or schema.junctions) else "pending")


# ─── step 5: build & output ───────────────────────────────────────────────────


def _cached_read(sheet_id: str, tab: str) -> list:
    """Session-state cached wrapper for sheets_io.read_values."""
    cache_key = f"_read_cache_{sheet_id}_{tab}"
    if cache_key not in st.session_state:
        st.session_state[cache_key] = sheets_io.read_values(sheet_id, tab)
    return st.session_state[cache_key]


def _clear_read_cache() -> None:
    """Invalidate all _cached_read entries after a write."""
    for k in list(st.session_state.keys()):
        if k.startswith("_read_cache_"):
            del st.session_state[k]


def _render_junction_card(schema, jc, obj_labels: dict) -> None:
    from modules.junction_builder import derive_junctions, build_junction_grid, db_junction_pairs_from_records
    from modules.splitter import split_object
    from modules.dedup_engine import deduplicate
    from modules.sheets_io import rows_to_dicts, ensure_tab, write_grid
    from config.runtime_schema import IdentityConfig

    label = jc.junction_object
    id_map_a = st.session_state.get(f"id_map_{jc.object_a}", {})
    id_map_b = st.session_state.get(f"id_map_{jc.object_b}", {})

    missing_parents = []
    if not id_map_a:
        missing_parents.append(obj_labels.get(jc.object_a, jc.object_a))
    if not id_map_b:
        missing_parents.append(obj_labels.get(jc.object_b, jc.object_b))

    with st.container(border=True):
        if missing_parents:
            st.markdown(f"🔒 **{label}** — ממתין ל-Ids של: {', '.join(missing_parents)}")
            st.caption("טען את ההורים ל-Salesforce, הדבק Ids (לחץ 'קלוט Ids' בכל הורה), ואז חזור לבנות.")
            return

        st.markdown(f"**{label}** (`{jc.junction_object}`)")
        built = st.session_state.get(f"build_junction_{jc.junction_object}")
        if built:
            st.caption(f"נוצרו: **{built.get('created', 0)}** · קיימים ב-DB: **{built.get('exists', 0)}** · אזהרות: **{built.get('warnings', 0)}**")

        if st.button("בנה Junction", key=f"build_junction_btn_{jc.junction_object}"):
            with st.spinner(f"בונה {jc.junction_object}…"):
                rows = _cached_read(schema.input_sheet_id, schema.input_tab)
                columns_a = adapt_columns(schema, jc.object_a, rows)
                records_a = split_object(jc.object_a, rows, columns_a, data_start_row=schema.data_start_row)
                records_a = apply_value_maps(records_a, schema)
                records_a = apply_extra_fields(records_a, schema, jc.object_a)
                record_dicts_a = [r.values for r in records_a]
                id_cfg_a = schema.identity.get(jc.object_a, IdentityConfig())
                db_tab_a = schema.db_tabs.get(jc.object_a, "")
                db_rows_a = _cached_read(schema.db_sheet_id, db_tab_a) if db_tab_a else []
                db_recs_a = rows_to_dicts(db_rows_a)
                dedup_a = deduplicate(
                    record_dicts_a, id_cfg_a.mechanisms or [], db_recs_a,
                    digits_only_fields=schema.digits_only_fields,
                    local_key_prefix=jc.object_a[:1].upper(),
                    dedup_internal=id_cfg_a.dedup_internal,
                )

                columns_b = adapt_columns(schema, jc.object_b, rows)
                records_b = split_object(jc.object_b, rows, columns_b, data_start_row=schema.data_start_row)
                records_b = apply_value_maps(records_b, schema)
                records_b = apply_extra_fields(records_b, schema, jc.object_b)
                record_dicts_b = [r.values for r in records_b]
                id_cfg_b = schema.identity.get(jc.object_b, IdentityConfig())
                db_tab_b = schema.db_tabs.get(jc.object_b, "")
                db_rows_b = _cached_read(schema.db_sheet_id, db_tab_b) if db_tab_b else []
                db_recs_b = rows_to_dicts(db_rows_b)
                dedup_b = deduplicate(
                    record_dicts_b, id_cfg_b.mechanisms or [], db_recs_b,
                    digits_only_fields=schema.digits_only_fields,
                    local_key_prefix=jc.object_b[:1].upper(),
                    dedup_internal=id_cfg_b.dedup_internal,
                )

                jnc_tab = schema.db_tabs.get(jc.junction_object, "")
                jnc_db_rows = _cached_read(schema.db_sheet_id, jnc_tab) if jnc_tab else []
                jnc_db_recs = rows_to_dicts(jnc_db_rows)
                db_pairs = db_junction_pairs_from_records(jnc_db_recs, jc)

                junction_records = derive_junctions(
                    rows, columns_a,
                    records_a, dedup_a,
                    records_b, dedup_b,
                    id_map_a, id_map_b,
                    db_pairs,
                    config=jc,
                    data_start_row=schema.data_start_row,
                )

                grid, cell_colors = build_junction_grid(junction_records, jc)
                grid = _apply_id_conversion_to_grid(grid)
                ensure_tab(schema.input_sheet_id, OUTPUT_TAB(jc.junction_object))
                write_grid(schema.input_sheet_id, OUTPUT_TAB(jc.junction_object), grid)

                n_created = sum(1 for r in junction_records if not r.exists_in_db and not r.warning)
                n_exists = sum(1 for r in junction_records if r.exists_in_db)
                n_warnings = sum(1 for r in junction_records if r.warning)
                st.session_state[f"build_junction_{jc.junction_object}"] = {
                    "created": n_created, "exists": n_exists, "warnings": n_warnings,
                }
                _clear_read_cache()

                if n_warnings:
                    st.warning(f"⚠️ {n_warnings} אזהרות — ייתכן שחלק מה-Ids חסרים.")
                st.success(f"✅ {jc.junction_object} נכתב ל-{OUTPUT_TAB(jc.junction_object)}")
                st.rerun()


def _render_manual_panel(schema, obj: str, build_result) -> None:
    from modules.output_writer import parse_manual_choices, build_contacts_grid, build_manual_grid
    from modules.sheets_io import rows_to_dicts, write_grid, ensure_tab
    from modules.splitter import split_object
    from modules.dedup_engine import deduplicate
    from config.runtime_schema import IdentityConfig

    with st.expander(f"⚠️ טיפול ידני — {build_result.counts.get('ambiguous', 0)} ריבוי-התאמות"):
        st.caption(f"פתח את לשונית «{OUTPUT_TAB_MANUAL(obj)}» בגיליון, סמן ✓ לכל שורת-מקור, ואז לחץ 'קלוט בחירות'.")
        if st.button("קלוט בחירות ידניות", key=f"manual_apply_{obj}"):
            manual_rows = _cached_read(schema.input_sheet_id, OUTPUT_TAB_MANUAL(obj))
            manual_choices, warnings = parse_manual_choices(manual_rows)
            for w in warnings:
                st.warning(w)
            if not manual_choices:
                st.warning("לא נמצאו בחירות (✓). סמן שורה בלשונית הידנית קודם.")
                return

            rows = _cached_read(schema.input_sheet_id, schema.input_tab)
            columns = adapt_columns(schema, obj, rows)
            records = split_object(obj, rows, columns, schema.data_start_row)
            records = apply_value_maps(records, schema)
            records = apply_extra_fields(records, schema, obj)
            record_dicts = [r.values for r in records]
            source_rows = [r.source_row for r in records]

            db_tab = schema.db_tabs.get(obj, "")
            db_rows = _cached_read(schema.db_sheet_id, db_tab) if db_tab else []
            db_recs = rows_to_dicts(db_rows)
            db_by_id = {r["Id"]: r for r in db_recs if r.get("Id")}
            id_cfg = schema.identity.get(obj, IdentityConfig())
            mechanisms = id_cfg.mechanisms or []

            result = deduplicate(
                record_dicts, mechanisms, db_recs,
                digits_only_fields=schema.digits_only_fields,
                local_key_prefix=obj[:1].upper(),
                dedup_internal=id_cfg.dedup_internal,
            )

            grid, cell_colors = build_contacts_grid(
                result, record_dicts, columns, db_by_id,
                object_api=obj,
                manual_choices=manual_choices,
            )
            grid = _apply_id_conversion_to_grid(grid)

            ensure_tab(schema.input_sheet_id, OUTPUT_TAB(obj))
            write_grid(schema.input_sheet_id, OUTPUT_TAB(obj), grid)

            manual_grid, manual_colors = build_manual_grid(
                result, record_dicts, columns, db_by_id, source_rows,
                object_api=obj,
                marked=manual_choices,
                digits_only_fields=schema.digits_only_fields,
            )
            ensure_tab(schema.input_sheet_id, OUTPUT_TAB_MANUAL(obj))
            write_grid(schema.input_sheet_id, OUTPUT_TAB_MANUAL(obj), manual_grid)

            st.session_state[f"build_{obj}"] = result
            _clear_read_cache()
            st.success("✅ בחירות קולטו — גריד הפלט עודכן.")
            st.rerun()


def _render_unkeyed_panel(schema, obj: str, build_result) -> None:
    n = build_result.counts.get("unkeyed", 0)
    with st.expander(f"⬜ ללא-זיהוי — {n} רשומות"):
        total = len(build_result.persons) if hasattr(build_result, "persons") else 1
        if total > 0 and n > total * 0.5:
            st.error(f"⚠️ {n} מתוך {total} רשומות ללא-זיהוי — ייתכן ששדה-מפתח לא מופה.")
        st.caption("רשומות אלה אין להם מפתח-זיהוי. ניתן להוסיף מנגנון זיהוי או לטעון כחדשות.")
        c1, c2 = st.columns(2)
        if c1.button("🔧 הוסף מנגנון זיהוי", key=f"unkeyed_goto_identity_{obj}"):
            st.session_state["step"] = 3
            st.rerun()
        if c2.button("📥 טען כחדשות (Insert)", key=f"unkeyed_insert_{obj}"):
            st.info("רשומות ללא-זיהוי יטענו כ-Insert. לחץ 'בנה' שוב לעדכון הגריד.")


def _render_paste_back(schema, obj: str) -> None:
    with st.expander("📋 הכנס Ids שחזרו מהטעינה"):
        st.caption(
            "1. טען את הלשונית ב-Salesforce Inspector  \n"
            "2. Inspector יוסיף עמודת `Id`  \n"
            "3. לחץ 'קלוט Ids' — junctions ישוחררו"
        )
        if st.button("קלוט Ids שחזרו", key=f"paste_back_{obj}"):
            out_rows = _cached_read(schema.input_sheet_id, OUTPUT_TAB(obj))
            id_map = read_ids_from_output_tab(out_rows)
            if not id_map:
                st.warning(f"לא נמצאה עמודת Id בלשונית «{OUTPUT_TAB(obj)}». ודא שטענת דרך Inspector.")
            else:
                st.session_state[f"id_map_{obj}"] = id_map
                st.success(f"✅ קולטו {len(id_map)} Ids עבור {obj}.")
                _clear_read_cache()
                st.rerun()


def _apply_id_conversion_to_grid(grid: list) -> list:
    """Convert any 15-char alphanumeric cell values to 18-char Salesforce Ids."""
    result = []
    for row in grid:
        result.append([
            convert_id_15_to_18(cell)
            if isinstance(cell, str) and len(cell) == 15 and cell.isalnum()
            else cell
            for cell in row
        ])
    return result


def _run_build_pipeline(schema: "RuntimeSchema", obj: str) -> None:
    from modules.splitter import split_object
    from modules.dedup_engine import deduplicate
    from modules.output_writer import build_contacts_grid, build_manual_grid

    with st.spinner(f"בונה {obj}…"):
        rows = _cached_read(schema.input_sheet_id, schema.input_tab)
        columns = adapt_columns(schema, obj, rows)
        records = split_object(obj, rows, columns, data_start_row=schema.data_start_row)
        records = apply_value_maps(records, schema)
        records = apply_extra_fields(records, schema, obj)

        # Convert SplitRecord list → list[dict] for dedup engine
        record_dicts = [r.values for r in records]
        source_rows = [r.source_row for r in records]

        db_tab = schema.db_tabs.get(obj, "")
        db_rows = _cached_read(schema.db_sheet_id, db_tab) if db_tab else []
        db_recs = sheets_io.rows_to_dicts(db_rows)
        # Build {Id: dict} index required by output_writer
        db_by_id = {r["Id"]: r for r in db_recs if r.get("Id")}

        id_cfg = schema.identity.get(obj, IdentityConfig())
        mechanisms = id_cfg.mechanisms or []

        result = deduplicate(
            record_dicts, mechanisms, db_recs,
            digits_only_fields=schema.digits_only_fields,
            local_key_prefix=obj[:1].upper(),
            dedup_internal=id_cfg.dedup_internal,
        )

        grid, cell_colors = build_contacts_grid(
            result, record_dicts, columns, db_by_id,
            object_api=obj,
        )
        grid = _apply_id_conversion_to_grid(grid)

        gsheet = schema.input_sheet_id
        sheets_io.ensure_tab(gsheet, OUTPUT_TAB(obj))
        sheets_io.write_grid(gsheet, OUTPUT_TAB(obj), grid)

        if result.counts.get("ambiguous", 0) or result.counts.get("unkeyed", 0):
            manual_grid, manual_colors = build_manual_grid(
                result, record_dicts, columns, db_by_id, source_rows,
                object_api=obj,
            )
            sheets_io.ensure_tab(gsheet, OUTPUT_TAB_MANUAL(obj))
            sheets_io.write_grid(gsheet, OUTPUT_TAB_MANUAL(obj), manual_grid)

        st.session_state[f"build_{obj}"] = result
        _clear_read_cache()

        # Validate output grid (dates + Id lengths)
        from modules.validator import validate_output_grid
        field_dict = st.session_state.get("field_dict", {})
        issues, _marks = validate_output_grid(grid, obj, field_dict)
        st.session_state[f"validate_{obj}"] = issues
        st.session_state[f"loaded_{obj}"] = True

    st.success(f"✅ {obj} נכתב ל-{OUTPUT_TAB(obj)}")
    st.info("טענת ל-Salesforce — ה-DB לא משקף עוד את המצב האמיתי. רענן לפני הפעם הבאה.")
    st.rerun()


def _render_object_card(schema: "RuntimeSchema", obj: str, order: int, obj_labels: dict) -> None:
    label = obj_labels.get(obj, obj)
    build_result = st.session_state.get(f"build_{obj}")
    status_icon = "✅" if build_result else "⬜"

    with st.container(border=True):
        col_title, col_btn = st.columns([7, 2])
        col_title.markdown(f"**{order}. {label}** (`{obj}`) {status_icon}")

        if col_btn.button("בנה", key=f"build_btn_{obj}"):
            _run_build_pipeline(schema, obj)

        if build_result:
            c = build_result.counts
            st.caption(
                f"חדשים: **{c.get('inserts', 0)}** · "
                f"קיימים: **{c.get('upserts', 0)}** · "
                f"ריבוי: **{c.get('ambiguous', 0)}** · "
                f"ללא-זיהוי: **{c.get('unkeyed', 0)}**"
            )
            if c.get("ambiguous", 0) > 0:
                _render_manual_panel(schema, obj, build_result)
            if c.get("unkeyed", 0) > 0:
                _render_unkeyed_panel(schema, obj, build_result)
            _render_paste_back(schema, obj)

        validation = st.session_state.get(f"validate_{obj}")
        if validation is not None:
            n = len(validation)
            if n == 0:
                st.success("✅ ולידציה תקינה (תאריכים · Id)")
            else:
                if st.button(f"⚠️ {n} בעיות", key=f"val_chip_{obj}"):
                    st.session_state[f"show_issues_{obj}"] = not st.session_state.get(
                        f"show_issues_{obj}", False
                    )
                if st.session_state.get(f"show_issues_{obj}"):
                    for issue in validation:
                        st.error(f"{issue.label} {issue.location}: {issue.message}")


def screen_build() -> None:
    schema: RuntimeSchema = st.session_state["schema"]
    tiers = _load_order(schema)
    junction_apis = {jc.junction_object for jc in schema.junctions}
    all_obj_labels = {o.api_name: o.display_name for o in schema.objects}

    db_age = st.session_state.get("db_freshness_days")
    if db_age is not None and db_age > 7:
        st.warning(
            f"⚠️ גיליון ה-DB עודכן לפני {db_age} ימים — "
            "החלטות insert/upsert מסתמכות עליו. מומלץ לרענן."
        )

    if not tiers:
        st.info("אין אובייקטים לבנייה — חבר קלט ומפה שדות קודם.")
        return

    st.subheader("בנייה ופלט")
    st.caption("בנה כל אובייקט לפי סדר הטעינה. junctions ממתינים ל-Ids של ההורים.")

    tier_num = 0
    for tier in tiers:
        for obj in tier:
            if obj in junction_apis:
                continue
            tier_num += 1
            _render_object_card(schema, obj, tier_num, all_obj_labels)

    if schema.junctions:
        st.divider()
        st.markdown("**קשרי Junction**")
        for jc in schema.junctions:
            _render_junction_card(schema, jc, all_obj_labels)

    built = [o for o in all_obj_labels if st.session_state.get(f"build_{o}")]
    if built:
        _set_status(5, "done")


def screen_stub(step: int, label: str) -> None:
    st.info(f"שלב {step} ({label}) — בפרוסה הבאה")


# ─── main router ──────────────────────────────────────────────────────────────

def main() -> None:
    _topbar()
    step = st.session_state["step"]
    if step == 1:
        screen_step1()
    elif step == 2:
        screen_mapping()
    elif step == 3:
        screen_identity()
    elif step == 4:
        screen_lookups()
    elif step == 5:
        screen_build()


main()
