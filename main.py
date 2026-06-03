"""
כלי מיגרציה לסיילספורס — wizard (Streamlit).

הרצה:  streamlit run main.py
"""
import streamlit as st

from config import template_config
from modules import (
    sheets_io, query_builder, field_dictionary, mapper, recent_sheets,
    splitter, dedup_engine, output_writer,
)

st.set_page_config(page_title="כלי מיגרציה לסיילספורס", layout="wide")

# כיוון RTL בסיסי לעברית (כולל כותרות) — אך קוד (SQL) תמיד LTR כדי שלא יוצג הפוך
st.markdown(
    "<style>"
    ".stApp, .stMarkdown, .stTextInput, .stTextArea, .stButton,"
    ' [data-testid="stHeading"], h1, h2, h3, h4 {direction: rtl; text-align: right;}'
    '[data-testid="stCode"], [data-testid="stCode"] * {direction: ltr; text-align: left;}'
    "</style>",
    unsafe_allow_html=True,
)

st.title("כלי מיגרציה לסיילספורס")

# שלושת הגיליונות והרמה הנדרשת לכל אחד
SHEETS = [
    ("template", "עותק הטמפלייט", True),   # צריך כתיבה (Editor)
    ("db", "קובץ DB", False),              # קריאה בלבד (Viewer)
    ("soql", "מיפוי אובייקטים ושדות", False),  # קריאה בלבד (Viewer) — תוצאת שאילתת FieldDefinition
]

_DOT = {"green": "🟢", "yellow": "🟡", "red": "🔴"}

# בחירות מיוחדות ב-dropdown של המיפוי
_OTHER = "אחר (הזן ידנית)"
_UNMAPPED = "—"


@st.cache_data(show_spinner=False)
def _read_cached(link: str, tab: str | None) -> list[list[str]]:
    """
    קריאת ערכי-גיליון עם זיכרון-מטמון: כל עוד לא לחצו 'רענן', אותה (גיליון, לשונית)
    נקראת פעם אחת בלבד — מעבר בין מסכים לא קורא שוב מ-Google (מהיר, חוסך מכסת-API).
    אחרי כתיבה לגיליון יש לרוקן את המטמון (`_read_cached.clear()`) כדי לא להציג נתון ישן.
    """
    return sheets_io.read_values(link, tab=tab)


def _sidebar_controls() -> None:
    """כפתורי 'רענן מהגיליונות' (מרוקן מטמון) ו'התחל מחדש' (מנקה חישובים ובחירות)."""
    st.sidebar.divider()
    if st.sidebar.button("🔄 רענן מהגיליונות"):
        _read_cached.clear()
        st.rerun()
    if st.sidebar.button("♻️ התחל מחדש"):
        _read_cached.clear()
        # מנקה בחירות וחישובים, אך משאיר את החיבורים (קישורי הגיליונות) על כנם
        for k in list(st.session_state.keys()):
            if k.startswith(("mech_", "obj_", "api_", "tiebreak")) or k in (
                "mechanisms",
            ):
                del st.session_state[k]
        st.rerun()


