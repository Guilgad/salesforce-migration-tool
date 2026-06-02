---
title: Google Service Account
date: 2026-05-31
tags:
  - הגדרות
  - google-cloud
  - credentials
---

# Google Service Account

> [!danger] אבטחה
> קובץ `credentials.json` **לעולם** לא יועלה ל-GitHub. הוא נמצא ב-`.gitignore`.

## פרטי החשבון

| שדה        | ערך                                                              |
| ---------- | ---------------------------------------------------------------- |
| פרויקט GCP | `sheets-automation-497917`                                       |
| שם החשבון  | `python-worker`                                                  |
| מייל       | `python-worker@sheets-automation-497917.iam.gserviceaccount.com` |
| API מופעל  | Google Sheets API                                                |

## איך לשתף Sheet עם הכלי

> [!important] חובה לכל Sheet חדש
> כל Google Sheet שהכלי צריך לקרוא או לכתוב אליו **חייב** להיות משותף עם כתובת המייל הזו כ-**Editor**.

כתובת לשיתוף:
```
python-worker@sheets-automation-497917.iam.gserviceaccount.com
```

### שלבים:
1. פתח את ה-Google Sheet
2. לחץ **Share**
3. הדבק את כתובת המייל
4. בחר **Editor**
5. בטל את "Notify people"
6. לחץ **Share**

## קבצים קשורים

- `credentials.json` — קובץ המפתח (בתיקיית הפרויקט, לא ב-git)
- ראה [[תוכנית פיתוח#קבצי קלט]] לרשימת כל ה-Sheets הנדרשים
