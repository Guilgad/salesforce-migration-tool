"""
בדיקת גישה זעירה: האם ה-service account (מתוך credentials.json) רואה את הגיליונות?
מדווח לכל גיליון: שם ורמת גישה (Editor=כתיבה / Viewer=קריאה בלבד), או "אין גישה".

התקנה (פעם אחת):
    pip install google-api-python-client google-auth

הרצה:
    python check_access.py <קישור-או-id> [עוד קישורים...]
"""
import re
import sys

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

# ודא הדפסת עברית/יוניקוד גם ב-console של Windows
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

CREDENTIALS_FILE = "credentials.json"
SCOPES = ["https://www.googleapis.com/auth/drive.metadata.readonly"]


def extract_id(link_or_id: str) -> str:
    """מחלץ את מזהה הגיליון מקישור מלא, או מחזיר את הקלט כמו שהוא אם זה כבר id."""
    match = re.search(r"/d/([a-zA-Z0-9_-]+)", link_or_id)
    return match.group(1) if match else link_or_id


def main(links: list[str]) -> None:
    creds = Credentials.from_service_account_file(CREDENTIALS_FILE, scopes=SCOPES)
    drive = build("drive", "v3", credentials=creds)
    sa_email = creds.service_account_email
    print(f"Service account: {sa_email}\n")

    for link in links:
        file_id = extract_id(link)
        try:
            f = (
                drive.files()
                .get(fileId=file_id, fields="name,capabilities(canEdit)", supportsAllDrives=True)
                .execute()
            )
        except Exception as e:
            print(f"[אין גישה]  {file_id}  ->  שתף עם {sa_email}  ({type(e).__name__})")
            continue

        level = "Editor (כתיבה)" if f["capabilities"]["canEdit"] else "Viewer (קריאה בלבד)"
        print(f"[יש גישה]   {f['name']}  ->  {level}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("שימוש: python check_access.py <קישור-או-id> [עוד קישורים...]")
        sys.exit(1)
    main(sys.argv[1:])