def screen_connection() -> None:
    """שלב 0 — חיבור גיליונות + בניית שאילתת SOQL למילון השדות."""
    st.header("שלב 0 — חיבור + שאילתת מילון")

    # ===== בונה שאילתת SOQL (שלב 1 לשעבר) — מקופל מעל החיבור =====
    with st.expander("בניית שאילתת מילון (FieldDefinition) ל-Inspector", expanded=False):
        st.write(
            "הזן שמות-API של אובייקטים (אחד בכל שורה). הכלי ירכיב שאילתה — העתק "
            "ל-Salesforce Inspector, הרץ, ושמור את התוצאה כגיליון *מיפוי אובייקטים ושדות*, "
            "ואז חבר אותו למטה."
        )
        default_objects = "\n".join(template_config.DEFAULT_OBJECTS)
        raw = st.text_area("אובייקטים", value=default_objects, height=140, key="soql_objects")
        objects = query_builder.clean_object_names(raw)
        if objects:
            st.caption(f"{len(objects)} אובייקטים: {', '.join(objects)}")
            st.code(query_builder.build_field_definition_query(objects), language="sql")
        else:
            st.warning("לא הוזנו אובייקטים — אין שאילתה להציג.")

    st.divider()

    # ===== חיבור שלושת הגיליונות =====
    try:
        sa_email = sheets_io.service_account_email()
        st.write("שתף כל גיליון עם ה-service account, ברמת ההרשאה המתאימה:")
        st.code(sa_email, language=None)
    except Exception as e:  # noqa: BLE001
        st.error(f"שגיאה בטעינת credentials.json — ודא שהקובץ קיים בשורש הפרויקט.\n\n{e}")
        st.stop()

    new_label = "— הדבק קישור חדש —"
    for key, label, needs_write in SHEETS:
        needed = "Editor" if needs_write else "Viewer"
        recents = recent_sheets.recent_for(key)
        options = [r["name"] for r in recents] + [new_label]
        sel = st.selectbox(f"{label}  (נדרש: {needed})", options, key=f"recent_{key}")
        if sel == new_label:
            resolved = st.text_input("הדבק קישור לגיליון", key=f"newlink_{key}")
        else:
            resolved = next((r["id"] for r in recents if r["name"] == sel), "")
        st.session_state[f"link_{key}"] = resolved

    if st.button("בדוק חיבור"):
        st.divider()
        for key, label, needs_write in SHEETS:
            link = st.session_state.get(f"link_{key}", "")
            status = sheets_io.connection_status(link, needs_write)
            suffix = f"  ·  _{status.name}_" if status.name else ""
            st.markdown(f"{_DOT[status.color]} **{label}** — {status.message}{suffix}")
            if status.name:
                recent_sheets.remember(key, sheets_io.extract_id(link), status.name)


# סטטוס → (אייקון, תווית-תיאור). הסדר כאן הוא סדר המקרא.
_STATUS_LABEL = {
    mapper.STATUS_VALID: ("✅", "התאמה"),
    mapper.STATUS_INVALID: ("🔴", "התאמה שגויה"),
    mapper.STATUS_MISSING: ("🟡", "לא נמצאה התאמה"),
    mapper.STATUS_CONTROL: ("🎚️", "בקרה (לא נטען)"),
    mapper.STATUS_NO_DICT: ("⚠️", "האובייקט לא נכלל בשאילתא"),
    mapper.STATUS_IGNORE: ("⚪", "לא רלוונטי"),
}
_STATUS_ICON = {s: icon for s, (icon, _lbl) in _STATUS_LABEL.items()}


def _apply_object_overrides(cols: list[mapper.TemplateColumn]) -> None:
    """מחיל override לאובייקט פר-עמודה מתוך ה-session (תיקון ידני במסך המיפוי)."""
    for c in cols:
        key = f"obj_{c.index}"
        if key in st.session_state:
            val = st.session_state[key]
            if val == _OTHER:
                val = st.session_state.get(f"objother_{c.index}", "").strip()
            elif val == _UNMAPPED:
                val = ""
            c.object_api = val


def _run_mapping_pipeline(template_link: str, soql_link: str):
    """קורא את הגיליונות ומריץ חילוץ→מיפוי→(override)→ולידציה. מחזיר עמודות + אזהרות + מילון."""
    dict_rows = _read_cached(soql_link, None)
    parsed = field_dictionary.parse_field_dictionary(dict_rows, template_config.DEFAULT_OBJECTS)
    tmpl_rows = _read_cached(template_link, template_config.TEMPLATE_TAB)
    cols = mapper.extract_columns(
        tmpl_rows,
        block_row=template_config.TEMPLATE_BLOCK_ROW,
        label_row=template_config.TEMPLATE_LABEL_ROW,
        api_row=template_config.TEMPLATE_API_ROW,
    )
    mapper.assign_objects(cols, template_config.BLOCK_TO_OBJECT, template_config.WANDERING_OVERRIDES)
    _apply_object_overrides(cols)  # תיקוני אובייקט ידניים (session) — לפני הוולידציה
    mapper.validate_columns(cols, parsed.objects, control_columns=template_config.CONTROL_COLUMNS)
    return cols, parsed.warnings, parsed.objects


