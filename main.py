"""
כלי מיגרציה לסיילספורס — wizard (Streamlit).

הרצה:  streamlit run main.py
"""
import streamlit as st

from config import template_config
from modules import (
    sheets_io, query_builder, field_dictionary, mapper, recent_sheets,
    splitter, dedup_engine, output_writer, relationship_builder, campaign_member_builder,
    validator, notes_store,
)

st.set_page_config(page_title="כלי מיגרציה לסיילספורס", layout="wide")

# כיוון RTL בסיסי לעברית (כולל כותרות) — אך קוד (SQL) תמיד LTR כדי שלא יוצג הפוך
st.markdown(
    "<style>"
    ".stApp, .stMarkdown, .stTextInput, .stTextArea, .stButton,"
    ' [data-testid="stHeading"], h1, h2, h3, h4 {direction: rtl; text-align: right;}'
    '[data-testid="stCode"], [data-testid="stCode"] * {direction: ltr; text-align: left;}'
    # פאנל-צד צר: הניווט עבר לסרגל העליון; נשארו רק רענון + פתק-הערות
    ' [data-testid="stSidebar"] {min-width: 280px; max-width: 320px;}'
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

# בחירות מיוחדות ב-dropdown של המיפוי (מופיעות בראש הרשימה)
_OTHER = "אחר (הזן ידנית)"
_UNMAPPED = "—"
_BLANK = "— ריק —"  # ב-dropdown של API: בחירת 'כלום' בלי לפתוח תיבת-הקלדה


@st.cache_data(show_spinner=False)
def _read_cached(link: str, tab: str | None) -> list[list[str]]:
    """
    קריאת ערכי-גיליון עם זיכרון-מטמון: כל עוד לא לחצו 'רענן', אותה (גיליון, לשונית)
    נקראת פעם אחת בלבד — מעבר בין מסכים לא קורא שוב מ-Google (מהיר, חוסך מכסת-API).
    אחרי כתיבה לגיליון יש לרוקן את המטמון (`_read_cached.clear()`) כדי לא להציג נתון ישן.
    """
    return sheets_io.read_values(link, tab=tab)


# ===== ניווט: סרגל-שלבים עליון + סטטוס חי =====
# st.session_state["status"][step_index][sub] = טקסט-badge קצר.
# כל מסך כותב את הסטטוס שלו בסוף הצינור (lazy) — הסרגל בלבד קורא משם; אין צימוד בין המסכים.

def _set_status(step: int, text: str, sub: str = "") -> None:
    """שומר badge-טקסט לשלב. `sub` מבדיל בין תת-מסכי שלבים 4/5 (אנשי-קשר/קמפיינים וכו')."""
    st.session_state.setdefault("status", {}).setdefault(step, {})[sub] = text


def _status_badge(step: int) -> str:
    """מאחד את כל ה-badges של שלב (כולל תת-מסכים) למחרוזת אחת לסרגל."""
    parts = st.session_state.get("status", {}).get(step, {})
    return " · ".join(p for p in parts.values() if p)


def _truncate(s: str, n: int = 12) -> str:
    """קיצור שם-שדה ל-badge בסרגל (השם המלא נשאר בתצוגת המסך)."""
    return s if len(s) <= n else s[: n - 1] + "…"


def _topbar() -> None:
    """סרגל-שלבים עליון: ניווט בלחיצה + badge-סטטוס לכל שלב (RTL טבעי)."""
    cols = st.columns(len(STEPS))
    active = st.session_state.get("step", 0)
    status = st.session_state.get("status", {})
    for i, (col, step) in enumerate(zip(cols, STEPS)):
        with col:
            done = bool(status.get(i))
            prefix = "✓ " if done else f"{i + 1} · "
            if st.button(prefix + step["label"], key=f"nav_{i}",
                         use_container_width=True,
                         type="primary" if i == active else "secondary"):
                st.session_state["step"] = i
                st.rerun()
            badge = _status_badge(i)
            st.markdown(
                f"<div style='text-align:center;font-size:0.8rem;color:#555;"
                f"min-height:1.2em'>{badge or '—'}</div>",
                unsafe_allow_html=True,
            )
    st.divider()


def _sidebar_controls() -> None:
    """
    שני כפתורים זה-לצד-זה מעל הקו המפריד, ותחתיו פתק-הערות אישי שנשמר מקומית:
    - 'רענן את 3 הגיליונות'      — מרוקן את מטמון-הקריאה (קורא נתונים טריים מטמפלייט+DB+מיפוי).
    - 'רענן ואפס מנגנונים ומיפוי' — מרוקן מטמון *וגם* מאפס מנגנוני-זיהוי ובחירות-מיפוי;
                                    משאיר חיבורים והערות.
    """
    c1, c2 = st.sidebar.columns(2)
    if c1.button("רענן את 3 הגיליונות", use_container_width=True,
                 help="קורא מחדש נתונים עדכניים משלושת הגיליונות (טמפלייט, DB, מיפוי). "
                      "לא נוגע בבחירות שלך."):
        _read_cached.clear()
        st.rerun()
    if c2.button("רענן ואפס מנגנונים ומיפוי", use_container_width=True,
                 help="מנקה נתונים *וגם* מאפס את מנגנוני-הזיהוי ואת בחירות-המיפוי "
                      "(אובייקט+API לכל עמודה). החיבורים וההערות נשארים."):
        _read_cached.clear()
        # מנקה בחירות וחישובים, אך משאיר את החיבורים, ההערות וכל השאר על כנם
        for k in list(st.session_state.keys()):
            if k.startswith(("mech_", "obj_", "api_", "tiebreak")) or k in (
                "mechanisms",
            ):
                del st.session_state[k]
        st.rerun()

    st.sidebar.divider()

    # פתק-הערות אישי — נשמר לקובץ מקומי, נשמר בין סשנים, רק המשתמש מוחק.
    if "user_notes" not in st.session_state:
        st.session_state["user_notes"] = notes_store.load()
    notes_val = st.sidebar.text_area(
        "📝 הערות אישיות", key="user_notes", height=520,
        placeholder="מקום לרשום לעצמך תזכורות על התהליך…",
    )
    notes_store.save(notes_val)


def screen_connection() -> None:
    """שלב 0 — חיבור שלושת הגיליונות."""
    st.header("חיבור גיליונות")

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

    # סטטוס לסרגל: כמה מ-3 הגיליונות מחוברים (קישור נבחר)
    n_linked = sum(1 for k, _, _ in SHEETS if st.session_state.get(f"link_{k}"))
    if n_linked:
        _set_status(0, f"{n_linked}/3 מחוברים")

    if st.button("בדוק חיבור"):
        st.divider()
        for key, label, needs_write in SHEETS:
            link = st.session_state.get(f"link_{key}", "")
            status = sheets_io.connection_status(link, needs_write)
            suffix = f"  ·  _{status.name}_" if status.name else ""
            st.markdown(f"{_DOT[status.color]} **{label}** — {status.message}{suffix}")
            if status.name:
                recent_sheets.remember(key, sheets_io.extract_id(link), status.name)


# מקרא מקובץ: (אייקון, תווית, [סטטוסים]). הסדר כאן הוא סדר המקרא.
# 'התאמה שגויה' ו'לא נמצאה התאמה' מאוחדים לנורית אדומה אחת.
_LEGEND = [
    ("✅", "התאמה", [mapper.STATUS_VALID]),
    ("🔴", "התאמה שגויה/חסרה", [mapper.STATUS_INVALID, mapper.STATUS_MISSING]),
    ("🏳️", "בקרה (לא נטען)", [mapper.STATUS_CONTROL]),
    ("⚠️", "האובייקט לא בשאילתא", [mapper.STATUS_NO_DICT]),
    ("⚪", "לא רלוונטי", [mapper.STATUS_IGNORE]),
]
# כל סטטוס → אייקון-הקבוצה שלו (INVALID ו-MISSING → 🔴).
_STATUS_ICON = {s: icon for icon, _lbl, statuses in _LEGEND for s in statuses}

# רקע-שורה עדין לסטטוסים שדורשים תשומת-לב (כל מה שאינו "התאמה") — כדי שיבלטו מיד.
# INVALID ו-MISSING מאוחדים לנורית אדומה אחת → שניהם ברקע אדמדם.
_ROW_TINT = {
    mapper.STATUS_INVALID: "#fdecea",   # אדמדם
    mapper.STATUS_MISSING: "#fdecea",   # אדמדם
    mapper.STATUS_NO_DICT: "#fdecea",   # אדמדם
}


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


def _validation_summary(
    grid, object_api: str, dictionary: dict, *, written: bool = False, tab: str | None = None
) -> list:
    """
    בדיקת-נתונים על גריד-פלט (תאריכים/אורך-Id) + סיכום קצר במסך.
    מחזיר marks: [(row0, col0, message)] לסימון על גיליון-הטעינה.

    written: False = תצוגה-מקדימה (עוד לא נכתב/נצבע) → ההודעה מנחה ללחוץ "בנה וכתוב".
             True  = אחרי-כתיבה → ההודעה מציינת שהתאים *כבר* סומנו אדום בלשונית tab.
    """
    issues, marks = validator.validate_output_grid(grid, object_api, dictionary)
    if not issues:
        st.success("בדיקת נתונים: לא נמצאו בעיות ✅ (נבדקו: תאריכים ומזהי Id)")
        return marks
    bad_dates = sum(1 for i in issues if i.kind == validator.KIND_BAD_DATE)
    bad_ids = sum(1 for i in issues if i.kind == validator.KIND_BAD_ID)
    parts = []
    if bad_dates:
        parts.append(f"{bad_dates} תאריכים")
    if bad_ids:
        parts.append(f"{bad_ids} מזהי-Id")
    example = issues[0].location  # דוגמת-מיקום (למשל "J16") כדי שהמשתמש ידע איפה לחפש
    head = f"בדיקת נתונים: ⚠️ {len(issues)} בעיות ({' · '.join(parts)})."
    if written:
        where = f"בלשונית **{tab}**" if tab else "בגיליון-הטעינה"
        st.warning(f"{head} התאים סומנו אדום {where} (למשל {example}), עם הסבר בריחוף.")
    else:
        st.warning(f"{head} לחץ **בנה וכתוב** כדי לסמן אותן אדום בלשונית הפלט (למשל {example}).")
    with st.expander("פירוט הבעיות"):
        for i in issues:
            st.markdown(f"- **{i.location}** · {i.label}: {i.message}")
    return marks


def _recheck_button(key: str) -> None:
    """כפתור 'בדוק שוב' — קורא נתונים טריים מהגיליונות ומריץ שוב את הבדיקה."""
    if st.button("🔍 בדוק שוב", key=key,
                 help="קורא נתונים עדכניים מהגיליונות ומריץ שוב את בדיקת הנתונים"):
        _read_cached.clear()
        st.rerun()


def _apply_validation_marks(link: str, tab: str, grid, builder_colors, marks) -> None:
    """
    צובע מחדש את גיליון-הטעינה (אידמפוטנטי): מאפס רקע+הערות בטווח-הדאטה, מצייר את
    צבעי-הבונה ואת תאי-השגיאה (אדום-עז 'error'), ומוסיף הערת-תא עם הסיבה.
    מניח שהגריד כבר נכתב (write_grid) — חייב לרוץ במקום color_cells הרגיל.
    """
    n_cols = max((len(r) for r in grid), default=0)
    sheets_io.reset_data_format(link, tab, 2, len(grid), n_cols)  # 2 = שורות-הכותרת
    error_cells = [(r, c, "error") for r, c, _ in marks]
    sheets_io.color_cells(link, tab, list(builder_colors) + error_cells)
    if marks:
        sheets_io.set_cell_notes(link, tab, [(r, c, m) for r, c, m in marks])


def _object_selectbox(c: mapper.TemplateColumn, base_objs: list[str]) -> str:
    """dropdown אובייקט לשורה. מחזיר את האובייקט שנבחר (כולל '' ללא-מיפוי / ערך ידני)."""
    opts = [_OTHER, _UNMAPPED] + base_objs
    # עמודת-בקרה מגיעה ריקה (בלי הניחוש הגולמי) — אפשר עדיין לבחור ידנית אם הכלי טעה
    cur = "" if c.status == mapper.STATUS_CONTROL else c.object_api
    if cur in base_objs:
        idx = opts.index(cur)
    elif not cur:
        idx = opts.index(_UNMAPPED)
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
    # תצוגה = שם השדה בעברית (Label); הערך הנשמר = ה-API. כפילות-תוויות → API בסוגריים לייחוד.
    fields = mapper.candidates_for(obj, dictionary)
    label_counts: dict[str, int] = {}
    for f in fields:
        label_counts[f.label] = label_counts.get(f.label, 0) + 1
    disp2api = {}
    for f in fields:
        if not f.label:
            disp = f.api  # שדה ללא תווית — מציגים את ה-API עצמו
        elif label_counts[f.label] == 1:
            disp = f.label
        else:
            disp = f"{f.label} ({f.api})"  # תווית כפולה — מוסיפים API לייחוד
        disp2api[disp] = f.api
    opts = [_OTHER, _BLANK] + list(disp2api)
    # עמודת-בקרה מגיעה ריקה; שדה ללא ערך נברירת-מחדל ל"ריק" (לא מציע שדה שגוי אוטומטית)
    cur = "" if c.status == mapper.STATUS_CONTROL else (c.clean_api or c.proposed_api)
    cur_disp = next((d for d, a in disp2api.items() if a == cur), None)
    if cur_disp:
        idx = opts.index(cur_disp)
    elif cur:
        idx = opts.index(_OTHER)
    else:
        idx = opts.index(_BLANK)
    sel = st.selectbox("API", opts, index=idx, key=f"api_{c.index}", label_visibility="collapsed")
    if sel == _OTHER:
        default = cur if not cur_disp else ""
        return st.text_input("API (ידני)", value=default, key=f"apiother_{c.index}",
                             label_visibility="collapsed").strip()
    if sel == _BLANK:
        return ""
    return disp2api[sel]


def screen_mapping() -> None:
    """שלבים 2–3 — מיפוי וולידציה עם עריכה inline."""
    st.header("2 · מיפוי")

    template_link = st.session_state.get("link_template", "")
    soql_link = st.session_state.get("link_soql", "")
    if not template_link or not soql_link:
        st.warning("חסר חיבור — חזור למסך החיבור וחבר את *עותק הטמפלייט* ואת *מיפוי אובייקטים ושדות*.")
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
        f"{icon} {lbl} ({sum(counts.get(s, 0) for s in statuses)})"
        for icon, lbl, statuses in _LEGEND
    )
    st.markdown(f"<div style='font-size:1.15rem'>{legend}</div>", unsafe_allow_html=True)

    # סטטוס לסרגל: התאמה / בקרה / (אם יש) אדומות
    _valid = counts.get(mapper.STATUS_VALID, 0)
    _control = counts.get(mapper.STATUS_CONTROL, 0)
    _red = counts.get(mapper.STATUS_INVALID, 0) + counts.get(mapper.STATUS_MISSING, 0)
    _badge = f"✅{_valid} · 🏳️{_control}" + (f" · 🔴{_red}" if _red else "")
    _set_status(1, _badge)

    for w in dict_warnings:
        st.warning(w)

    st.caption(
        "ערוך כל שורה: בחר אובייקט ו-API מהרשימות (או *אחר* להקלדה). תיקוני אובייקט נשמרים "
        "לסשן; תיקוני API ייכתבו לטמפלייט בלחיצת *נעל ושמור*."
    )

    base_objs = list(dictionary.keys())
    rows = [c for c in cols if c.status != mapper.STATUS_IGNORE]
    ignored = [c for c in cols if c.status == mapper.STATUS_IGNORE]
    if ignored:
        with st.expander(f"⚪ עמודות מוסתרות ({len(ignored)}) — מפרידים/תיאורים ללא שדה"):
            for c in ignored:
                letter = sheets_io.col_letter(c.index)
                st.markdown(f"- **{letter}** · {c.label or '*(ריק)*'}")

    # כותרות עמודות (סדר לוגי; תחת RTL מופיע מימין לשמאל)
    widths = [3, 3, 4, 1, 1]
    h = st.columns(widths)
    for col, title in zip(h, ("שם עמודה מהלקוח", "אובייקט", "API", "נורית", "עמ'")):
        col.markdown(f"**{title}**")

    corrections: dict[int, str] = {}
    for c in rows:
        col_name, col_obj, col_api, col_light, col_letter = st.columns(widths)
        tint = _ROW_TINT.get(c.status)
        bg = f"background:{tint};" if tint else ""
        col_name.markdown(
            f"<div style='{bg}padding:6px 8px;border-radius:4px'>{c.label or '—'}</div>",
            unsafe_allow_html=True,
        )
        with col_obj:
            chosen_obj = _object_selectbox(c, base_objs)
        with col_api:
            chosen_api = _api_selectbox(c, chosen_obj, dictionary)
        col_light.markdown(
            f"<div style='{bg}font-size:1.6rem;text-align:center;border-radius:4px;"
            f"padding:2px 0'>{_STATUS_ICON.get(c.status, '')}</div>",
            unsafe_allow_html=True,
        )
        col_letter.markdown(
            f"<div style='{bg}text-align:center;border-radius:4px;padding:6px 0'>"
            f"{sheets_io.col_letter(c.index)}</div>",
            unsafe_allow_html=True,
        )
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


