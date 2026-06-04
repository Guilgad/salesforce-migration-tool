"""
חיבור ל-Google Sheets דרך ה-service account, ובדיקת גישה למסך החיבור.

מספק את הלוגיקה של "נורות החיבור": לכל גיליון בודק אם ה-service account ניגש אליו
ובאיזו רמה (Editor/Viewer), ומחזיר סטטוס צבע (green/yellow/red) לפי הרמה הנדרשת.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

from config import settings


@dataclass
class AccessResult:
    """תוצאת בדיקת גישה גולמית מול Drive."""
    ok: bool                 # האם ה-service account הצליח לפתוח את הקובץ
    name: str | None
    can_edit: bool
    error: str | None = None


@dataclass
class ConnectionStatus:
    """סטטוס מוכן-לתצוגה לנורית החיבור."""
    color: str               # "green" | "yellow" | "red"
    message: str
    name: str | None = None


_credentials: Credentials | None = None


def get_credentials() -> Credentials:
    """טוען (פעם אחת) את מפתח ה-service account."""
    global _credentials
    if _credentials is None:
        _credentials = Credentials.from_service_account_file(
            str(settings.CREDENTIALS_FILE), scopes=settings.SCOPES
        )
    return _credentials


def service_account_email() -> str:
    return get_credentials().service_account_email


def _drive():
    return build("drive", "v3", credentials=get_credentials(), cache_discovery=False)


def _sheets():
    return build("sheets", "v4", credentials=get_credentials(), cache_discovery=False)


def read_values(link_or_id: str, tab: str | None = None) -> list[list[str]]:
    """
    קורא את כל ערכי התאים מלשונית בגיליון, כרשימת שורות (כל שורה רשימת מחרוזות).
    ברירת מחדל: הלשונית הראשונה. שורות עשויות להיות "קצרות" (תאים ריקים בסוף מושמטים).
    """
    sid = extract_id(link_or_id)
    svc = _sheets()
    if tab is None:
        meta = (
            svc.spreadsheets()
            .get(spreadsheetId=sid, fields="sheets.properties.title")
            .execute()
        )
        sheets = meta.get("sheets", [])
        if not sheets:
            return []
        tab = sheets[0]["properties"]["title"]
    resp = svc.spreadsheets().values().get(spreadsheetId=sid, range=tab).execute()
    return resp.get("values", [])


def rows_to_dicts(rows: list[list[str]]) -> list[dict]:
    """
    ממיר גריד (שורה ראשונה = כותרת) לרשימת מילונים {כותרת: ערך}.
    חסין לשורות 'קצרות' (תאים ריקים בסוף מושמטים ב-API): מפתח חסר → "".
    שורה ריקה לחלוטין מדולגת. משמש להפיכת ייצוא-DB ל-db_records ל-dedup.
    """
    if not rows:
        return []
    header = [str(h or "").strip() for h in rows[0]]
    out: list[dict] = []
    for row in rows[1:]:
        if not any(str(c or "").strip() for c in row):
            continue  # שורה ריקה — מדלגים
        rec = {h: (str(row[i]).strip() if i < len(row) and row[i] is not None else "")
               for i, h in enumerate(header) if h}
        out.append(rec)
    return out


def ensure_tab(link_or_id: str, tab: str) -> None:
    """יוצר לשונית אם אינה קיימת (אידמפוטנטי). לא נוגע בלשונית קיימת."""
    sid = extract_id(link_or_id)
    svc = _sheets()
    meta = (
        svc.spreadsheets()
        .get(spreadsheetId=sid, fields="sheets.properties.title")
        .execute()
    )
    titles = {s["properties"]["title"] for s in meta.get("sheets", [])}
    if tab in titles:
        return
    (
        svc.spreadsheets()
        .batchUpdate(
            spreadsheetId=sid,
            body={"requests": [{"addSheet": {"properties": {"title": tab}}}]},
        )
        .execute()
    )


def write_grid(link_or_id: str, tab: str, grid: list[list[str]]) -> int:
    """
    כתיבה אידמפוטנטית של גריד שלם ללשונית: מנקה את הלשונית ואז כותב מ-A1 (RAW).
    ריצה-חוזרת דורסת נקי (אין שיירים משורות ישנות). מחזיר מספר השורות שנכתבו.
    """
    sid = extract_id(link_or_id)
    svc = _sheets()
    svc.spreadsheets().values().clear(spreadsheetId=sid, range=tab, body={}).execute()
    if not grid:
        return 0
    (
        svc.spreadsheets()
        .values()
        .update(
            spreadsheetId=sid,
            range=f"'{tab}'!A1",
            valueInputOption="RAW",
            body={"values": grid},
        )
        .execute()
    )
    return len(grid)


def _sheet_id(link_or_id: str, tab: str) -> int:
    """
    מחזיר את ה-sheetId המספרי (gid) של לשונית. נצרך לבקשות batchUpdate של
    פורמט/RTL שעובדות מול gid (לא מול שם). זורק ValueError אם הלשונית חסרה.
    """
    sid = extract_id(link_or_id)
    meta = (
        _sheets()
        .spreadsheets()
        .get(spreadsheetId=sid, fields="sheets.properties(sheetId,title)")
        .execute()
    )
    for s in meta.get("sheets", []):
        if s["properties"]["title"] == tab:
            return s["properties"]["sheetId"]
    raise ValueError(f"לשונית לא נמצאה: {tab}")


def set_tab_rtl(link_or_id: str, tab: str) -> None:
    """מסמן לשונית ככיוון ימין-לשמאל (rightToLeft), כדי שתיקרא נכון בעברית."""
    sid = extract_id(link_or_id)
    sheet_id = _sheet_id(link_or_id, tab)
    (
        _sheets()
        .spreadsheets()
        .batchUpdate(
            spreadsheetId=sid,
            body={
                "requests": [
                    {
                        "updateSheetProperties": {
                            "properties": {"sheetId": sheet_id, "rightToLeft": True},
                            "fields": "rightToLeft",
                        }
                    }
                ]
            },
        )
        .execute()
    )


# גווני-רקע רכים לצביעת תאים (עקבי עם נורות החיבור green/yellow/red).
_CELL_COLORS = {
    "green":  {"red": 0.78, "green": 0.91, "blue": 0.79},
    "yellow": {"red": 1.00, "green": 0.95, "blue": 0.70},
    "red":    {"red": 0.96, "green": 0.78, "blue": 0.78},
    "orange": {"red": 1.00, "green": 0.80, "blue": 0.40},  # הכרעה-בשילוב — בולט לעין
}


def color_cells(link_or_id: str, tab: str, updates: list[tuple[int, int, str]]) -> int:
    """
    צובע רקע תאים בודדים. updates: רשימת (row0, col0, color) באינדקסים 0-based,
    color אחד מ-{"green","yellow","red"}. צבע לא-מוכר מדולג. updates ריק → 0 ללא קריאה.
    מחזיר את מספר התאים שנצבעו.
    """
    if not updates:
        return 0
    sid = extract_id(link_or_id)
    sheet_id = _sheet_id(link_or_id, tab)
    requests = []
    for row0, col0, color in updates:
        rgb = _CELL_COLORS.get(color)
        if rgb is None:
            continue
        requests.append(
            {
                "repeatCell": {
                    "range": {
                        "sheetId": sheet_id,
                        "startRowIndex": row0,
                        "endRowIndex": row0 + 1,
                        "startColumnIndex": col0,
                        "endColumnIndex": col0 + 1,
                    },
                    "cell": {"userEnteredFormat": {"backgroundColor": rgb}},
                    "fields": "userEnteredFormat.backgroundColor",
                }
            }
        )
    if not requests:
        return 0
    (
        _sheets()
        .spreadsheets()
        .batchUpdate(spreadsheetId=sid, body={"requests": requests})
        .execute()
    )
    return len(requests)


def col_letter(col0: int) -> str:
    """אינדקס עמודה 0-based → אות A1 (0→A, 25→Z, 26→AA)."""
    s, n = "", col0 + 1
    while n > 0:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


# alias פנימי לאחור-תאימות בתוך המודול
_col_letter = col_letter


def write_cells(link_or_id: str, tab: str, updates: list[tuple[int, int, str]]) -> int:
    """
    כתיבה כירורגית של תאים בודדים (לא דורסת תאים אחרים).
    updates: רשימת (row0, col0, value) באינדקסים 0-based. מחזיר מספר התאים שנכתבו.
    """
    if not updates:
        return 0
    sid = extract_id(link_or_id)
    data = [
        {"range": f"'{tab}'!{_col_letter(col0)}{row0 + 1}", "values": [[value]]}
        for row0, col0, value in updates
    ]
    (
        _sheets()
        .spreadsheets()
        .values()
        .batchUpdate(spreadsheetId=sid, body={"valueInputOption": "RAW", "data": data})
        .execute()
    )
    return len(data)


def extract_id(link_or_id: str) -> str:
    """מחלץ מזהה גיליון מקישור מלא, או מחזיר את הקלט כמו שהוא."""
    match = re.search(r"/d/([a-zA-Z0-9_-]+)", link_or_id or "")
    return match.group(1) if match else (link_or_id or "").strip()


def check_access(link_or_id: str) -> AccessResult:
    """בודק בפועל אם ה-service account ניגש לגיליון, ובאיזו רמה."""
    file_id = extract_id(link_or_id)
    if not file_id:
        return AccessResult(ok=False, name=None, can_edit=False, error="קישור ריק")
    try:
        f = (
            _drive()
            .files()
            .get(fileId=file_id, fields="name,capabilities(canEdit)", supportsAllDrives=True)
            .execute()
        )
        return AccessResult(ok=True, name=f.get("name"), can_edit=bool(f["capabilities"]["canEdit"]))
    except Exception as e:  # noqa: BLE001 — כל כשל = אין גישה, מדווח למשתמש
        return AccessResult(ok=False, name=None, can_edit=False, error=f"{type(e).__name__}: {e}")


def connection_status(link_or_id: str, needs_write: bool) -> ConnectionStatus:
    """
    מתרגם בדיקת גישה לסטטוס נורית, לפי הרמה הנדרשת:
      - אין גישה            -> 🔴
      - צריך כתיבה ואין      -> 🔴
      - צריך כתיבה ויש       -> 🟢
      - צריך קריאה ויש כתיבה -> 🟡 (עודף הרשאה)
      - צריך קריאה ויש קריאה -> 🟢
    """
    if not (link_or_id or "").strip():
        return ConnectionStatus(color="red", message="לא הוזן קישור")

    result = check_access(link_or_id)
    if not result.ok:
        return ConnectionStatus(
            color="red",
            message=f"אין גישה — שתף עם {service_account_email()}",
        )

    if needs_write:
        if result.can_edit:
            return ConnectionStatus(color="green", message="גישת Editor — מוכן", name=result.name)
        return ConnectionStatus(
            color="red", message="צריך הרשאת Editor (כרגע קריאה בלבד)", name=result.name
        )

    # צריך קריאה בלבד
    if result.can_edit:
        return ConnectionStatus(
            color="yellow", message="עודף הרשאה — מספיק Viewer לבטיחות", name=result.name
        )
    return ConnectionStatus(color="green", message="גישת Viewer — מוכן", name=result.name)