def _object_selectbox(c: mapper.TemplateColumn, base_objs: list[str]) -> str:
    """dropdown אובייקט לשורה. מחזיר את האובייקט שנבחר (כולל '' ללא-מיפוי / ערך ידני)."""
    opts = [_UNMAPPED] + base_objs + [_OTHER]
    cur = c.object_api
    if cur in base_objs:
        idx = opts.index(cur)
    elif not cur:
        idx = 0
    else:
        idx = opts.index(_OTHER)
    sel = st.selectbox("אובייקט", opts, index=idx, key=f"obj_{c.index}",
                       label_visibility="collapsed")
    if sel == _OTHER:
        default = cur if cur not in base_objs else ""
        return st.text_input("אובייקט (ידני)", value=default, key=f"objother_{c.index}",
                             label_visibility="collapsed").strip()
    if sel == _UNMAPPED:
        return ""
    return sel


def _api_selectbox(c: mapper.TemplateColumn, obj: str, dictionary: dict) -> str:
    """dropdown API לשורה, תלוי באובייקט שנבחר. מחזיר את ה-API שנבחר (או ידני)."""
    disp2api = {f"{f.api} — {f.label}": f.api for f in mapper.candidates_for(obj, dictionary)}
    opts = list(disp2api) + [_OTHER]
    cur = c.clean_api or c.proposed_api
    cur_disp = next((d for d, a in disp2api.items() if a == cur), None)
    if cur_disp:
        idx = opts.index(cur_disp)
    elif cur:
        idx = opts.index(_OTHER)
    else:
        idx = 0 if disp2api else opts.index(_OTHER)
    sel = st.selectbox("API", opts, index=idx, key=f"api_{c.index}", label_visibility="collapsed")
    if sel == _OTHER:
        default = cur if not cur_disp else ""
        return st.text_input("API (ידני)", value=default, key=f"apiother_{c.index}",
                             label_visibility="collapsed").strip()
    return disp2api[sel]


def screen_mapping() -> None:
    """שלבים 2–3 — מיפוי וולידציה עם עריכה inline."""
    st.header("שלבים 2–3 — מיפוי וולידציה")

    template_link = st.session_state.get("link_template", "")
    soql_link = st.session_state.get("link_soql", "")
    if not template_link or not soql_link:
        st.warning("חסר חיבור — חזור לשלב 0 וחבר את *עותק הטמפלייט* ואת *מיפוי אובייקטים ושדות*.")
        return

    try:
        cols, dict_warnings, dictionary = _run_mapping_pipeline(template_link, soql_link)
    except Exception as e:  # noqa: BLE001 — כל כשל מדווח למשתמש, לא מפיל את המסך
        st.error(f"שגיאה בקריאת הגיליונות או בפירוק:\n\n{e}")
        return

    # ===== מקרא נוריות (כל 6, תמיד, עם תיאור + ספירה) =====
    counts: dict[str, int] = {}
    for c in cols:
        counts[c.status] = counts.get(c.status, 0) + 1
    legend = " · ".join(
        f"{icon} {lbl} ({counts.get(s, 0)})" for s, (icon, lbl) in _STATUS_LABEL.items()
    )
    st.markdown(legend)

    for w in dict_warnings:
        st.warning(w)

    st.caption(
        "ערוך כל שורה: בחר אובייקט ו-API מהרשימות (או *אחר* להקלדה). תיקוני אובייקט נשמרים "
        "לסשן; תיקוני API ייכתבו לטמפלייט בלחיצת *נעל ושמור*."
    )

    base_objs = list(dictionary.keys())
    rows = [c for c in cols if c.status != mapper.STATUS_IGNORE]

    # כותרות עמודות (סדר לוגי; תחת RTL מופיע מימין לשמאל)
    widths = [3, 3, 4, 1, 1]
    h = st.columns(widths)
    for col, title in zip(h, ("שם עמודה מהלקוח", "אובייקט", "API", "נורית", "עמ'")):
        col.markdown(f"**{title}**")

    corrections: dict[int, str] = {}
    for c in rows:
        col_name, col_obj, col_api, col_light, col_letter = st.columns(widths)
        col_name.write(c.label or "—")
        with col_obj:
            chosen_obj = _object_selectbox(c, base_objs)
        with col_api:
            chosen_api = _api_selectbox(c, chosen_obj, dictionary)
        col_light.write(_STATUS_ICON.get(c.status, ""))
        col_letter.write(sheets_io.col_letter(c.index))
        if chosen_api and chosen_api != c.clean_api:
            corrections[c.index] = chosen_api

    # שמירת תיקוני API
    st.divider()
    if corrections:
        st.markdown("**ייכתבו לטמפלייט (שורת API):**")
        for idx, api in corrections.items():
            lbl = next(c.label for c in rows if c.index == idx)
            st.markdown(f"- עמ' {sheets_io.col_letter(idx)} · {lbl} → `{api}`")
        if st.button(f"🔒 נעל ושמור {len(corrections)} תיקונים לטמפלייט"):
            try:
                updates = [(template_config.TEMPLATE_API_ROW, idx, api) for idx, api in corrections.items()]
                n = sheets_io.write_cells(template_link, template_config.TEMPLATE_TAB, updates)
                _read_cached.clear()  # המיפוי השתנה בגיליון — לקרוא מחדש בריצה הבאה
                st.success(f"נכתבו {n} תיקונים לטמפלייט.")
            except Exception as e:  # noqa: BLE001
                st.error(f"כשל בכתיבה לטמפלייט: {e}")


