"""qa_run.py — מנוע QA מקצה-לקצה לפי planning/בדיקות-QA.md.

משחזר במדויק את הצינור של כל מסך (אותן פונקציות-מודול ש-main.py קורא), מזריק את
נתוני-הדמה D1–D14 *מתחת* לדאטה האמיתית בלשונית "טמפלייט טעינה", ומאמת כל בדיקה.

כלי-עזר חד-פעמי (כמו qa_e2e.py) — לא חלק מהכלי. לא מוחק נתונים אמיתיים.

הרצה:  python qa_run.py            # כל הפאזות + כתיבת דוח
       python qa_run.py write      # רק כתיבת D1-D14
       python qa_run.py contacts   # פאזה בודדת (write,contacts,campaigns,rel,cm,validation)
"""
from __future__ import annotations

import sys
from collections import defaultdict

sys.stdout.reconfigure(encoding="utf-8")

from config import template_config as T
from modules import (
    sheets_io, field_dictionary, mapper, splitter, dedup_engine, output_writer,
    relationship_builder, campaign_member_builder, validator, formatter, identity,
)

TPL = "1K9ZtCe14IOt5KTOaJVCan-5iWD1NeHjM-PixH1J8LiQ"
DB = "1aauowFwIV6wpYYR9WU9BJBcv7ehEj7otkbUbKSLS6wU"
SOQL = "1gtWdPGep5-5nA3Gq6880itaLo01M2cf73peJLGmzSBo"

# מנגנוני-זיהוי לפי מסמך ה-QA: 1=ת"ז, 2=שם-משפחה+טלפון, 3=טלפון.
# (מנגנון 3 נחוץ לשרשרת D4↔D5 שמתמזגת לפי טלפון בלבד — ראה דיווח QA-3/5.4.)
MECHS = [["ID_Number__c"], ["LastName", "MobilePhone"], ["MobilePhone"]]

BLOCK_P = T.CONTACT_BLOCK_PRIMARY     # "פרטי איש הקשר ראשי"
BLOCK_S = T.CONTACT_BLOCK_SECONDARY   # בלוק איש-קשר נוסף

# אינדקסי-עמודה (0-based) בלשונית "טמפלייט טעינה"
P_FIRST, P_LAST, P_KIRBA, P_PHONE, P_EMAIL, P_ID, P_BDATE = 2, 3, 4, 5, 6, 7, 8
P_PARTSTATUS, P_PART = 12, 13
C_NAME, C_AMT, C_START, C_END, C_TYPE, C_STATUS = 15, 16, 17, 18, 19, 20
S_FIRST, S_LAST, S_PHONE, S_ID, S_PART, S_TYPE = 22, 23, 25, 27, 33, 34

DATA_START = T.TEMPLATE_DATA_START_ROW  # 4
DUMMY_START_ROW0 = 13  # שורה 14 בגיליון — מתחת לדאטה האמיתית (רואים 9 שורות אמת 4..12)

# כל העמודות שננקה/נכתוב בבלוק-הדמה (כדי שכתיבה-חוזרת תהיה אידמפוטנטית)
USED_COLS = [P_FIRST, P_LAST, P_KIRBA, P_PHONE, P_EMAIL, P_ID, P_BDATE, P_PARTSTATUS,
             P_PART, C_NAME, C_AMT, C_START, C_END, C_TYPE, C_STATUS,
             S_FIRST, S_LAST, S_PHONE, S_ID, S_PART, S_TYPE]

