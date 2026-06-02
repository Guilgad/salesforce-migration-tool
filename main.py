"""
כלי מיגרציה לסיילספורס — wizard (Streamlit).

ניווט מינימלי בין שלבים (רדיו בצד) — הניווט/הנעילות המלאים יבואו בסבב נפרד.
הרצה:  streamlit run main.py
"""
import streamlit as st

from config import template_config
from modules import sheets_io, query_builder

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


SCREENS = {
    "שלב 0 — חיבור": screen_connection,
    "שלב 1 — SOQL": screen_soql,
}

choice = st.sidebar.radio("שלב", list(SCREENS.keys()))
SCREENS[choice]()