_N_MECHANISMS = 3


def screen_identity() -> None:
    """מסך הרכבת מנגנוני-זיהוי (3 מנגנונים מדורגים) — המשתמש בוחר, הכלי מרכיב."""
    st.header("מנגנוני זיהוי")
    st.write(
        "הרכב עד שלושה מנגנונים לזיהוי איש-קשר, לפי עדיפות (1→3). כל מנגנון = צירוף "
        "שדות שצריכים *כולם* להתאים. הראשון שמוצא התאמה מנצח."
    )

    template_link = st.session_state.get("link_template", "")
    soql_link = st.session_state.get("link_soql", "")
    if not template_link or not soql_link:
        st.warning("חסר חיבור — חזור לשלב 0 וחבר את *עותק הטמפלייט* ואת *מיפוי אובייקטים ושדות*.")
        return

    try:
        cols, _warnings, _dictionary = _run_mapping_pipeline(template_link, soql_link)
    except Exception as e:  # noqa: BLE001 — כל כשל מדווח למשתמש, לא מפיל את המסך
        st.error(f"שגיאה בקריאת הגיליונות או בפירוק:\n\n{e}")
        return

    # מאגר השדות = שדות Contact התקפים (✅), מיוחדים לפי API (אותו שדה בשני בלוקי Contact)
    pool: dict[str, str] = {}  # api → תווית-תצוגה (api — label)
    for c in cols:
        if c.object_api == template_config.IDENTITY_OBJECT and c.status == mapper.STATUS_VALID:
            pool.setdefault(c.clean_api, f"{c.clean_api} — {c.label}")
    if not pool:
        st.warning(
            f"אין שדות תקפים לאובייקט {template_config.IDENTITY_OBJECT} — "
            "השלם קודם את המיפוי (מסך *מיפוי*)."
        )
        return

    disp2api = {disp: api for api, disp in pool.items()}
    options = list(disp2api)
    default_api = template_config.DEFAULT_IDENTITY_FIELD
    default_disp = pool.get(default_api)  # למנגנון 1 בלבד, אם קיים במאגר

    mechanisms: list[list[str]] = []
    for n in range(1, _N_MECHANISMS + 1):
        active = st.checkbox(f"מנגנון {n} — פעיל", value=(n == 1), key=f"mech_active_{n}")
        default = [default_disp] if (n == 1 and default_disp) else []
        chosen = st.multiselect(
            f"שדות מנגנון {n} (צירוף AND)",
            options,
            default=default,
            key=f"mech_fields_{n}",
            disabled=not active,
        )
        if active and chosen:
            mechanisms.append([disp2api[d] for d in chosen])

    # תצוגה-מקדימה חיה של הרשימה שתורכב (לפי תוויות, קריא יותר)
    st.divider()
    if mechanisms:
        api2label = {api: lbl.split(" — ", 1)[-1] for api, lbl in pool.items()}
        preview = " · ".join(
            f"מנגנון {i}: " + " + ".join(api2label.get(a, a) for a in mech)
            for i, mech in enumerate(mechanisms, 1)
        )
        st.markdown(f"**יורכב:** {preview}")
    else:
        st.warning("אין מנגנון פעיל עם שדות — בחר לפחות מנגנון אחד.")

    if st.button("שמור מנגנונים"):
        st.session_state["mechanisms"] = mechanisms
        if mechanisms:
            st.success(f"נשמרו {len(mechanisms)} מנגנונים.")
        else:
            st.info("נשמרה רשימה ריקה (אין מנגנון פעיל).")