# ===== נתוני-הדמה D1–D14 (col_index -> value) =====
DUMMY = {
    "D1":  {P_FIRST: "דמה", P_LAST: "אחד", P_ID: "999000001", P_PHONE: "050-1111111",
            P_BDATE: "28.07.2025", P_PART: "TRUE", C_NAME: "קמפיין QA 1",
            S_FIRST: "דמה", S_LAST: "שתיים", S_ID: "999000002", S_PHONE: "050-2222222",
            S_TYPE: "Spouse", S_PART: "TRUE"},
    "D2":  {P_FIRST: "דמה", P_LAST: "אחד", P_ID: "999000001", P_PHONE: "050-9999999",
            P_PART: "FALSE", C_NAME: "קמפיין QA 1"},
    "D3":  {P_FIRST: "דמה", P_LAST: "אחד", P_PHONE: "050-1111111", P_PART: "TRUE",
            C_NAME: "קמפיין QA 2", S_FIRST: "דמה", S_LAST: "שלוש", S_ID: "999000003",
            S_PHONE: "050-3333333", S_TYPE: "Child", S_PART: "FALSE"},
    "D4":  {P_FIRST: "דמה", P_LAST: "ארבע", P_ID: "999000001", P_PHONE: "050-5555555",
            P_PART: "TRUE", C_NAME: "קמפיין QA 1"},
    "D5":  {P_FIRST: "דמה", P_LAST: "חמש", P_ID: "999000099", P_PHONE: "050-5555555",
            P_PART: "FALSE"},
    "D6":  {P_FIRST: "דמה", P_LAST: "שש", P_ID: "311045884", P_PHONE: "050-6666666",
            P_PART: "TRUE", C_NAME: "קמפיין QA 2"},
    "D7":  {P_FIRST: "ענבר", P_LAST: "אורבך", P_PHONE: "546925735", P_PART: "FALSE"},
    "D8":  {P_FIRST: "דמה", P_LAST: "שמונה", P_ID: "15262918", P_PHONE: "050-8888888",
            P_PART: "FALSE"},
    "D9":  {P_FIRST: "דמה", P_LAST: "תשע", P_PART: "TRUE", C_NAME: "קמפיין QA 3"},
    "D10": {P_FIRST: "דמה", P_LAST: "עשר", P_ID: "999000010", P_PHONE: "050-1010101",
            P_BDATE: "31-13-2000", P_PART: "FALSE"},
    "D11": {P_FIRST: "אסתי", P_LAST: "יניב", P_ID: "26619478", P_PHONE: "050-1100000",
            P_PART: "FALSE", S_FIRST: "קמה", S_LAST: "יניב", S_ID: "221062508",
            S_PHONE: "050-1200000", S_TYPE: "Spouse", S_PART: "FALSE"},
    "D12": {C_NAME: "קמפיין  QA  1 "},  # כפילות-שם + נירמול רווחים (כפול/קצוות)
    "D13": {C_NAME: "יום טרפיה ים המלח -פצועים"},  # קמפיין קיים ב-DB → Upsert
    "D14": {S_FIRST: "דמה", S_LAST: "ארבע-עשר", S_ID: "999000014", S_PHONE: "050-1414141",
            S_TYPE: "Friend"},
}
DKEYS = [f"D{i}" for i in range(1, 15)]
ROW_OF = {k: DUMMY_START_ROW0 + i for i, k in enumerate(DKEYS)}  # D1->13 ... D14->26


def fake_id(local_key: str) -> str:
    """Id סינתטי 18-תווים לדמיית הדבקה-חזרה אחרי טעינה (insert ללא Id אמיתי)."""
    return ("FAKE" + local_key).ljust(18, "0")[:18]


# ---------- תשתית ----------
def run_mapping():
    dict_rows = sheets_io.read_values(SOQL, None)
    parsed = field_dictionary.parse_field_dictionary(dict_rows, T.DEFAULT_OBJECTS)
    tmpl = sheets_io.read_values(TPL, T.TEMPLATE_TAB)
    cols = mapper.extract_columns(tmpl, block_row=T.TEMPLATE_BLOCK_ROW,
                                  label_row=T.TEMPLATE_LABEL_ROW, api_row=T.TEMPLATE_API_ROW)
    mapper.assign_objects(cols, T.BLOCK_TO_OBJECT, T.WANDERING_OVERRIDES)
    mapper.validate_columns(cols, parsed.objects, control_columns=T.CONTROL_COLUMNS)
    return cols, parsed.objects


def person_for(dedup, split_records, source_row, block):
    """מחזיר את ה-PersonResult שמכיל את רשומת (source_row, block), או None."""
    target = None
    for i, rec in enumerate(split_records):
        if rec.source_row == source_row and rec.block == block:
            target = i
            break
    if target is None:
        return None
    for p in dedup.persons:
        if target in p.record_indices:
            return p
    return None


# ---------- אוסף-תוצאות ----------
RESULTS = []  # (test_id, ok, expected, got, note)


def check(tid, ok, expected, got, note=""):
    RESULTS.append((tid, bool(ok), str(expected), str(got), note))
    mark = "PASS" if ok else "FAIL"
    print(f"  [{mark}] {tid}: expected={expected} | got={got}" + (f" | {note}" if note else ""))


