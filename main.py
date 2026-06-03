"""
כלי מיגרציה לסיילספורס — wizard (Streamlit).

ניווט מינימלי בין שלבים (רדיו בצד) — הניווט/הנעילות המלאים יבואו בסבב נפרד.
הרצה:  streamlit run main.py
"""
import streamlit as st

from config import template_config
from modules import sheets_io, query_builder, field_dictionary, mapper

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
    ("soql", "תוצאת SOQL", False),         # קריאה בלבד (Viewer)
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
    for key, label, needs_write in SHEETS:
        needed = "Editor" if needs_write else "Viewer"
        st.text_input(f"{label}  (נדרש: {needed}) — קישור", key=f"link_{key}")

    if st.button("בדוק חיבור"):
        st.divider()
        for key, label, needs_write in SHEETS:
            link = st.session_state.get(f"link_{key}", "")
            status = sheets_io.connection_status(link, needs_write)
            suffix = f"  ·  _{status.name}_" if status.name else ""
            st.markdown(f"{_DOT[status.color]} **{label}** — {status.message}{suffix}")


def screen_soql() -> None:
    """שלב 1 — בניית שאילתת SOQL למילון השדות (FieldDefinition)."""
    st.header("שלב 1 — בניית שאילתת SOQL")
    st.write(
        "הזן שמות-API של אובייקטים (אחד בכל שורה). הכלי ירכיב שאילתת "
        "`FieldDefinition` — העתק אותה ל-Salesforce Inspector, הרץ, "
        "ושמור את התוצאה כגיליון *תוצאת SOQL*."
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
    return cols, parsed.warnings


def screen_mapping() -> None:
    """שלבים 2–3 — תצוגת מיפוי וולידציה (קריאה בלבד)."""
    st.header("שלבים 2–3 — מיפוי וולידציה")

    template_link = st.session_state.get("link_template", "")
    soql_link = st.session_state.get("link_soql", "")
    if not template_link or not soql_link:
        st.warning("חסר חיבור — חזור לשלב 0 וחבר את *עותק הטמפלייט* ואת *תוצאת SOQL*.")
        return

    try:
        cols, dict_warnings = _run_mapping_pipeline(template_link, soql_link)
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

    # דורש תשומת לב: 🔴 שגוי / 🟡 חסר
    needs = [c for c in cols if c.status in (mapper.STATUS_INVALID, mapper.STATUS_MISSING)]
    if needs:
        st.caption("דורש תשומת לב (יתוקן בפרוסת העריכה):")
        for c in needs:
            st.markdown(f"- {_STATUS_ICON[c.status]} **{c.label}** ({c.object_api}) — `{c.proposed_api or '—'}`")

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
    st.caption("תצוגה בלבד. תיקון 🔴/🟡 ונעילה — בפרוסה הבאה.")


SCREENS = {
    "שלב 0 — חיבור": screen_connection,
    "שלב 1 — SOQL": screen_soql,
    "שלבים 2–3 — מיפוי": screen_mapping,
}

choice = st.sidebar.radio("שלב", list(SCREENS.keys()))
SCREENS[choice]()
