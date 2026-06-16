# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project state

The tool is **functionally complete for v1**. Full source code exists under `main.py`, `config/`, and `modules/`. Do not re-enter planning mode unless the user explicitly asks to redesign a feature. New work = implement directly, following the patterns already in the codebase.

Planning docs live in `planning/` (Obsidian notes); settings notes live in `Settings/`. Project planning documents are written in Hebrew. The user is a Salesforce implementer (not a developer) — keep explanations plain and concise.

## What the tool does

A Streamlit wizard that turns a customer's raw data (Google Sheets) into Salesforce-ready load sheets, with dedup and insert/upsert decisions baked in. Key design constraints:

- **No direct Salesforce connection.** Everything flows through files. Salesforce data comes in via exports (Google Sheets), and the tool's output is a Google Sheet the user loads manually via Salesforce Inspector.
- **Google Sheets is the only I/O surface.** Inputs and outputs are all Sheets, accessed via the Sheets API with a service account.
- **Generic and modular.** The tool must not assume any specific customer schema; column-to-field mapping is data-driven via the template sheet.

## Architecture (implemented)

**Inputs (3 Google Sheets)**
1. Customer template Sheet — raw data + header rows with block/label/API-name structure
2. FieldDefinition SOQL export Sheet — produced by running a generated query in Salesforce Inspector
3. DB export Sheet — existing Salesforce records for upsert-vs-insert decisions

**Module layout**
```
main.py                          # Streamlit wizard — all UI screens
config/
  settings.py                    # paths, filenames
  template_config.py             # template-specific constants (objects, rows, blocks, etc.)
modules/
  sheets_io.py                   # Google Sheets read/write (API wrapper)
  query_builder.py               # Step 0: FieldDefinition SOQL builder
  field_dictionary.py            # Step 2: parse SOQL result → field dict
  mapper.py                      # Steps 2–3: column extraction, object assignment, validation
  identity.py                    # identity key computation (multi-mechanism, ranked)
  splitter.py                    # split template rows into per-object records
  dedup_engine.py                # internal dedup + DB cross-reference (insert/upsert/ambiguous)
  output_writer.py               # build load grids (Contacts, Campaigns, manual)
  relationship_builder.py        # derive & dedup bidirectional relationships
  campaign_member_builder.py     # derive CampaignMember records from control column
  formatter.py                   # text normalisation + date parsing
  validator.py                   # data validation (dates, Id length)
  recent_sheets.py               # MRU list of recently used sheets per role
  notes_store.py                 # persist user notes across sessions (.notes.txt)
tests/                           # pytest suite (engine units + v2 integration)
```

## Testing contract (v2) — חובה

חוק-ברזל שנלמד בדם (באג ה-`db_tabs`/`extra_fields`): בדיקות-יחידה על פונקציות-טהורות עם
נתונים-מוזנים-ביד **אינן** מוכיחות שהאפליקציה עובדת. הן עברו ירוקות בעוד הצלבת-ה-DB וה-extra_fields
היו מתים לגמרי, כי אף בדיקה לא הריצה את שכבת-החיווט (UI→schema→מנועים).

- **כל פיצ'ר/חיווט חדש שמשפיע על הבנייה → חייב בדיקת-אינטגרציה** שבונה `RuntimeSchema` כמו ה-UI
  (mappings/identity/db_tabs/lookups/...) ומריצה את `orchestrator.build_object_core`, ובודקת את
  **הפלט** (insert/upsert/backfill/עמודה-נגזרת) — לא רק "אין חריגה". ראה `tests/test_v2_pipeline_e2e.py`.
- `orchestrator.build_object_core` הוא ה-seam הטהור (ללא Streamlit) לבדיקות כאלה. אם לוגיקה חדשה
  חיה רק ב-`main.py`, חלץ את הליבה לשם כדי שתהיה ניתנת-לבדיקה.