# ================= פאזה: כתיבת D1-D14 =================
def phase_write():
    print("== כתיבת נתוני-הדמה D1–D14 ==")
    updates = []
    for k in DKEYS:
        r = ROW_OF[k]
        vals = DUMMY[k]
        for col in USED_COLS:
            updates.append((r, col, vals.get(col, "")))
    n = sheets_io.write_cells(TPL, T.TEMPLATE_TAB, updates)
    print(f"  נכתבו {n} תאים בשורות {DUMMY_START_ROW0+1}–{DUMMY_START_ROW0+14} (1-based).")
    # אימות קריאה-חזרה
    rows = sheets_io.read_values(TPL, T.TEMPLATE_TAB)
    check("SETUP-rows", len(rows) >= DUMMY_START_ROW0 + 14, ">=27 rows", len(rows))
    check("SETUP-D1", sheets_io._col_letter and rows[13][P_ID] == "999000001",
          "999000001 @H14", rows[13][P_ID] if len(rows[13]) > P_ID else "")
    return rows


# ================= פאזה: Contacts =================
def build_contacts(cols, dictionary):
    tmpl = sheets_io.read_values(TPL, T.TEMPLATE_TAB)
    split = splitter.split_object("Contact", tmpl, cols, data_start_row=DATA_START)
    rv = [r.values for r in split]
    src = [r.source_row for r in split]
    db_rows = sheets_io.read_values(DB, T.DB_TAB_NAMES["Contact"])
    db_records = sheets_io.rows_to_dicts(db_rows)
    db_by_id = {r["Id"]: r for r in db_records if r.get("Id")}
    dedup = dedup_engine.deduplicate(rv, MECHS, db_records,
                                     digits_only_fields=T.DIGITS_ONLY_FIELDS)
    grid, colors = output_writer.build_contacts_grid(dedup, rv, cols, db_by_id)
    manual, mcolors = output_writer.build_manual_grid(
        dedup, rv, cols, db_by_id, src, digits_only_fields=T.DIGITS_ONLY_FIELDS)
    return dict(tmpl=tmpl, split=split, rv=rv, src=src, db_by_id=db_by_id,
                dedup=dedup, grid=grid, colors=colors, manual=manual, mcolors=mcolors,
                dictionary=dictionary, cols=cols)


