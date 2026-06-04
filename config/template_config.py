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

# שם לשונית הטמפלייט שממנה קוראים (ספציפי-לטמפלייט).
TEMPLATE_TAB = "טמפלייט טעינה"

# מבנה שורות-הכותרת של "טמפלייט טעינה" (אינדקס שורה, 0-based).
# 4 שורות כותרת ואז דאטה. ספציפי-לטמפלייט — לכן כאן ולא במנוע.
TEMPLATE_BLOCK_ROW = 0       # כותרות בלוקים (קיבוץ לאובייקט; תאים ממוזגים/דלילים)
TEMPLATE_HELP_ROW = 1        # טקסט הסבר/הנחיה — לא משמש למיפוי
TEMPLATE_LABEL_ROW = 2       # שם העמודה בעברית (תווית אנושית)
TEMPLATE_API_ROW = 3         # שם שדה ה-API בסיילספורס (המיפוי המוצע)
TEMPLATE_DATA_START_ROW = 4  # השורה הראשונה של דאטה אמיתית

# מיפוי בלוק→אובייקט SF (ברירת מחדל; ה-UI של שלב 2 יאפשר לתקן).
BLOCK_TO_OBJECT: dict[str, str] = {
    "פרטי איש הקשר ראשי": "Contact",
    "פרטי האירוע": "Campaign",
    "עבור איש קשר נוסף שמקושר לראשון (בן/בת זוג, ילד/ה..)": "Contact",
}

# עמודות נודדות: תווית-עמודה → אובייקט, גובר על ברירת-המחדל של הבלוק.
# מזוהה לפי תווית כדי לתפוס את אותו שדה בשני בלוקי איש-הקשר במכה אחת.
WANDERING_OVERRIDES: dict[str, str] = {
    "סטטוס השתתפות": "CampaignMember",
    "משתתף באירוע": "CampaignMember",
    "מחיר כרטיס ליחיד": "CampaignMember",  # מחיר לכל משתתף (רק כש"משתתף באירוע"=TRUE)
    "סוג הקשר": "npe4__Relationship__c",
}

# עמודות-בקרה: דגלים שמכתיבים לוגיקה (נצרכים ע"י ה-splitter) אך אינם נטענים כשדה.
CONTROL_COLUMNS: set[str] = {
    "משתתף באירוע",  # TRUE/FALSE — האם ליצור CampaignMember עבור איש הקשר בשורה
}

# מנגנוני זיהוי (v1): מורכבים עבור אובייקט אחד בלבד; קמפיינים מזוהים בנפרד לפי שם.
IDENTITY_OBJECT = "Contact"
# שדה ת"ז — ברירת-המחדל למנגנון 1 (אם קיים במאגר השדות התקפים).
DEFAULT_IDENTITY_FIELD = "ID_Number__c"

# שדות שמנורמלים ל"ספרות-בלבד" לצורך התאמת-dedup (פנימי בלבד — לא נוגע בדאטה הנטענת).
# מקפים/רווחים/קידומות בטלפון ובת"ז לא יפילו התאמה. ניתן להרחבה.
DIGITS_ONLY_FIELDS: set[str] = {
    "ID_Number__c",
    "MobilePhone",
}

# שמות לשוניות בגיליון ה-DB לכל אובייקט (מה שהמשתמש צריך ליצור ב-Inspector).
# אובייקטים שאינם ברשימה → fallback = שם ה-API עצמו.
DB_TAB_NAMES: dict[str, str] = {
    "Contact":               "Contact",
    "Campaign":              "Campaign",
    "CampaignMember":        "CampaignMember",
    "npe4__Relationship__c": "npe4__Relationship__c",
}

# לשוניות-פלט שהכלי כותב לתוך הטמפלייט עצמו (אפשרות א' — הטמפלייט כבר משותף כ-Editor).
# גריד מוכן-לטעינה: עמודות-מטא + שדות, שורה לכל אדם. ריצה-חוזרת דורסת נקי.
OUTPUT_TAB_CONTACTS = "פלט - Contacts"
# לשונית "טיפול ידני": רשומות דו-משמעיות/ללא-זיהוי שלא נכנסו לטעינה — רשומת-הקלט
# לצד מועמדי-המאגר, עם עמודת "בחר" שהמשתמש מסמן בה את הנכונה (פרוסה 8).
OUTPUT_TAB_MANUAL_CONTACTS = "טיפול ידני - Contacts"

# ===== Relationships (שלב 5 חלק ג') =====
# קשרים הם גיליון נגזר: לכל שורה עם שני אנשי-קשר (ראשי + נוסף) נגזר קשר אחד.
# כיוון אחד בלבד — NPSP יוצר את ההפוך אוטומטית. רק זוגות חדשים נכנסים לפלט.
RELATIONSHIP_OBJECT = "npe4__Relationship__c"
RELATIONSHIP_CONTACT_A_FIELD = "npe4__Contact__c"
RELATIONSHIP_CONTACT_B_FIELD = "npe4__RelatedContact__c"
RELATIONSHIP_TYPE_FIELD = "npe4__Type__c"
# שמות הבלוקים (חייב להיות זהה לשמות ב-BLOCK_TO_OBJECT).
CONTACT_BLOCK_PRIMARY = "פרטי איש הקשר ראשי"
CONTACT_BLOCK_SECONDARY = "עבור איש קשר נוסף שמקושר לראשון (בן/בת זוג, ילד/ה..)"
OUTPUT_TAB_RELATIONSHIPS = "פלט - Relationships"

# ===== CampaignMember (שלב 5 חלק ד') =====
# v1: טוען את כולם ללא בדיקת-קיום מול DB (מוסכם בתוכנית).
CM_OBJECT = "CampaignMember"
CM_CONTACT_ID_FIELD = "ContactId"    # שדה lookup סטנדרטי (נגזר, לא מה-mapper)
CM_CAMPAIGN_ID_FIELD = "CampaignId"  # שדה lookup סטנדרטי (נגזר, לא מה-mapper)
CM_PARTICIPATING_LABEL = "משתתף באירוע"  # תווית עמודת-הבקרה (STATUS_CONTROL)
OUTPUT_TAB_CM = "פלט - CampaignMember"

# ===== Campaigns (שלב 5 חלק ב') =====
# קמפיינים אינם משתמשים במנגנוני-הזיהוי של Contacts — הם מזוהים לפי **שם** בלבד
# (מנורמל: חיתוך רווחים, casefold — דרך identity.normalize). אותו מנוע dedup גנרי.
CAMPAIGN_OBJECT = "Campaign"
# שדה ה-dedup לקמפיינים. חייב להתאים ל-clean_api שה-mapper מייצר לעמודת שם-הקמפיין.
CAMPAIGN_NAME_FIELD = "Name"
# מנגנון יחיד לפי שם — הקלט ל-dedup_engine.deduplicate עבור קמפיינים.
CAMPAIGN_MECHANISMS: list[list[str]] = [[CAMPAIGN_NAME_FIELD]]
# לשוניות-פלט לקמפיינים (בתוך הטמפלייט, כמו Contacts).
OUTPUT_TAB_CAMPAIGNS = "פלט - Campaigns"
OUTPUT_TAB_MANUAL_CAMPAIGNS = "טיפול ידני - Campaigns"

# ===== ולידציה (שלב 6) =====
# לשונית שאליה נכתבת רשימת הבעיות (מיפוי/תאריכים/אורך-Id) לפני בנייה/טעינה.
OUTPUT_TAB_ISSUES = "בעיות"
