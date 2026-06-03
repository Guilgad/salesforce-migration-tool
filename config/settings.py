"""הגדרות גלובליות של הכלי."""
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# מפתח ה-service account (ב-.gitignore, לעולם לא ב-git)
CREDENTIALS_FILE = PROJECT_ROOT / "credentials.json"

# זיכרון מקומי של גיליונות אחרונים (MRU) — נתוני-ריצה, ב-.gitignore
RECENT_SHEETS_FILE = PROJECT_ROOT / ".recent_sheets.json"

# הרשאות: כתיבה/קריאה של גיליונות + קריאת capabilities (canEdit) לבדיקת הגישה
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.metadata.readonly",
]