def phase_contacts(cols, dictionary, write_output=True):
    print("== Contacts (מסך 5) ==")
    ctx = build_contacts(cols, dictionary)
    dedup, split, grid = ctx["dedup"], ctx["split"], ctx["grid"]

    pX = person_for(dedup, split, ROW_OF["D1"], BLOCK_P)  # קבוצת השרשרת D1-D5
    # QA-5.1: D1 ראשי = Insert, Id ריק (הקבוצה לא ב-DB)
    check("QA-5.1", pX and pX.action == dedup_engine.ACTION_INSERT and not pX.sf_id,
          "Insert + Id ריק", f"{pX.action if pX else None}/{pX.sf_id if pX else None}")

    # QA-5.2: D1+D2 באותה קבוצה (כפילות ת"ז)
    src_rows = {split[i].source_row for i in pX.record_indices if split[i].block == BLOCK_P} if pX else set()
    check("QA-5.2", {ROW_OF["D1"], ROW_OF["D2"]} <= src_rows,
          "D1,D2 מאוחדים", sorted(src_rows))
    # QA-5.3: D1+D3 מאוחדים (שם+טלפון). הערה: __נמצא_לפי ריק כי הקבוצה Insert (לא Upsert מול DB)
    found_text, _ = output_writer._found_by_cell(pX) if pX else ("", None)
    check("QA-5.3", ROW_OF["D3"] in src_rows,
          "D3 מאוחד עם D1", ROW_OF["D3"] in src_rows,
          note=f"__נמצא_לפי='{found_text}' (ריק — הקבוצה Insert; ראה דיווח)")
    # QA-5.4: שרשרת D1+D4+D5 (ת"ז+טלפון) — כולם בקבוצה אחת
    check("QA-5.4", {ROW_OF["D4"], ROW_OF["D5"]} <= src_rows,
          "D4,D5 בשרשרת אחת", sorted(src_rows))

    # QA-5.5: D6 Upsert לפי מנגנון 1
    p6 = person_for(dedup, split, ROW_OF["D6"], BLOCK_P)
    t6, c6 = output_writer._found_by_cell(p6) if p6 else ("", None)
    check("QA-5.5", p6 and p6.action == dedup_engine.ACTION_UPSERT and p6.found_by == 0,
          "Upsert + מנגנון 1", f"{p6.action if p6 else None}/found_by={p6.found_by if p6 else None}",
          note=f"Id={p6.sf_id if p6 else None}, תא='{t6}'({c6})")
    # QA-5.6: D7 Upsert לפי מנגנון 2
    p7 = person_for(dedup, split, ROW_OF["D7"], BLOCK_P)
    t7, c7 = output_writer._found_by_cell(p7) if p7 else ("", None)
    check("QA-5.6", p7 and p7.action == dedup_engine.ACTION_UPSERT and p7.found_by == 1,
          "Upsert + מנגנון 2", f"{p7.action if p7 else None}/found_by={p7.found_by if p7 else None}",
          note=f"Id={p7.sf_id if p7 else None}, תא='{t7}'({c7})")
    # QA-5.7: Backfill — שדה ריק בקלט מתמלא מה-DB ב-Upsert (D6: Email)
    db6 = ctx["db_by_id"].get(p6.sf_id, {}) if p6 and p6.sf_id else {}
    # מצא שורת-פלט של D6
    out_email = None
    api_row = grid[1]
    email_col = api_row.index("Email") if "Email" in api_row else None
    lk_col = 0
    for row in grid[2:]:
        if p6 and row[lk_col] == p6.local_key:
            out_email = row[email_col] if email_col is not None and email_col < len(row) else ""
            break
    backfilled = bool(db6.get("Email")) and out_email == str(db6.get("Email")).strip()
    check("QA-5.7", backfilled or (not db6.get("Email")),
          "Email מ-DB ממולא", f"out={out_email!r} db={db6.get('Email')!r}",
          note="(אם ל-DB אין Email — אין מה למלא)")

    # QA-5.8: D8 ambiguous — לא בפלט, בטיפול ידני עם מועמדים
    p8 = person_for(dedup, split, ROW_OF["D8"], BLOCK_P)
    in_main = any(r[lk_col] == (p8.local_key if p8 else None) for r in grid[2:])
    check("QA-5.8", p8 and p8.ambiguous and len(p8.match_ids) >= 2 and not in_main,
          "ambiguous + >=2 מועמדים + לא בפלט",
          f"ambiguous={p8.ambiguous if p8 else None} ids={len(p8.match_ids) if p8 else 0} in_main={in_main}")
    # QA-5.9: D9 unkeyed
    p9 = person_for(dedup, split, ROW_OF["D9"], BLOCK_P)
    in_main9 = any(r[lk_col] == (p9.local_key if p9 else None) for r in grid[2:])
    check("QA-5.9", p9 and p9.unkeyed and not in_main9,
          "unkeyed + לא בפלט", f"unkeyed={p9.unkeyed if p9 else None} in_main={in_main9}")

    # QA-5.12: ולידציית תאריך שגוי (D10 Birthdate=31-13-2000)
    issues, marks = validator.validate_output_grid(grid, "Contact", dictionary)
    bad_dates = [i for i in issues if i.kind == validator.KIND_BAD_DATE]
    d10_flagged = any("31-13-2000" in i.message for i in bad_dates)
    check("QA-5.12", d10_flagged, "תאריך D10 מסומן", f"{len(bad_dates)} תאריכים שגויים")
    # QA-5.13: ולידציה נקייה — שאר התאריכים תקינים (רק D10 שגוי)
    check("QA-5.13", len(bad_dates) == 1, "רק שגיאת-תאריך אחת (D10)",
          f"{len(bad_dates)} שגיאות", note="; ".join(i.location for i in bad_dates))

    # QA-5.11: אידמפוטנטיות — בנייה חוזרת מחזירה גריד זהה
    ctx2 = build_contacts(cols, dictionary)
    check("QA-5.11", ctx2["grid"] == grid and ctx2["colors"] == ctx["colors"],
          "גריד+צבעים זהים בריצה חוזרת", ctx2["grid"] == grid)

    # ----- כתיבת פלט + מילוי fake-ids (להמשך rel/cm) -----
    if write_output:
        write_contacts_outputs(ctx)
    return ctx


def write_contacts_outputs(ctx):
    grid, colors, manual, mcolors = ctx["grid"], ctx["colors"], ctx["manual"], ctx["mcolors"]
    # מילוי Id סינתטי לשורות Insert (Id ריק) — דמיית הדבקה-חזרה
    api_row = grid[1]
    id_col = api_row.index("Id")
    lk_col = 0
    grid2 = [list(r) for r in grid]
    for r in grid2[2:]:
        if id_col < len(r) and not r[id_col]:
            r[id_col] = fake_id(r[lk_col])
    sheets_io.ensure_tab(TPL, T.OUTPUT_TAB_CONTACTS)
    sheets_io.write_grid(TPL, T.OUTPUT_TAB_CONTACTS, grid2)
    sheets_io.set_tab_rtl(TPL, T.OUTPUT_TAB_CONTACTS)
    sheets_io.color_cells(TPL, T.OUTPUT_TAB_CONTACTS, colors)
    # לשונית טיפול-ידני
    if len(manual) > 1:
        sheets_io.ensure_tab(TPL, T.OUTPUT_TAB_MANUAL_CONTACTS)
        sheets_io.write_grid(TPL, T.OUTPUT_TAB_MANUAL_CONTACTS, manual)
        sheets_io.set_tab_rtl(TPL, T.OUTPUT_TAB_MANUAL_CONTACTS)
        sheets_io.color_cells(TPL, T.OUTPUT_TAB_MANUAL_CONTACTS, mcolors)
        sheets_io.set_checkbox_column(TPL, T.OUTPUT_TAB_MANUAL_CONTACTS,
                                     output_writer.MANUAL_CHOICE_COL, 1, len(manual))
    print(f"  נכתב פלט-Contacts ({len(grid2)-2} שורות) + טיפול-ידני ({len(manual)-1} שורות).")


