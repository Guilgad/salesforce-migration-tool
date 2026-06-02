"""
לוגיקה ספציפית-ללקוח, מבודדת מהמנוע הגנרי.

v1 נסגר על טמפלייט "מחנה פסח". כל מה שהוא ספציפי-ללקוח יושב כאן בלבד —
המנוע (modules/) נשאר גנרי. הכללה אמיתית רק כשיגיע לקוח שני.
"""
from __future__ import annotations

# אובייקטי ברירת-המחדל לשאילתת מילון השדות (שלב 1). ניתן לעריכה ב-UI.
DEFAULT_OBJECTS: list[str] = [
    "Contact",
    "Campaign",
    "npe4__Relationship__c",
    "CampaignMember",
]