def screen_db_export() -> None:
    """שלב 4 — שאילתות SELECT לייצוא DB + ולידציה של הגיליון המחובר."""
    st.header("שלב 4 — ייצוא DB")
    st.write(
        "הרץ כל שאילתה ב-Salesforce Inspector, שמור את התוצאה בגיליון ה-DB בלשונית "
        "המוצגת, ואז לחץ *בדוק DB* לאימות."
    )

    template_link = st.session_state.get("link_template", "")
    soql_link = st.session_state.get("link_soql", "")
    if not template_link or not soql_link:
        st.warning("חסר חיבור — חזור לשלב 0 וחבר את *עותק הטמפלייט* ואת *מיפוי אובייקטים ושדות*.")
        return

    try:
        cols, _warnings, _dictionary = _run_mapping_pipeline(template_link, soql_link)
    except Exception as e:  # noqa: BLE001
        st.error(f"שגיאה בקריאת הגיליונות:\n\n{e}")
        return

    # אובייקט → שדות תקפים (ייחוד — שני בלוקי Contact לא כופלים שדות)
    queries: dict[str, list[str]] = {}
    for c in cols:
        if c.status == mapper.STATUS_VALID and c.clean_api:
            fields = queries.setdefault(c.object_api, [])
            if c.clean_api not in fields:
                fields.append(c.clean_api)

    if not queries:
        st.warning("אין עמודות ממופות תקפות — השלם קודם את המיפוי.")
        return

    # ===== סקשן A: שאילתות לייצוא =====
    st.subheader("שאילתות לייצוא ב-Inspector")
    for obj, fields in queries.items():
        tab_name = template_config.DB_TAB_NAMES.get(obj, obj)
        with st.expander(f"**{obj}** — {len(fields)} שדות + Id", expanded=True):
            st.code(query_builder.build_data_query(obj, fields), language="sql")
            st.caption(f"שמור תוצאה ללשונית: **{tab_name}**")

    # ===== סקשן B: ולידציה של גיליון ה-DB =====
    st.divider()
    st.subheader("סטטוס גיליון ה-DB")

    db_link = st.session_state.get("link_db", "")
    if not db_link:
        st.info("גיליון DB אינו מחובר — חזור לשלב 0 וחבר אותו.")
        return

    if st.button("בדוק DB"):
        access = sheets_io.check_access(db_link)
        if not access.ok:
            st.error(f"🔴 שגיאת גישה לגיליון DB: {access.error}")
            return
        st.markdown(f"🟢 **{access.name}** — גישה תקינה")
        for obj in queries:
            tab_name = template_config.DB_TAB_NAMES.get(obj, obj)
            try:
                rows = _read_cached(db_link, tab_name)
            except Exception:  # noqa: BLE001
                st.markdown(f"⚠️ **{obj}** — לשונית *{tab_name}* לא נמצאה")
                continue
            if not rows:
                st.markdown(f"⚠️ **{obj}** — לשונית ריקה (אין נתונים)")
                continue
            header = rows[0]
            record_count = len(rows) - 1
            id_note = "" if "Id" in header else " · ⚠️ עמודת Id חסרה"
            st.markdown(f"✅ **{obj}** — {record_count:,} רשומות{id_note}")


