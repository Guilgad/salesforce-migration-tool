"""
כלי מיגרציה לסיילספורס — wizard (Streamlit).

שלב 0: מסך חיבור. מציג את כתובת ה-service account, מקבל 3 קישורי גיליונות,
ובודק לכל אחד את רמת הגישה בפועל (נורית 🟢/🟡/🔴).
הרצה:  streamlit run main.py
"""
import streamlit as st

from modules import sheets_io

st.set_page_config(page_title="כלי מיגרציה לסיילספורס", layout="centered")

# כיוון RTL בסיסי לעברית
st.markdown(
    "<style>.stApp, .stMarkdown, .stTextInput, .stButton {direction: rtl; text-align: right;}</style>",
    unsafe_allow_html=True,
)

st.title("כלי מיגרציה לסיילספורס")
st.header("שלב 0 — חיבור גיליונות")

# כתובת ה-service account לשיתוף
try:
    sa_email = sheets_io.service_account_email()
    st.write("שתף כל גיליון עם ה-service account, ברמת ההרשאה המתאימה:")
    st.code(sa_email, language=None)
except Exception as e:  # noqa: BLE001
    st.error(f"שגיאה בטעינת credentials.json — ודא שהקובץ קיים בשורש הפרויקט.\n\n{e}")
    st.stop()

# הגדרת שלושת הגיליונות והרמה הנדרשת לכל אחד
SHEETS = [
    ("template", "עותק הטמפלייט", True),   # צריך כתיבה (Editor)
    ("db", "קובץ DB", False),              # קריאה בלבד (Viewer)
    ("soql", "תוצאת SOQL", False),         # קריאה בלבד (Viewer)
]

_DOT = {"green": "🟢", "yellow": "🟡", "red": "🔴"}

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
