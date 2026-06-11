"""
כלי מיגרציה לסיילספורס v2 — wizard (Streamlit).
הרצה: streamlit run main.py
"""
from __future__ import annotations

import streamlit as st

from config.runtime_schema import (
    RuntimeSchema, ObjectDef, ExtraField, ValueMap, ValueMapEntry,
    ROLE_FIELD, ROLE_CONTROL, ROLE_SKIP, ST_OK, ST_CHECK,
)
from modules import (  # noqa: F401 — validator/notes_store used in later slices
    sheets_io, query_builder, field_dictionary, mapper, recent_sheets,
    schema_reader, auto_mapper, validator, notes_store,
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
            freshness = _db_freshness_label(db_id)
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


def _mapping_row(c, m, fields, datatypes, input_rows) -> None:
    """שורת-מיפוי אחת: תווית · בורר-שדה · מקור · סטטוס · דוגמה."""
    col_label, col_field, col_src, col_status, col_prev, col_vm = st.columns(
        [3, 4, 1.2, 1.6, 3, 1]
    )

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

            hdr = st.columns([3, 4, 1.2, 1.6, 3, 1])
            for hcol, title in zip(
                hdr,
                ("עמודה מהלקוח", "שדה Salesforce", "מקור", "סטטוס", "דוגמה → אחרי", "מפה"),
            ):
                hcol.markdown(f"**{title}**")
            for c in obj_cols:
                m = schema.mappings.get(c.index)
                if m is None or (m.role == ROLE_SKIP and not c.label and not c.proposed_api):
                    continue  # עמודת-מפריד — מוצגת ב"עמודות מוסתרות"
                _mapping_row(c, m, fields, datatypes, input_rows)

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
        screen_stub(3, "מנגנוני זיהוי")
    elif step == 4:
        screen_stub(4, "קשרים ו-Lookups")
    elif step == 5:
        screen_stub(5, "בנייה ופלט")


main()
