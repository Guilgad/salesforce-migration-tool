"""
כלי מיגרציה לסיילספורס — wizard (Streamlit).

ניווט מינימלי בין שלבים (רדיו בצד) — הניווט/הנעילות המלאים יבואו בסבב נפרד.
הרצה:  streamlit run main.py
"""
import streamlit as st

from config import template_config
from modules import sheets_io, query_builder, field_dictionary, mapper, recent_sheets

st.set_page_config(page_title="כלי מיגרציה לסיילספורס", layout="centered")

# כיוון RTL בסיסי לעברית — אך קוד (SQL) תמיד LTR כדי שלא יוצג הפוך
st.markdown(
    "<style>"
    ".stApp, .stMarkdown, .stTextInput, .stTextArea, .stButton {direction: rtl; text-align: right;}"
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


def screen_connection() -> None:
    """שלב 0 — מסך חיבור: כתובת ה-service account + נורית גישה לכל גיליון."""
    st.header("שלב 0 — חיבור גיליונות")

    try:
        sa_email = sheets_io.service_account_email()
        st.write("שתף כל גיליון עם ה-service account, ברמת ההרשאה המתאימה:")
        st.code(sa_email, language=None)
    except Exception as e:  # noqa: BLE001
        st.error(f"שגיאה בטעינת credentials.json — ודא שהקובץ קיים בשורש הפרויקט.\n\n{e}")
        st.stop()

    st.divider()
    new_label = "— הדבק קישור חדש —"
    for key, label, needs_write in SHEETS:
        needed = "Editor" if needs_write else "Viewer"
        recents = recent_sheets.recent_for(key)
        # רשימת אחרונים (לפי שם, אחרון-ראשון) + אפשרות קישור חדש בסוף
        options = [r["name"] for r in recents] + [new_label]
        sel = st.selectbox(f"{label}  (נדרש: {needed})", options, key=f"recent_{key}")
        if sel == new_label:
            resolved = st.text_input("הדבק קישור לגיליון", key=f"newlink_{key}")
        else:
            resolved = next((r["id"] for r in recents if r["name"] == sel), "")
        # הקישור שנבחר זמין לשאר השלבים
        st.session_state[f"link_{key}"] = resolved

    if st.button("בדוק חיבור"):
        st.divider()
        for key, label, needs_write in SHEETS:
            link = st.session_state.get(f"link_{key}", "")
            status = sheets_io.connection_status(link, needs_write)
            suffix = f"  ·  _{status.name}_" if status.name else ""
            st.markdown(f"{_DOT[status.color]} **{label}** — {status.message}{suffix}")
            # חיבור שנפתח בהצלחה → נשמר לזיכרון האחרונים
            if status.name:
                recent_sheets.remember(key, sheets_io.extract_id(link), status.name)


def screen_soql() -> None:
    """שלב 1 — בניית שאילתת SOQL למילון השדות (FieldDefinition)."""
    st.header("שלב 1 — בניית שאילתת SOQL")
    st.write(
        "הזן שמות-API של אובייקטים (אחד בכל שורה). הכלי ירכיב שאילתת "
        "`FieldDefinition` — העתק אותה ל-Salesforce Inspector, הרץ, "
        "ושמור את התוצאה כגיליון *מיפוי אובייקטים ושדות*."
    )

    default_objects = "\n".join(template_config.DEFAULT_OBJECTS)
    raw = st.text_area("אובייקטים", value=default_objects, height=160, key="soql_objects")

    objects = query_builder.clean_object_names(raw)
    if not objects:
        st.warning("לא הוזנו אובייקטים — אין שאילתה להציג.")
        return

    query = query_builder.build_field_definition_query(objects)
    st.caption(f"{len(objects)} אובייקטים: {', '.join(objects)}")
    st.code(query, language="sql")


_STATUS_ICON = {
    mapper.STATUS_VALID: "✅",
    mapper.STATUS_INVALID: "🔴",
    mapper.STATUS_MISSING: "🟡",
    mapper.STATUS_CONTROL: "🎚️",
    mapper.STATUS_IGNORE: "⚪",
    mapper.STATUS_NO_DICT: "⚠️",
}


def _run_mapping_pipeline(template_link: str, soql_link: str) -> list[mapper.TemplateColumn]:
    """קורא את הגיליונות ומריץ חילוץ→מיפוי→ולידציה. מחזיר עמודות מסווגות."""
    dict_rows = sheets_io.read_values(soql_link)
    parsed = field_dictionary.parse_field_dictionary(dict_rows, template_config.DEFAULT_OBJECTS)
    tmpl_rows = sheets_io.read_values(template_link, tab=template_config.TEMPLATE_TAB)
    cols = mapper.extract_columns(
        tmpl_rows,
        block_row=template_config.TEMPLATE_BLOCK_ROW,
        label_row=template_config.TEMPLATE_LABEL_ROW,
        api_row=template_config.TEMPLATE_API_ROW,
    )
    mapper.assign_objects(cols, template_config.BLOCK_TO_OBJECT, template_config.WANDERING_OVERRIDES)
    mapper.validate_columns(cols, parsed.objects, control_columns=template_config.CONTROL_COLUMNS)
    return cols, parsed.warnings, parsed.objects


def screen_mapping() -> None:
    """שלבים 2–3 — תצוגת מיפוי וולידציה (קריאה בלבד)."""
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

    # סיכום נורות
    counts: dict[str, int] = {}
    for c in cols:
        counts[c.status] = counts.get(c.status, 0) + 1
    summary = " · ".join(
        f"{_STATUS_ICON[s]} {counts[s]}"
        for s in (mapper.STATUS_VALID, mapper.STATUS_INVALID, mapper.STATUS_MISSING,
                  mapper.STATUS_CONTROL, mapper.STATUS_NO_DICT, mapper.STATUS_IGNORE)
        if counts.get(s)
    )
    st.markdown(f"**סיכום:** {summary}")

    for w in dict_warnings:
        st.warning(w)

    # ===== עריכה: תיקון 🔴 שגוי / 🟡 חסר =====
    needs = [c for c in cols if c.status in (mapper.STATUS_INVALID, mapper.STATUS_MISSING)]
    if needs:
        st.subheader("תיקון מיפוי")
        st.caption(
            "בחר לכל עמודה את שדה ה-API הנכון. השינויים ייכתבו לשורת ה-API שבטמפלייט "
            "(רק התאים שתיקנת). אם השדה התקין חסר מהרשימה — בחר *אחר* והקלד אותו."
        )
        no_change, other = "(ללא שינוי)", "אחר (הקלד ידנית)"
        corrections: dict[int, str] = {}
        for c in needs:
            disp2api = {f"{f.api} — {f.label}": f.api for f in mapper.candidates_for(c.object_api, dictionary)}
            options = [no_change] + list(disp2api) + [other]
            sel = st.selectbox(
                f"{_STATUS_ICON[c.status]} עמ' {c.index} · {c.label} ({c.object_api}) — כעת: {c.proposed_api or '—'}",
                options,
                key=f"fix_{c.index}",
            )
            chosen = ""
            if sel == other:
                chosen = st.text_input("שם API", key=f"fixother_{c.index}").strip()
            elif sel != no_change:
                chosen = disp2api[sel]
            if chosen and chosen != c.clean_api:
                corrections[c.index] = chosen

        if corrections:
            st.markdown("**ייכתבו לטמפלייט (שורת API):**")
            for idx, api in corrections.items():
                lbl = next(c.label for c in needs if c.index == idx)
                st.markdown(f"- עמ' {idx} · {lbl} → `{api}`")
            if st.button(f"🔒 נעל ושמור {len(corrections)} תיקונים לטמפלייט"):
                try:
                    updates = [(template_config.TEMPLATE_API_ROW, idx, api) for idx, api in corrections.items()]
                    n = sheets_io.write_cells(template_link, template_config.TEMPLATE_TAB, updates)
                    st.success(f"נכתבו {n} תיקונים לטמפלייט. לחץ *בדוק חיבור* או רענן כדי לראות נורות מעודכנות.")
                except Exception as e:  # noqa: BLE001
                    st.error(f"כשל בכתיבה לטמפלייט: {e}")

    # טבלת כל העמודות (ללא מפרידים/תיאור)
    table = [
        {
            "נורית": _STATUS_ICON[c.status],
            "#": c.index,
            "תווית": c.label,
            "אובייקט": c.object_api,
            "API": c.clean_api or c.proposed_api,
        }
        for c in cols
        if c.status != mapper.STATUS_IGNORE
    ]
    st.dataframe(table, hide_index=True, use_container_width=True)


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


SCREENS = {
    "שלב 0 — חיבור": screen_connection,
    "שלב 1 — SOQL": screen_soql,
    "שלבים 2–3 — מיפוי": screen_mapping,
    "מנגנוני זיהוי": screen_identity,
}

choice = st.sidebar.radio("שלב", list(SCREENS.keys()))
SCREENS[choice]()