# ================= פאזה: בחירה ידנית (QA-5.10) =================
def phase_manual_choice(cols, dictionary):
    print("== טיפול ידני / בחירה (QA-5.10) ==")
    ctx = build_contacts(cols, dictionary)
    dedup, split = ctx["dedup"], ctx["split"]
    p8 = person_for(dedup, split, ROW_OF["D8"], BLOCK_P)
    if not (p8 and p8.match_ids):
        check("QA-5.10", False, "מועמד ל-D8", "אין מועמד ambiguous")
        return
    chosen_id = p8.match_ids[0]
    choices = {p8.local_key: chosen_id}
    grid2, colors2 = output_writer.build_contacts_grid(
        dedup, ctx["rv"], cols, ctx["db_by_id"], manual_choices=choices)
    # D8 אמור עכשיו להיות בפלט כ-Upsert עם ה-Id הנבחר ותווית "נבחר ידנית"
    lk_col, api_row = 0, grid2[1]
    id_col = api_row.index("Id")
    fb_col = 1  # "נמצא לפי"
    row8 = next((r for r in grid2[2:] if r[lk_col] == p8.local_key), None)
    ok = row8 is not None and row8[id_col] == chosen_id and row8[fb_col] == "נבחר ידנית"
    check("QA-5.10", ok, "D8 בפלט Upsert + 'נבחר ידנית'",
          f"id={row8[id_col] if row8 else None} fb={row8[fb_col] if row8 else None}")


# ================= פאזה: Campaigns =================
def phase_campaigns(cols, dictionary, write_output=True):
    print("== Campaigns (מסך 6) ==")
    tmpl = sheets_io.read_values(TPL, T.TEMPLATE_TAB)
    split = splitter.split_object(T.CAMPAIGN_OBJECT, tmpl, cols, data_start_row=DATA_START)
    rv = [r.values for r in split]
    db_rows = sheets_io.read_values(DB, T.DB_TAB_NAMES[T.CAMPAIGN_OBJECT])
    db_records = sheets_io.rows_to_dicts(db_rows)
    db_by_id = {r["Id"]: r for r in db_records if r.get("Id")}
    dedup = dedup_engine.deduplicate(rv, T.CAMPAIGN_MECHANISMS, db_records, local_key_prefix="K")
    grid, colors = output_writer.build_campaigns_grid(dedup, rv, cols, db_by_id)

    def camp_person(name_norm):
        for p in dedup.persons:
            for i in p.record_indices:
                if identity.normalize(rv[i].get("Name", "")) == name_norm:
                    return p
        return None

    api_row = grid[1]
    name_col = api_row.index("Name") if "Name" in api_row else None
    lk_col, fb_col = 0, 1
    sd_col = api_row.index("StartDate") if "StartDate" in api_row else None

    def out_row(p):
        return next((r for r in grid[2:] if r[lk_col] == p.local_key), None) if p else None

    # QA-6.1: קמפיינים QA 1/2/3 → Insert
    for name in ["קמפיין QA 1", "קמפיין QA 2", "קמפיין QA 3"]:
        p = camp_person(identity.normalize(name))
        r = out_row(p)
        check(f"QA-6.1·{name}", p and p.action == dedup_engine.ACTION_INSERT and r is not None,
              "Insert + בפלט", f"{p.action if p else None}")
    # QA-6.2 + QA-6.5: D1+D12 (אותו שם, רווחים עודפים) → קמפיין אחד
    p1 = camp_person(identity.normalize("קמפיין QA 1"))
    src_rows = {split[i].source_row for i in p1.record_indices} if p1 else set()
    check("QA-6.2", p1 and {ROW_OF["D1"], ROW_OF["D2"], ROW_OF["D4"]} <= src_rows,
          "D1/D2/D4 (QA 1) קמפיין אחד", sorted(src_rows))
    check("QA-6.5", p1 and ROW_OF["D12"] in src_rows,
          "D12 (רווחים עודפים) מתמזג", ROW_OF["D12"] in src_rows)
    # QA-6.3: D13 → Upsert (קיים ב-DB)
    p13 = camp_person(identity.normalize("יום טרפיה ים המלח -פצועים"))
    r13 = out_row(p13)
    fb13 = r13[fb_col] if r13 else None
    check("QA-6.3", p13 and p13.action == dedup_engine.ACTION_UPSERT and fb13 == "קיים",
          "Upsert + 'קיים'", f"{p13.action if p13 else None}/fb={fb13}", note=f"Id={p13.sf_id if p13 else None}")
    # QA-6.4: Backfill StartDate מ-DB ל-D13
    db13 = db_by_id.get(p13.sf_id, {}) if p13 and p13.sf_id else {}
    out_sd = r13[sd_col] if (r13 and sd_col is not None and sd_col < len(r13)) else ""
    check("QA-6.4", bool(db13.get("StartDate")) and out_sd == str(db13.get("StartDate")).strip(),
          "StartDate מ-DB", f"out={out_sd!r} db={db13.get('StartDate')!r}")

    if write_output:
        # מילוי fake-id ל-insert + כתיבה (לצורך CM)
        id_col = api_row.index("Id")
        grid2 = [list(r) for r in grid]
        for r in grid2[2:]:
            if id_col < len(r) and not r[id_col]:
                r[id_col] = fake_id(r[lk_col])
        sheets_io.ensure_tab(TPL, T.OUTPUT_TAB_CAMPAIGNS)
        sheets_io.write_grid(TPL, T.OUTPUT_TAB_CAMPAIGNS, grid2)
        sheets_io.set_tab_rtl(TPL, T.OUTPUT_TAB_CAMPAIGNS)
        sheets_io.color_cells(TPL, T.OUTPUT_TAB_CAMPAIGNS, colors)
        print(f"  נכתב פלט-Campaigns ({len(grid2)-2} שורות).")
    return dedup


