"""
כלי מיגרציה לסיילספורס v2 — wizard (Streamlit).
הרצה: streamlit run main.py
"""
from __future__ import annotations

import streamlit as st

from config.runtime_schema import RuntimeSchema, ObjectDef
from modules import (
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
    " .block-container {padding-top: 1.5rem;}"
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
        card_class = _CARD_COLORS[css_class]
        icon = _status_icon("current" if num == current else status)
        if col.button(
            f"{icon} {num}. {label}",
            key=f"nav_{num}",
            use_container_width=True,
        ):
            st.session_state["step"] = num
            st.rerun()
    st.divider()


# ─── screens ──────────────────────────────────────────────────────────────────

def screen_step1() -> None:
    """Step 1: Connection + Queries — implemented in Task 4+5."""
    st.info("שלב 1 — בפרוסה הבאה (Task 4–5)")


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