- בדיקות "renders_without_exception" מרוכזות ב-`tests/test_v2_screens_smoke.py` בלבד (גלאי-קריסות).
  אל תוסיף עוד כאלה פר-מסך — הן ביטחון-שווא.

## שיטת-עבודה (v2) — ברירת-מחדל מחייבת

ארבעה כללים שננעלו אחרי ניתוח "למה v2 כל-הזמן נשבר" (פירוט ב-memory `working-method`):

1. **"ירוק ≠ גמור".** לא להכריז "הושלם" עד בדיקת-תפר (אינטגרציה דרך `build_object_core`/AppTest שבודקת
   פלט) **וגם** אימות-חי לעבודת-UI. pytest ירוק לבדו אינו עדות.
2. **פרוסות-קטנות + אימות אחרי כל אחת** — לא לצבור צעדים ואז לבדוק.
3. **מקור-אמת יחיד למזהים-משותפים** — שם-אובייקט/שדה שחי בשני מקורות (כותרת-לקוח מול מילון-SF) חייב
   להיקאנן בגבול אחד. שורש משפחת באגי-ה-case. בכל הוספה — לשאול "איפה מקור-האמת היחיד?".
4. **דוגמת-דאטה אמיתית לפני בניית-חיווט** — בונים מול מציאות, לא מול הנחות.

הוק מקומי `.claude/hooks/pytest_on_py_change.py` (ב-`settings.local.json`, gitignored) מריץ pytest
אוטומטית כשנגעת ב-`.py` ומקפיץ כשל — רשת-בטיחות מכנית, לא-חוסמת (לא נלחמת ב-TDD).

**Wizard navigation (main.py)** — top process-bar `_topbar()` with 5 steps (click to navigate via
`st.session_state["step"]`); per-step live status badges via `_set_status`/`_status_badge`. The
sidebar is slim (refresh buttons + personal notes only). Steps 4–5 bundle two builders each, switched
by a horizontal `st.radio` sub-nav (not `st.tabs` — avoids running both pipelines). Step model = `STEPS`.

1. חיבור + שאילתות — `screen_step1`: connect 3 sheets + query builder (`screen_queries`: dropdown over
   FieldDefinition + per-object DB-export queries, editable before copy) + DB check (`screen_db_validation`)
2. מיפוי (column mapping with inline edit)
3. מנגנוני זיהוי (identity mechanisms — up to `_N_MECHANISMS`=5)
4. גיליונות ראשיים — sub-nav: Contacts | Campaigns
5. גיליונות מותנים — sub-nav: Relationships | CampaignMembers

## Google credentials

- `credentials.json` is a Google Cloud service-account key for project `sheets-automation-497917`. **It must never be committed.** Already in `.gitignore`.
- Service-account email: `python-worker@sheets-automation-497917.iam.gserviceaccount.com` (see `Settings/Google Service Account.md`). Every Sheet the tool needs to read or write must be shared with this address as **Editor**. Mention this to the user any time a new Sheet is introduced — it's the most common foot-gun.
- Sheets API is already enabled on the GCP project.

## Git workflow (agreed with user)

Commit at **logical milestones** — each module or fix that has passed the user's review — **never on a timer**. At each such checkpoint, **proactively propose** the commit ("we finished X, worth committing — approve?") and commit only after the user says yes. Do not auto-commit silently, and do not commit mid-work. Pushing stays manual / on request.

**Remote:** `https://github.com/Guilgad/salesforce-migration-tool.git` (origin/main).
If `git remote -v` returns empty, run: `git remote add origin https://github.com/Guilgad/salesforce-migration-tool.git`

## Known limitations (v1, deferred)

- False-positive 🔴 on compound fields (FirstName/LastName, Mailing/Other address components) — not returned by FieldDefinition but valid for loading. Mitigated by `KNOWN_STANDARD_FIELDS` allowlist in `mapper.py`.
- No 15→18 Salesforce Id conversion (validator warns on Id length ≠ 18).
- Identity mechanisms for Contacts only; Campaigns identified by name only.