# ================= פאזה: Relationships =================
def phase_relationships(cols, dictionary):
    print("== Relationships (מסך 7) ==")
    tmpl = sheets_io.read_values(TPL, T.TEMPLATE_TAB)
    split = splitter.split_object("Contact", tmpl, cols, data_start_row=DATA_START)
    dedup = dedup_engine.deduplicate([r.values for r in split], MECHS, [],
                                     digits_only_fields=T.DIGITS_ONLY_FIELDS, local_key_prefix="C")
    contacts_out = sheets_io.read_values(TPL, T.OUTPUT_TAB_CONTACTS)
    id_map = relationship_builder.id_map_from_grid(contacts_out)
    db_rel = sheets_io.rows_to_dicts(sheets_io.read_values(DB, T.DB_TAB_NAMES["npe4__Relationship__c"]))
    db_pairs = relationship_builder.db_rel_pairs_from_records(db_rel)
    rel = relationship_builder.derive_relationships(
        tmpl, cols, split, dedup, id_map, db_pairs, data_start_row=DATA_START,
        block_primary=BLOCK_P, block_secondary=BLOCK_S, relationship_object=T.RELATIONSHIP_OBJECT)
    grid, colors = relationship_builder.build_relationship_grid(rel)
    by_row = {r.source_row: r for r in rel}

    # QA-7.1: D1 → קשר נגזר (Spouse), נכתב לפלט
    r1 = by_row.get(ROW_OF["D1"])
    in_grid1 = r1 and not r1.exists_in_db and not r1.warning
    check("QA-7.1", r1 and r1.type_val == "Spouse" and in_grid1,
          "קשר Spouse בפלט", f"type={r1.type_val if r1 else None} exists={r1.exists_in_db if r1 else None} warn={bool(r1.warning) if r1 else None}")
    # QA-7.2: D11 → קיים ב-DB → לא בפלט
    r11 = by_row.get(ROW_OF["D11"])
    check("QA-7.2", r11 and r11.exists_in_db,
          "exists_in_db=True (לא בפלט)", f"exists={r11.exists_in_db if r11 else None}",
          note=f"Ids={r11.sf_id_a},{r11.sf_id_b}" if r11 else "")
    # QA-7.3: סימטריה — אותו זוג בכיוון הפוך עדיין מזוהה כקיים
    if r11 and r11.sf_id_a and r11.sf_id_b:
        rev = (min(r11.sf_id_b, r11.sf_id_a), max(r11.sf_id_b, r11.sf_id_a))
        check("QA-7.3", rev in db_pairs, "כיוון הפוך = אותו זוג", rev in db_pairs)
    else:
        check("QA-7.3", False, "זוג D11 תקין", "חסר Id")
    # QA-7.4: D14 (B בלבד) → אין קשר בפלט
    r14 = by_row.get(ROW_OF["D14"])
    no_row14 = (r14 is None) or r14.warning or r14.exists_in_db
    check("QA-7.4", no_row14, "אין שורת-קשר ל-D14", f"rec={'warning' if (r14 and r14.warning) else r14}")
    # QA-7.5: Id חסר → אזהרה (בודקים עם id_map ריק)
    rel_noid = relationship_builder.derive_relationships(
        tmpl, cols, split, dedup, {}, db_pairs, data_start_row=DATA_START,
        block_primary=BLOCK_P, block_secondary=BLOCK_S, relationship_object=T.RELATIONSHIP_OBJECT)
    warns = [r for r in rel_noid if r.warning]
    check("QA-7.5", len(warns) > 0, "אזהרת Id-חסר כשאין מיפוי", f"{len(warns)} אזהרות")

    sheets_io.ensure_tab(TPL, T.OUTPUT_TAB_RELATIONSHIPS)
    sheets_io.write_grid(TPL, T.OUTPUT_TAB_RELATIONSHIPS, grid)
    sheets_io.set_tab_rtl(TPL, T.OUTPUT_TAB_RELATIONSHIPS)
    sheets_io.color_cells(TPL, T.OUTPUT_TAB_RELATIONSHIPS, colors)
    print(f"  נכתב פלט-Relationships ({len(grid)-2} קשרים חדשים).")