def screen_contacts() -> None:
    """שלב 5 — בניית גריד Contacts מוכן-לטעינה וכתיבתו ללשונית-פלט בטמפלייט."""
    st.header("שלב 5 — בניית אנשי קשר לטעינה")
    st.write(
        "הכלי קורא את אנשי הקשר מהטמפלייט, מאחד כפילויות, ומשווה למאגר כדי לדעת מי "
        "כבר קיים (לעדכון) ומי חדש. רשומות לעדכון מקבלות גם השלמת פרטים חסרים מהמאגר. "
        "התוצאה נכתבת ללשונית מוכנה-לטעינה בתוך הטמפלייט."
    )

    template_link = st.session_state.get("link_template", "")
    soql_link = st.session_state.get("link_soql", "")
    db_link = st.session_state.get("link_db", "")
    mechanisms = st.session_state.get("mechanisms")

    if not template_link or not soql_link or not db_link:
        st.warning("חסר חיבור — חזור לשלב 0 וחבר את *עותק הטמפלייט*, *מיפוי אובייקטים ושדות* ו-*קובץ DB*.")
        return
    if not mechanisms:
        st.warning("לא הוגדרו מנגנוני זיהוי — חזור למסך *מנגנוני זיהוי* ושמור לפחות מנגנון אחד.")
        return

    try:
        cols, _warnings, _dictionary = _run_mapping_pipeline(template_link, soql_link)
        tmpl_rows = _read_cached(template_link, template_config.TEMPLATE_TAB)
        split_records = splitter.split_object(
            "Contact", tmpl_rows, cols,
            data_start_row=template_config.TEMPLATE_DATA_START_ROW,
        )
        record_values = [r.values for r in split_records]

        db_rows = _read_cached(db_link, template_config.DB_TAB_NAMES["Contact"])
        db_records = sheets_io.rows_to_dicts(db_rows)
        db_by_id = {r["Id"]: r for r in db_records if r.get("Id")}

        dedup = dedup_engine.deduplicate(
            record_values, mechanisms, db_records,
            digits_only_fields=template_config.DIGITS_ONLY_FIELDS,
        )
        grid, cell_colors = output_writer.build_contacts_grid(dedup, record_values, cols, db_by_id)
    except Exception as e:  # noqa: BLE001 — כל כשל מדווח למשתמש, לא מפיל את המסך
        st.error(f"שגיאה בהרצת הצינור:\n\n{e}")
        return

    # ===== סיכום-נורות =====
    c = dedup.counts
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("חדשים", c.get("inserts", 0))
    m2.metric("לעדכון", c.get("upserts", 0))
    m3.metric("⚠️ נמצאו כמה התאמות", c.get("ambiguous", 0))
    m4.metric("⚠️ ללא נתוני זיהוי", c.get("unkeyed", 0))
    st.caption(
        f"{len(record_values)} שורות מהטמפלייט → {len(dedup.persons)} אנשים ייחודיים · "
        f"{len(db_records)} רשומות במאגר"
    )

    # ===== תצוגה מקדימה =====
    # שתי שורות-כותרת (עברית מעל API); כותרת התצוגה = העברית, נתונים משורה 2 ואילך.
    if len(grid) > 2:
        st.subheader("תצוגה מקדימה")
        st.dataframe(
            {grid[0][col]: [row[col] for row in grid[2:]] for col in range(len(grid[0]))},
            use_container_width=True,
        )
    else:
        st.info("אין אנשי קשר בטמפלייט עדיין — תיכתבו שורות הכותרות בלבד.")

    # ===== כתיבה =====
    st.divider()
    out_tab = template_config.OUTPUT_TAB_CONTACTS
    st.markdown(f"היעד: לשונית **{out_tab}** בתוך הטמפלייט (כתיבה חוזרת מחליפה את התוכן הקודם).")
    if st.button(f"כתוב {max(len(grid) - 2, 0)} שורות ל-{out_tab}"):
        try:
            sheets_io.ensure_tab(template_link, out_tab)
            n = sheets_io.write_grid(template_link, out_tab, grid)
            sheets_io.set_tab_rtl(template_link, out_tab)
            sheets_io.color_cells(template_link, out_tab, cell_colors)
            _read_cached.clear()  # רוקון מטמון אחרי כתיבה — הקריאה הבאה תביא נתון עדכני
            st.success(f"נכתבו {n} שורות (כולל 2 שורות כותרת) ללשונית {out_tab}.")
        except Exception as e:  # noqa: BLE001
            st.error(f"כשל בכתיבה לטמפלייט: {e}")


SCREENS = {
    "שלב 0 — חיבור + שאילתה": screen_connection,
    "שלבים 2–3 — מיפוי": screen_mapping,
    "מנגנוני זיהוי": screen_identity,
    "שלב 4 — ייצוא DB": screen_db_export,
    "שלב 5 — בניית Contacts": screen_contacts,
}

choice = st.sidebar.radio("שלב", list(SCREENS.keys()))
_sidebar_controls()
SCREENS[choice]()