_N_MECHANISMS = 5


def screen_identity() -> None:
    """מסך הרכבת מנגנוני-זיהוי (3 מנגנונים מדורגים) — המשתמש בוחר, הכלי מרכיב."""
    st.header("3 · מנגנוני זיהוי")
    st.write(
        "הרכב עד שלושה מנגנונים לזיהוי איש-קשר, לפי עדיפות (1→3). כל מנגנון = צירוף "
        "שדות שצריכים *כולם* להתאים. הראשון שמוצא התאמה מנצח."
    )

    template_link = st.session_state.get("link_template", "")
    soql_link = st.session_state.get("link_soql", "")
    if not template_link or not soql_link:
        st.warning("חסר חיבור — חזור למסך החיבור וחבר את *עותק הטמפלייט* ואת *מיפוי אובייקטים ושדות*.")
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

    # זריעה חד-פעמית של מצב הווידג'טים מהקונפיג השמור — רק כשהמפתח לא קיים
    # (Streamlit זורק מצב-widget של מסך שלא הוצג; כך החזרה למסך לא מאפסת את הבחירה).
    saved = st.session_state.get("mechanisms", [])  # list[list[str]] של שמות-API
    for n in range(1, _N_MECHANISMS + 1):
        if f"mech_active_{n}" not in st.session_state:
            mech = saved[n - 1] if (n - 1) < len(saved) else None
            if mech is not None:
                st.session_state[f"mech_active_{n}"] = True
                st.session_state[f"mech_fields_{n}"] = [pool[a] for a in mech if a in pool]
            else:
                st.session_state[f"mech_active_{n}"] = (n == 1)
                st.session_state[f"mech_fields_{n}"] = [default_disp] if (n == 1 and default_disp) else []

    mechanisms: list[list[str]] = []
    for n in range(1, _N_MECHANISMS + 1):
        active = st.checkbox(f"מנגנון {n} — פעיל", key=f"mech_active_{n}")
        chosen = st.multiselect(
            f"שדות מנגנון {n} (צירוף AND)",
            options,
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

    # סטטוס לסרגל: ✓ + שם-השדה הראשון (מקוצר) לכל מנגנון שמור
    saved_mechs = st.session_state.get("mechanisms") or []
    if saved_mechs:
        full = {api: lbl.split(" — ", 1)[-1] for api, lbl in pool.items()}
        _set_status(2, " · ".join(
            "✓" + _truncate(full.get(m[0], m[0])) for m in saved_mechs if m
        ))


def _db_queries(template_link: str, soql_link: str) -> dict[str, list[str]]:
    """ממפה אובייקט→שדות-תקפים לייצוא DB (כולל שדות-lookup נגזרים). עלול לזרוק על כשל-קריאה."""
    cols, _w, _d = _run_mapping_pipeline(template_link, soql_link)
    queries: dict[str, list[str]] = {}
    for c in cols:
        if c.status == mapper.STATUS_VALID and c.clean_api:
            fields = queries.setdefault(c.object_api, [])
            if c.clean_api not in fields:
                fields.append(c.clean_api)
    # שדות נגזרים שאינם בטמפלייט אך נדרשים לקריאת ה-DB (כגון lookups של Relationships)
    for obj, extra in template_config.REQUIRED_DB_FIELDS.items():
        if obj in queries:
            for f in extra:
                if f not in queries[obj]:
                    queries[obj].append(f)
    return queries


def screen_queries() -> None:
    """שלב 1 — בונה שאילתות: מילון FieldDefinition + ייצוא-DB לכל אובייקט, עם עריכה לפני העתקה."""
    st.subheader("שאילתות (העתק ל-Inspector)")
    st.write(
        "בחר שאילתה מהרשימה, ערוך אותה אם צריך, והעתק ל-Salesforce Inspector. שמור כל "
        "תוצאה ללשונית המתאימה (מוצגת מתחת)."
    )

    template_link = st.session_state.get("link_template", "")
    soql_link = st.session_state.get("link_soql", "")

    # אובייקטים למילון השדות (FieldDefinition) — ניתנים לעריכה
    default_objects = "\n".join(template_config.DEFAULT_OBJECTS)
    with st.expander("אובייקטים למילון השדות", expanded=False):
        raw = st.text_area("אובייקט בכל שורה", value=default_objects, height=120, key="soql_objects")
    objects = query_builder.clean_object_names(raw)

    # מאגר השאילתות הזמינות: מילון (תמיד, אם יש אובייקטים) + ייצוא-DB לכל אובייקט (אם המיפוי מוכן)
    query_map: dict[str, str] = {}
    tab_hint: dict[str, str] = {}
    if objects:
        query_map["מילון שדות (FieldDefinition)"] = query_builder.build_field_definition_query(objects)
    if template_link and soql_link:
        try:
            for obj, fields in _db_queries(template_link, soql_link).items():
                label = f"ייצוא DB — {obj}"
                query_map[label] = query_builder.build_data_query(obj, fields)
                tab_hint[label] = template_config.DB_TAB_NAMES.get(obj, obj)
        except Exception as e:  # noqa: BLE001
            st.error(f"שגיאה בבניית שאילתות הייצוא:\n\n{e}")

    if not query_map:
        st.info("הזן אובייקטים למילון, או חבר את הטמפלייט והמיפוי כדי לקבל גם שאילתות ייצוא-DB.")
        return

    selected = st.selectbox("בחר שאילתה", list(query_map), key="query_pick")
    # זריעה-מחדש של העורך כשמשנים בחירה (אחרת הערך נצמד לשאילתה הקודמת)
    if st.session_state.get("_query_pick_last") != selected:
        st.session_state["query_editor"] = query_map[selected]
        st.session_state["_query_pick_last"] = selected
    st.text_area("שאילתה (ניתנת לעריכה)", key="query_editor", height=170)
    if selected in tab_hint:
        st.caption(f"שמור את התוצאה ללשונית: **{tab_hint[selected]}**")
    else:
        st.caption("שמור את התוצאה כגיליון *מיפוי אובייקטים ושדות* וחבר אותו למעלה.")
    # תצוגת-העתקה נקייה (LTR + כפתור-העתקה) של מה שבעורך
    st.code(st.session_state.get("query_editor", ""), language="sql")


def screen_db_validation() -> None:
    """שלב 1 — אימות גיליון ה-DB מול הלשוניות הנדרשות."""
    st.subheader("סטטוס גיליון ה-DB")

    template_link = st.session_state.get("link_template", "")
    soql_link = st.session_state.get("link_soql", "")
    db_link = st.session_state.get("link_db", "")
    if not template_link or not soql_link:
        st.info("חבר את הטמפלייט והמיפוי למעלה כדי לבדוק את גיליון ה-DB.")
        return
    if not db_link:
        st.info("גיליון DB אינו מחובר — חבר אותו למעלה.")
        return

    try:
        queries = _db_queries(template_link, soql_link)
    except Exception as e:  # noqa: BLE001
        st.error(f"שגיאה בקריאת הגיליונות:\n\n{e}")
        return
    if not queries:
        st.warning("אין עמודות ממופות תקפות — השלם קודם את המיפוי.")
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
    st.header("בניית אנשי קשר לטעינה")
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
        st.warning("חסר חיבור — חזור למסך החיבור וחבר את *עותק הטמפלייט*, *מיפוי אובייקטים ושדות* ו-*קובץ DB*.")
        return
    if not mechanisms:
        st.warning("לא הוגדרו מנגנוני זיהוי — חזור למסך *מנגנוני זיהוי* ושמור לפחות מנגנון אחד.")
        return

    try:
        cols, _warnings, dictionary = _run_mapping_pipeline(template_link, soql_link)
        tmpl_rows = _read_cached(template_link, template_config.TEMPLATE_TAB)
        split_records = splitter.split_object(
            "Contact", tmpl_rows, cols,
            data_start_row=template_config.TEMPLATE_DATA_START_ROW,
        )
        record_values = [r.values for r in split_records]
        source_rows = [r.source_row for r in split_records]

        db_rows = _read_cached(db_link, template_config.DB_TAB_NAMES["Contact"])
        db_records = sheets_io.rows_to_dicts(db_rows)
        db_by_id = {r["Id"]: r for r in db_records if r.get("Id")}

        dedup = dedup_engine.deduplicate(
            record_values, mechanisms, db_records,
            digits_only_fields=template_config.DIGITS_ONLY_FIELDS,
        )
        grid, cell_colors = output_writer.build_contacts_grid(dedup, record_values, cols, db_by_id)
        manual_grid, _manual_colors = output_writer.build_manual_grid(
            dedup, record_values, cols, db_by_id, source_rows,
            digits_only_fields=template_config.DIGITS_ONLY_FIELDS,
        )
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
    _set_status(3, f"א.קשר: {c.get('inserts', 0)} חדשים · {c.get('upserts', 0)} קיימים",
                sub="contacts")

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

    # ===== בדיקת נתונים (אוטומטית) =====
    _validation_summary(grid, "Contact", dictionary)
    _recheck_button("recheck_contacts")

    # ===== כתיבה =====
    st.divider()
    out_tab = template_config.OUTPUT_TAB_CONTACTS
    manual_tab = template_config.OUTPUT_TAB_MANUAL_CONTACTS
    manual_count = max(len(manual_grid) - 1, 0)  # בלי שורת-הכותרת
    st.markdown(f"היעד: לשונית **{out_tab}** בתוך הטמפלייט (כתיבה חוזרת מחליפה את התוכן הקודם).")
    if manual_count:
        st.info(
            f"יש {manual_count} רשומות לטיפול ידני — הן נכתבות ללשונית **{manual_tab}** "
            f"ולא נטענות. סמן שם בעמודת *בחר* את שורת ה**מאגר** הנכונה, ולחץ שוב על הכפתור "
            "כדי לקלוט את הבחירות לפלט (Upsert)."
        )

    if st.button("בנה וכתוב גיליונות טעינה"):
        try:
            # קריאה טרייה (לא ממטמון) של לשונית הטיפול הידני — המשתמש עורך אותה ישירות
            # בגיליון; קליטת ה✓ חייבת לשקף את מצבו הנוכחי. לשונית שלא קיימת עדיין → ריק.
            try:
                manual_rows = sheets_io.read_values(template_link, manual_tab)
            except Exception:  # noqa: BLE001 — הלשונית עדיין לא נוצרה
                manual_rows = []
            choices, warns = output_writer.parse_manual_choices(manual_rows)
            for w in warns:
                st.warning(w)

            # בנייה מחדש עם הבחירות (אידמפוטנטי): מי שנבחר נכנס לפלט כ-Upsert,
            # והסימונים נשמרים בלשונית הידנית.
            grid2, colors2 = output_writer.build_contacts_grid(
                dedup, record_values, cols, db_by_id, manual_choices=choices
            )
            manual2, manual2_colors = output_writer.build_manual_grid(
                dedup, record_values, cols, db_by_id, source_rows, marked=choices,
                digits_only_fields=template_config.DIGITS_ONLY_FIELDS,
            )

            sheets_io.ensure_tab(template_link, out_tab)
            n = sheets_io.write_grid(template_link, out_tab, grid2)
            sheets_io.set_tab_rtl(template_link, out_tab)
            # צביעת-בונה + סימוני-ולידציה (אדום + הערת-תא) על גיליון-הטעינה
            marks = _validation_summary(grid2, "Contact", dictionary, written=True, tab=out_tab)
            _apply_validation_marks(template_link, out_tab, grid2, colors2, marks)

            remaining = max(len(manual2) - 1, 0)  # שורות שעדיין דורשות טיפול ידני
            if remaining:
                sheets_io.ensure_tab(template_link, manual_tab)
                sheets_io.write_grid(template_link, manual_tab, manual2)
                sheets_io.set_tab_rtl(template_link, manual_tab)
                sheets_io.color_cells(template_link, manual_tab, manual2_colors)
                sheets_io.set_checkbox_column(
                    template_link, manual_tab, output_writer.MANUAL_CHOICE_COL,
                    1, len(manual2),  # שורות-דאטה (אחרי שורת-הכותרת)
                )

            _read_cached.clear()  # רוקון מטמון אחרי כתיבה
            msg = f"נכתבו {max(n - 2, 0)} שורות ללשונית {out_tab}."
            if choices:
                msg += f" נקלטו {len(choices)} בחירות ידניות."
            if remaining:
                msg += f" {remaining} רשומות ממתינות בלשונית {manual_tab}."
            st.success(msg)
        except Exception as e:  # noqa: BLE001
            st.error(f"כשל בכתיבה לטמפלייט: {e}")


def screen_campaigns() -> None:
    """שלב 5 (קמפיינים) — בניית גריד Campaigns מוכן-לטעינה וכתיבתו ללשונית-פלט בטמפלייט.

    מקביל ל-screen_contacts, אך הזיהוי הוא לפי **שם** בלבד (CAMPAIGN_MECHANISMS) —
    לא מנגנוני-הזיהוי של Contacts. כל שורות-ההרשמה לאותו אירוע מתקבצות לקמפיין אחד.
    """
    st.header("בניית קמפיינים לטעינה")
    st.write(
        "הכלי קורא את האירועים מהטמפלייט, מאחד שורות עם אותו שם-אירוע לקמפיין אחד, "
        "ומשווה למאגר כדי לדעת אילו קמפיינים כבר קיימים (לעדכון) ואילו חדשים. "
        "התוצאה נכתבת ללשונית מוכנה-לטעינה בתוך הטמפלייט."
    )

    template_link = st.session_state.get("link_template", "")
    soql_link = st.session_state.get("link_soql", "")
    db_link = st.session_state.get("link_db", "")

    if not template_link or not soql_link or not db_link:
        st.warning("חסר חיבור — חזור למסך החיבור וחבר את *עותק הטמפלייט*, *מיפוי אובייקטים ושדות* ו-*קובץ DB*.")
        return

    mechanisms = template_config.CAMPAIGN_MECHANISMS

    try:
        cols, _warnings, dictionary = _run_mapping_pipeline(template_link, soql_link)
        tmpl_rows = _read_cached(template_link, template_config.TEMPLATE_TAB)
        split_records = splitter.split_object(
            template_config.CAMPAIGN_OBJECT, tmpl_rows, cols,
            data_start_row=template_config.TEMPLATE_DATA_START_ROW,
        )
        record_values = [r.values for r in split_records]
        source_rows = [r.source_row for r in split_records]

        db_rows = _read_cached(db_link, template_config.DB_TAB_NAMES[template_config.CAMPAIGN_OBJECT])
        db_records = sheets_io.rows_to_dicts(db_rows)
        db_by_id = {r["Id"]: r for r in db_records if r.get("Id")}

        dedup = dedup_engine.deduplicate(
            record_values, mechanisms, db_records, local_key_prefix="K",
        )
        grid, cell_colors = output_writer.build_campaigns_grid(dedup, record_values, cols, db_by_id)
        manual_grid, _manual_colors = output_writer.build_manual_grid(
            dedup, record_values, cols, db_by_id, source_rows,
            object_api=template_config.CAMPAIGN_OBJECT,
        )
    except Exception as e:  # noqa: BLE001 — כל כשל מדווח למשתמש, לא מפיל את המסך
        st.error(f"שגיאה בהרצת הצינור:\n\n{e}")
        return

    # ===== סיכום-נורות =====
    c = dedup.counts
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("חדשים", c.get("inserts", 0))
    m2.metric("לעדכון", c.get("upserts", 0))
    m3.metric("⚠️ נמצאו כמה התאמות", c.get("ambiguous", 0))
    m4.metric("⚠️ ללא שם", c.get("unkeyed", 0))
    st.caption(
        f"{len(record_values)} שורות מהטמפלייט → {len(dedup.persons)} קמפיינים ייחודיים · "
        f"{len(db_records)} רשומות במאגר"
    )
    _set_status(3, f"קמפיינים: {c.get('inserts', 0)} חדשים · {c.get('upserts', 0)} קיימים",
                sub="campaigns")

    # ===== תצוגה מקדימה =====
    if len(grid) > 2:
        st.subheader("תצוגה מקדימה")
        st.dataframe(
            {grid[0][col]: [row[col] for row in grid[2:]] for col in range(len(grid[0]))},
            use_container_width=True,
        )
    else:
        st.info("אין קמפיינים בטמפלייט עדיין — תיכתבו שורות הכותרות בלבד.")

    # ===== בדיקת נתונים (אוטומטית) =====
    _validation_summary(grid, template_config.CAMPAIGN_OBJECT, dictionary)
    _recheck_button("recheck_campaigns")

    # ===== כתיבה =====
    st.divider()
    out_tab = template_config.OUTPUT_TAB_CAMPAIGNS
    manual_tab = template_config.OUTPUT_TAB_MANUAL_CAMPAIGNS
    manual_count = max(len(manual_grid) - 1, 0)  # בלי שורת-הכותרת
    st.markdown(f"היעד: לשונית **{out_tab}** בתוך הטמפלייט (כתיבה חוזרת מחליפה את התוכן הקודם).")
    if manual_count:
        st.info(
            f"יש {manual_count} רשומות לטיפול ידני — הן נכתבות ללשונית **{manual_tab}** "
            f"ולא נטענות. סמן שם בעמודת *בחר* את שורת ה**מאגר** הנכונה, ולחץ שוב על הכפתור "
            "כדי לקלוט את הבחירות לפלט (Upsert)."
        )

    if st.button("בנה וכתוב גיליונות טעינה"):
        try:
            try:
                manual_rows = sheets_io.read_values(template_link, manual_tab)
            except Exception:  # noqa: BLE001 — הלשונית עדיין לא נוצרה
                manual_rows = []
            choices, warns = output_writer.parse_manual_choices(manual_rows)
            for w in warns:
                st.warning(w)

            grid2, colors2 = output_writer.build_campaigns_grid(
                dedup, record_values, cols, db_by_id, manual_choices=choices
            )
            manual2, manual2_colors = output_writer.build_manual_grid(
                dedup, record_values, cols, db_by_id, source_rows,
                object_api=template_config.CAMPAIGN_OBJECT, marked=choices,
            )

            sheets_io.ensure_tab(template_link, out_tab)
            n = sheets_io.write_grid(template_link, out_tab, grid2)
            sheets_io.set_tab_rtl(template_link, out_tab)
            # צביעת-בונה + סימוני-ולידציה (אדום + הערת-תא) על גיליון-הטעינה
            marks = _validation_summary(grid2, template_config.CAMPAIGN_OBJECT, dictionary, written=True, tab=out_tab)
            _apply_validation_marks(template_link, out_tab, grid2, colors2, marks)

            remaining = max(len(manual2) - 1, 0)  # שורות שעדיין דורשות טיפול ידני
            if remaining:
                sheets_io.ensure_tab(template_link, manual_tab)
                sheets_io.write_grid(template_link, manual_tab, manual2)
                sheets_io.set_tab_rtl(template_link, manual_tab)
                sheets_io.color_cells(template_link, manual_tab, manual2_colors)
                sheets_io.set_checkbox_column(
                    template_link, manual_tab, output_writer.MANUAL_CHOICE_COL,
                    1, len(manual2),  # שורות-דאטה (אחרי שורת-הכותרת)
                )

            _read_cached.clear()  # רוקון מטמון אחרי כתיבה
            msg = f"נכתבו {max(n - 2, 0)} שורות ללשונית {out_tab}."
            if choices:
                msg += f" נקלטו {len(choices)} בחירות ידניות."
            if remaining:
                msg += f" {remaining} רשומות ממתינות בלשונית {manual_tab}."
            st.success(msg)
        except Exception as e:  # noqa: BLE001
            st.error(f"כשל בכתיבה לטמפלייט: {e}")


def screen_relationship() -> None:
    """שלב 5 (קשרים) — גזירת קשרים חדשים מצמדי אנשי-קשר וכתיבתם לגיליון-טעינה.

    כפתור יחיד: המשתמש לוחץ אחרי שטען את Contacts לסיילספורס והדביק חזרה את ה-Ids.
    הצינור קורא את "פלט - Contacts" לבניית local_key→Id, גוזר קשרים מהטמפלייט,
    מסנן זוגות קיימים-ב-DB, וכותב את החדשים ללשונית "פלט - Relationships".
    """
    st.header("בניית קשרים לטעינה")
    st.write(
        "הכלי גוזר קשרים בין אנשי-קשר ראשי לנוסף מכל שורה, ומסנן זוגות שכבר קיימים "
        "במאגר. **לחץ על הכפתור לאחר שטענת את Contacts לסיילספורס וה-Ids הודבקו חזרה "
        "בלשונית 'פלט - Contacts'.** כיוון אחד בלבד — סיילספורס יוצר את ההפוך אוטומטית."
    )

    template_link = st.session_state.get("link_template", "")
    soql_link = st.session_state.get("link_soql", "")
    db_link = st.session_state.get("link_db", "")
    mechanisms = st.session_state.get("mechanisms")

    if not template_link or not soql_link or not db_link:
        st.warning("חסר חיבור — חזור למסך החיבור וחבר את *עותק הטמפלייט*, *מיפוי אובייקטים ושדות* ו-*קובץ DB*.")
        return
    if not mechanisms:
        st.warning("לא הוגדרו מנגנוני זיהוי — חזור למסך *מנגנוני זיהוי* ושמור לפחות מנגנון אחד.")
        return

    if st.button("בנה וכתוב גיליון קשרים"):
        try:
            # רוקנים מטמון כדי לקרוא Ids עדכניים מ-"פלט - Contacts" (המשתמש הדביק אותם)
            _read_cached.clear()

            cols, _warnings, dictionary = _run_mapping_pipeline(template_link, soql_link)
            tmpl_rows = _read_cached(template_link, template_config.TEMPLATE_TAB)

            # ריצת Contacts (אותה ריצה כמו screen_contacts) לבניית local_key → record_idx
            contact_split = splitter.split_object(
                "Contact", tmpl_rows, cols,
                data_start_row=template_config.TEMPLATE_DATA_START_ROW,
            )
            contact_records = [r.values for r in contact_split]
            # db_records=[] — רק קיבוץ פנימי לצורך local_key; אין צורך ב-DB כאן
            contact_dedup = dedup_engine.deduplicate(
                contact_records, mechanisms, [],
                digits_only_fields=template_config.DIGITS_ONLY_FIELDS,
                local_key_prefix="C",
            )

            # local_key → sf_id מלשונית פלט-Contacts (לאחר שהמשתמש הדביק את ה-Ids)
            try:
                contacts_out_rows = sheets_io.read_values(
                    template_link, template_config.OUTPUT_TAB_CONTACTS
                )
            except Exception:  # noqa: BLE001 — הלשונית עדיין לא קיימת
                contacts_out_rows = []
            contact_id_map = relationship_builder.id_map_from_grid(contacts_out_rows)

            if not contact_id_map:
                st.error(
                    "לא נמצאו Ids ב-'פלט - Contacts' — "
                    "יש לטעון את Contacts לסיילספורס ולהדביק את ה-Ids חזרה לפני הרצת שלב זה."
                )
                return

            # DB Relationships — לסינון זוגות קיימים
            db_rel_rows = _read_cached(
                db_link, template_config.DB_TAB_NAMES[template_config.RELATIONSHIP_OBJECT]
            )
            db_rel_records = sheets_io.rows_to_dicts(db_rel_rows)
            db_rel_pairs = relationship_builder.db_rel_pairs_from_records(db_rel_records)

            rel_records = relationship_builder.derive_relationships(
                tmpl_rows, cols, contact_split, contact_dedup,
                contact_id_map, db_rel_pairs,
                data_start_row=template_config.TEMPLATE_DATA_START_ROW,
                block_primary=template_config.CONTACT_BLOCK_PRIMARY,
                block_secondary=template_config.CONTACT_BLOCK_SECONDARY,
                relationship_object=template_config.RELATIONSHIP_OBJECT,
            )

            grid, cell_colors = relationship_builder.build_relationship_grid(rel_records)

            new_count = max(len(grid) - 2, 0)
            skipped_db = sum(1 for r in rel_records if r.exists_in_db)
            pending_id = sum(1 for r in rel_records if r.warning)
            _set_status(4, f"קשרים: {new_count} חדשים · {skipped_db} קיימים", sub="rel")

            # אינדיקציית בדיקת-כפילויות — בראש התוצאות כדי שלא תתפספס.
            # שני המספרים (רשומות → זוגות) מוכיחים שהכיוון ההפוך אוחד: NPSP שומר כל
            # קשר בשני כיוונים, כך ש-unique_pairs ≈ מחצית db_records_count.
            db_records_count = len(db_rel_records)   # רשומות-קשר שנקראו מה-DB
            unique_pairs = len(db_rel_pairs)         # זוגות ייחודיים אחרי איחוד דו-כיווני
            st.info(
                f"🔎 **בדיקת כפילויות (דו-כיוונית):** נקראו {db_records_count} קשרים מהמאגר "
                f"→ {unique_pairs} זוגות ייחודיים (A↔B נחשבים אותו קשר). "
                f"{skipped_db} מהקשרים שנגזרו כבר קיימים במאגר — דולגו."
            )

            for r in rel_records:
                if r.warning:
                    st.warning(r.warning)

            out_tab = template_config.OUTPUT_TAB_RELATIONSHIPS
            sheets_io.ensure_tab(template_link, out_tab)
            n = sheets_io.write_grid(template_link, out_tab, grid)
            sheets_io.set_tab_rtl(template_link, out_tab)
            # צביעת-בונה + סימוני-ולידציה (אדום + הערת-תא) על גיליון-הטעינה
            marks = _validation_summary(grid, template_config.RELATIONSHIP_OBJECT, dictionary, written=True, tab=out_tab)
            _apply_validation_marks(template_link, out_tab, grid, cell_colors, marks)
            _read_cached.clear()

            msg = f"נכתבו {new_count} קשרים חדשים ללשונית {out_tab}."
            if skipped_db:
                msg += f" {skipped_db} קשרים כבר קיימים במאגר — לא נכתבו."
            if pending_id:
                msg += f" {pending_id} שורות ממתינות ל-Id (Contacts שטרם נטענו)."
            st.success(msg)

        except Exception as e:  # noqa: BLE001
            st.error(f"שגיאה בבניית גיליון הקשרים:\n\n{e}")


def screen_campaign_members() -> None:
    """שלב 5 (CampaignMember) — גזירת רשומות השתתפות וכתיבתן לגיליון-טעינה.

    כפתור יחיד — לאחר שטענת Contacts ו-Campaigns וה-Ids הודבקו בחזרה.
    לכל שורה עם "משתתף באירוע"=TRUE (לראשי / לנוסף) נוצרת רשומת CampaignMember.
    v1: טוען את כולם ללא בדיקת-קיום מול DB.
    """
    st.header("בניית CampaignMember")
    st.write(
        "הכלי יוצר רשומת השתתפות לכל אדם שסומן כ-'משתתף באירוע', ומקשר אותו "
        "לקמפיין המתאים. **לחץ על הכפתור לאחר שטענת Contacts ו-Campaigns לסיילספורס "
        "וה-Ids הודבקו חזרה בלשוניות הפלט שלהם.**"
    )

    template_link = st.session_state.get("link_template", "")
    soql_link = st.session_state.get("link_soql", "")
    db_link = st.session_state.get("link_db", "")
    mechanisms = st.session_state.get("mechanisms")

    if not template_link or not soql_link or not db_link:
        st.warning("חסר חיבור — חזור למסך החיבור וחבר את *עותק הטמפלייט*, *מיפוי אובייקטים ושדות* ו-*קובץ DB*.")
        return
    if not mechanisms:
        st.warning("לא הוגדרו מנגנוני זיהוי — חזור למסך *מנגנוני זיהוי* ושמור לפחות מנגנון אחד.")
        return

    if st.button("בנה וכתוב CampaignMember"):
        try:
            _read_cached.clear()  # מטמון מתרענן — נקרא Ids עדכניים מגיליונות הפלט

            cols, _warnings, dictionary = _run_mapping_pipeline(template_link, soql_link)
            tmpl_rows = _read_cached(template_link, template_config.TEMPLATE_TAB)

            # פיצול + dedup Contacts — לבניית (source_row, block) → local_key
            contact_split = splitter.split_object(
                "Contact", tmpl_rows, cols,
                data_start_row=template_config.TEMPLATE_DATA_START_ROW,
            )
            contact_dedup = dedup_engine.deduplicate(
                [r.values for r in contact_split], mechanisms, [],
                digits_only_fields=template_config.DIGITS_ONLY_FIELDS,
                local_key_prefix="C",
            )

            # פיצול + dedup Campaigns — לבניית source_row → campaign_local_key
            campaign_split = splitter.split_object(
                template_config.CAMPAIGN_OBJECT, tmpl_rows, cols,
                data_start_row=template_config.TEMPLATE_DATA_START_ROW,
            )
            campaign_dedup = dedup_engine.deduplicate(
                [r.values for r in campaign_split], template_config.CAMPAIGN_MECHANISMS, [],
                local_key_prefix="K",
            )

            # local_key → sf_id מגיליונות הפלט (אחרי שהמשתמש הדביק Ids)
            try:
                contacts_out = sheets_io.read_values(template_link, template_config.OUTPUT_TAB_CONTACTS)
            except Exception:  # noqa: BLE001
                contacts_out = []
            try:
                campaigns_out = sheets_io.read_values(template_link, template_config.OUTPUT_TAB_CAMPAIGNS)
            except Exception:  # noqa: BLE001
                campaigns_out = []

            contact_id_map = relationship_builder.id_map_from_grid(contacts_out)
            campaign_id_map = relationship_builder.id_map_from_grid(campaigns_out)

            if not contact_id_map and not campaign_id_map:
                st.error(
                    "לא נמצאו Ids ב-'פלט - Contacts' וב-'פלט - Campaigns' — "
                    "יש לטעון את שניהם ולהדביק את ה-Ids לפני הרצת שלב זה."
                )
                return

            field_cols = campaign_member_builder._cm_field_columns(
                cols, template_config.CM_OBJECT
            )

            cm_records = campaign_member_builder.derive_campaign_members(
                tmpl_rows, cols, contact_split, contact_dedup,
                campaign_split, campaign_dedup,
                contact_id_map, campaign_id_map,
                data_start_row=template_config.TEMPLATE_DATA_START_ROW,
                block_primary=template_config.CONTACT_BLOCK_PRIMARY,
                block_secondary=template_config.CONTACT_BLOCK_SECONDARY,
                cm_object=template_config.CM_OBJECT,
                cm_participating_label=template_config.CM_PARTICIPATING_LABEL,
            )

            grid, cell_colors = campaign_member_builder.build_campaign_member_grid(
                cm_records, field_cols
            )

            written = max(len(grid) - 2, 0)
            pending = sum(1 for r in cm_records if r.warning)
            _set_status(4, f"CM: {written} נוצרו", sub="cm")

            for r in cm_records:
                if r.warning:
                    st.warning(r.warning)

            out_tab = template_config.OUTPUT_TAB_CM
            sheets_io.ensure_tab(template_link, out_tab)
            sheets_io.write_grid(template_link, out_tab, grid)
            sheets_io.set_tab_rtl(template_link, out_tab)
            # צביעת-בונה + סימוני-ולידציה (אדום + הערת-תא) על גיליון-הטעינה
            marks = _validation_summary(grid, template_config.CM_OBJECT, dictionary, written=True, tab=out_tab)
            _apply_validation_marks(template_link, out_tab, grid, cell_colors, marks)
            _read_cached.clear()

            msg = f"נכתבו {written} רשומות CampaignMember ללשונית {out_tab}."
            if pending:
                msg += f" {pending} רשומות ממתינות ל-Id (Contacts/Campaigns שטרם נטענו)."
            st.success(msg)

        except Exception as e:  # noqa: BLE001
            st.error(f"שגיאה בבניית CampaignMember:\n\n{e}")


def screen_step1() -> None:
    """שלב 1 — חיבור הגיליונות + שאילתות (מילון FieldDefinition + ייצוא DB) + בדיקת DB."""
    screen_connection()
    st.divider()
    screen_queries()
    st.divider()
    screen_db_validation()


# מבנה 5 השלבים. שלבים 4–5 מקבצים שני בונים כל אחד (תת-ניווט פנימי).
STEPS = [
    {"label": "חיבור + שאילתות", "screen": screen_step1},
    {"label": "מיפוי", "screen": screen_mapping},
    {"label": "מנגנוני זיהוי", "screen": screen_identity},
    {"label": "גיליונות ראשיים",
     "subs": [("אנשי קשר", screen_contacts), ("קמפיינים", screen_campaigns)]},
    {"label": "גיליונות מותנים",
     "subs": [("קשרים", screen_relationship), ("CampaignMember", screen_campaign_members)]},
]

if "step" not in st.session_state:
    st.session_state["step"] = 0

_topbar()
_sidebar_controls()

_active = st.session_state["step"]
_step = STEPS[_active]
if "screen" in _step:
    _step["screen"]()
else:
    # תת-ניווט אופקי בשלבים 4/5 — רץ רק הבונה שנבחר (לא st.tabs, שמריץ את שניהם)
    _subs = dict(_step["subs"])
    _chosen = st.radio("בחר גיליון", list(_subs), key=f"sub_{_active}", horizontal=True)
    _subs[_chosen]()