# ================= פאזה: CampaignMember =================
def phase_cm(cols, dictionary):
    print("== CampaignMember (מסך 8) ==")
    tmpl = sheets_io.read_values(TPL, T.TEMPLATE_TAB)
    c_split = splitter.split_object("Contact", tmpl, cols, data_start_row=DATA_START)
    c_dedup = dedup_engine.deduplicate([r.values for r in c_split], MECHS, [],
                                       digits_only_fields=T.DIGITS_ONLY_FIELDS, local_key_prefix="C")
    k_split = splitter.split_object(T.CAMPAIGN_OBJECT, tmpl, cols, data_start_row=DATA_START)
    k_dedup = dedup_engine.deduplicate([r.values for r in k_split], T.CAMPAIGN_MECHANISMS, [],
                                       local_key_prefix="K")
    c_map = relationship_builder.id_map_from_grid(sheets_io.read_values(TPL, T.OUTPUT_TAB_CONTACTS))
    k_map = relationship_builder.id_map_from_grid(sheets_io.read_values(TPL, T.OUTPUT_TAB_CAMPAIGNS))
    field_cols = campaign_member_builder._cm_field_columns(cols, T.CM_OBJECT)
    cm = campaign_member_builder.derive_campaign_members(
        tmpl, cols, c_split, c_dedup, k_split, k_dedup, c_map, k_map,
        data_start_row=DATA_START, block_primary=BLOCK_P, block_secondary=BLOCK_S,
        cm_object=T.CM_OBJECT, cm_participating_label=T.CM_PARTICIPATING_LABEL)
    grid, colors = campaign_member_builder.build_campaign_member_grid(cm, field_cols)

    def cms_for(source_row, block):
        return [r for r in cm if r.source_row == source_row and r.block == block and not r.warning]

    # QA-8.1: D1 ראשי + D3 ראשי (TRUE) → רשומות CM
    d1p = cms_for(ROW_OF["D1"], BLOCK_P)
    d3p = cms_for(ROW_OF["D3"], BLOCK_P)
    check("QA-8.1", len(d1p) == 1 and len(d3p) == 1,
          "CM ל-D1 ראשי ול-D3 ראשי", f"D1={len(d1p)} D3={len(d3p)}")
    # QA-8.2: D2 ראשי (FALSE) → אין CM
    d2p = [r for r in cm if r.source_row == ROW_OF["D2"] and r.block == BLOCK_P]
    check("QA-8.2", len(d2p) == 0, "אין CM ל-D2", f"{len(d2p)}")
    # QA-8.3: D1 נוסף (TRUE) → CM ל-Contact B
    d1s = cms_for(ROW_OF["D1"], BLOCK_S)
    check("QA-8.3", len(d1s) == 1, "CM ל-D1 נוסף (Contact B)", f"{len(d1s)}")
    # QA-8.4: Id חסר → אזהרה (id_map ריק)
    cm_noid = campaign_member_builder.derive_campaign_members(
        tmpl, cols, c_split, c_dedup, k_split, k_dedup, {}, {},
        data_start_row=DATA_START, block_primary=BLOCK_P, block_secondary=BLOCK_S,
        cm_object=T.CM_OBJECT, cm_participating_label=T.CM_PARTICIPATING_LABEL)
    check("QA-8.4", any(r.warning for r in cm_noid), "אזהרת Id-חסר", f"{sum(1 for r in cm_noid if r.warning)} אזהרות")

    sheets_io.ensure_tab(TPL, T.OUTPUT_TAB_CM)
    sheets_io.write_grid(TPL, T.OUTPUT_TAB_CM, grid)
    sheets_io.set_tab_rtl(TPL, T.OUTPUT_TAB_CM)
    sheets_io.color_cells(TPL, T.OUTPUT_TAB_CM, colors)
    print(f"  נכתב פלט-CampaignMember ({len(grid)-2} רשומות).")


# ================= פאזה: ולידציה מרוכזת =================
def phase_validation(cols, dictionary):
    print("== ולידציה מרוכזת (VAL) ==")
    # VAL.2: פורמטים חוקיים
    ok2 = all(formatter.parse_date(x) for x in ["2025-07-28", "28/07/2025", "28.07.2025", "28-07-2025"])
    check("QA-VAL.2", ok2, "כל הפורמטים נפרסים", ok2)
    # VAL.3: לא-חוקיים
    ok3 = all(formatter.parse_date(x) is None for x in ["2025-13-01", "abc", "31-13-2000"])
    check("QA-VAL.3", ok3, "לא-חוקיים → None", ok3)
    # VAL.1: Id באורך 15 → bad_id (סינתטי — ה-DB קריאה-בלבד)
    fake_grid = [["מזהה", "שם"], ["Id", "Name"], ["123456789012345", "בדיקה"]]
    iss, marks = validator.validate_output_grid(fake_grid, "Contact", dictionary)
    bad_ids = [i for i in iss if i.kind == validator.KIND_BAD_ID]
    check("QA-VAL.1", len(bad_ids) == 1 and len(marks) == 1,
          "Id-15 מסומן + mark", f"{len(bad_ids)} bad_id, {len(marks)} marks",
          note="אומת סינתטית — ה-DB קריאה-בלבד, לא ניתן לשנותו")
    # VAL.4: אידמפוטנטיות צביעה — אותו קלט → אותם marks
    iss2, marks2 = validator.validate_output_grid(fake_grid, "Contact", dictionary)
    check("QA-VAL.4", marks == marks2, "marks זהים בריצה חוזרת", marks == marks2)


# ================= דוח =================
def write_report():
    passed = sum(1 for _, ok, *_ in RESULTS if ok)
    total = len(RESULTS)
    lines = [
        "---", "title: תוצאות QA", "tags:", "  - qa", "  - testing",
        "created: 2026-06-05", "---", "",
        "# תוצאות QA — סבב מקצה-לקצה", "",
        f"בוצע אוטומטית דרך `qa_run.py` (משחזר את צינור כל מסך). קשור ל-[[בדיקות-QA]] ול-[[work-log]].",
        "", f"**סיכום: {passed}/{total} עברו.**", "",
        "| בדיקה | תוצאה | ציפינו | קיבלנו | הערה |",
        "|-------|-------|--------|--------|------|",
    ]
    for tid, ok, exp, got, note in RESULTS:
        mark = "✅" if ok else "❌"
        exp = exp.replace("|", "/"); got = got.replace("|", "/"); note = note.replace("|", "/")
        lines.append(f"| {tid} | {mark} | {exp} | {got} | {note} |")
    path = "planning/תוצאות-QA.md"
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"\nדוח נכתב ל-{path}  ({passed}/{total} עברו)")


def main():
    phase = sys.argv[1] if len(sys.argv) > 1 else "all"
    cols, dictionary = run_mapping()
    if phase in ("write", "all"):
        phase_write()
    if phase in ("contacts", "all"):
        phase_contacts(cols, dictionary)
    if phase in ("manual", "all"):
        phase_manual_choice(cols, dictionary)
    if phase in ("campaigns", "all"):
        phase_campaigns(cols, dictionary)
    if phase in ("rel", "all"):
        phase_relationships(cols, dictionary)
    if phase in ("cm", "all"):
        phase_cm(cols, dictionary)
    if phase in ("validation", "all"):
        phase_validation(cols, dictionary)
    if phase == "all":
        write_report()


if __name__ == "__main__":
    main()
