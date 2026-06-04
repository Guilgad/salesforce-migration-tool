"""
qa_e2e.py — בדיקת QA קצה-לקצה של צינור Contacts מול גיליון Google אמיתי.

כלי-עזר חד-פעמי (כמו check_access.py) — **לא חלק מהכלי**. מזריק נתונים סינתטיים
ללשוניות-QA ייעודיות בגיליון הטמפלייט (Editor), מריץ את אותן פונקציות-מודול ש-
screen_contacts קורא (split → dedup → build → write/color/rtl), ומאמת את כל
התרחישים המתועדים ביומן: כפילות פנימית (שרשור), Upsert לפי מנגנון 1/2, הכרעה-בשילוב,
ambiguous, unkeyed, נירמול מקפים, backfill, טיפול ידני ואידמפוטנטיות.

לא נוגע בנתונים האמיתיים — כל הלשוניות בקידומת "QA - " וניתנות למחיקה.
הרצה:  python qa_e2e.py
"""
from __future__ import annotations

from modules import dedup_engine, mapper, output_writer, sheets_io

TEMPLATE = "1K9ZtCe14IOt5KTOaJVCan-5iWD1NeHjM-PixH1J8LiQ"  # גיליון הטמפלייט (Editor)

TAB_IN = "QA - קלט"
TAB_DB = "QA - DB"
TAB_OUT = "QA - פלט"
TAB_MANUAL = "QA - טיפול ידני"

MECHS = [["ID_Number__c"], ["FirstName", "LastName"], ["MobilePhone"]]
DIGITS = {"ID_Number__c", "MobilePhone"}

# --- מבנה העמודות (מדמה את פלט mapper.validate_columns לשני בלוקי Contact) ---
_F = [("ID_Number__c", "תעודת זהות"), ("FirstName", "שם פרטי"),
      ("LastName", "שם משפחה"), ("MobilePhone", "טלפון נייד"), ("Email", "אימייל")]


def _build_columns() -> list[mapper.TemplateColumn]:
    cols, idx = [], 0
    for block in ("פרטי איש הקשר ראשי", "עבור איש קשר נוסף"):
        for api, label in _F:
            cols.append(mapper.TemplateColumn(
                index=idx, block=block, label=label, proposed_api=api,
                object_api="Contact", clean_api=api, status=mapper.STATUS_VALID,
            ))
            idx += 1
    return cols


# --- גריד הקלט: 4 שורות-כותרת + שורות-דאטה (10 עמודות: ראשי 0-4, נוסף 5-9) ---
def _input_grid() -> list[list[str]]:
    blank = [""] * 10
    row_block = ["פרטי איש הקשר ראשי"] + [""] * 4 + ["עבור איש קשר נוסף"] + [""] * 4
    row_help = ["סינתטי ל-QA — לא נתוני אמת"] + [""] * 9
    row_label = [lbl for _, lbl in _F] * 2
    row_api = [api for api, _ in _F] * 2

    def r(*vals):  # ממלא שורה ל-10 עמודות
        return list(vals) + [""] * (10 - len(vals))

    data = [
        r("111", "דנה", "כהן"),                              # שרשור א'
        r("111", "", "", "050-111-1111"),                    # שרשור ב' (אותה ת"ז)
        r("", "דנה", "גולן", "050-111-1111"),                # שרשור ג' (אותו טלפון, מקפים)
        r("222", "יוסי", "לוי"),                             # Upsert לפי ת"ז (🟢)
        r("888", "מיכל", "ברק"),                             # Upsert לפי שם (🟡)
        r("333", "אבי", "שמש"),                              # הכרעה-בשילוב (🟠)
        r("444"),                                            # ambiguous → טיפול ידני
        r("", "", "", "", "orphan@nodata.com"),              # unkeyed → טיפול ידני
        # שורה עם שני בלוקים: ראשי = מקפים+גרש (🟢 נירמול), נוסף = חדש (Insert)
        r("123-456", "או'הרה", "טסט", "", "", "777", "ילד", "טסט"),
    ]
    return [row_block, row_help, row_label, row_api] + data


def _db_grid() -> list[list[str]]:
    return [
        ["Id", "ID_Number__c", "FirstName", "LastName", "MobilePhone", "Email"],
        ["SF-0222", "222", "יוסי-ישן", "לוי-ישן", "050-999-9999", "yossi.old@x"],  # backfill
        ["SF-NAME", "555", "מיכל", "ברק", "", "michal@x"],
        ["SF-333A", "333", "אבי", "שמש", "", ""],
        ["SF-333B", "333", "גל", "שמש", "", ""],
        ["SF-444A", "444", "", "", "", ""],
        ["SF-444B", "444", "", "", "", ""],
        ["SF-HYPHEN", "123456", "", "", "", "hyphen.old@x"],
    ]


def _run_pipeline(cols, manual_choices=None):
    """משחזר את צינור screen_contacts מהגיליון, ומחזיר את כל התוצרים."""
    rows = sheets_io.read_values(TEMPLATE, TAB_IN)
    from modules import splitter
    recs = splitter.split_object("Contact", rows, cols, data_start_row=4)
    record_values = [r.values for r in recs]
    source_rows = [r.source_row for r in recs]

    db_records = sheets_io.rows_to_dicts(sheets_io.read_values(TEMPLATE, TAB_DB))
    db_by_id = {r["Id"]: r for r in db_records if r.get("Id")}

    dedup = dedup_engine.deduplicate(record_values, MECHS, db_records, digits_only_fields=DIGITS)
    grid, colors = output_writer.build_contacts_grid(
        dedup, record_values, cols, db_by_id, manual_choices=manual_choices)
    manual, _ = output_writer.build_manual_grid(
        dedup, record_values, cols, db_by_id, source_rows,
        marked=manual_choices, digits_only_fields=DIGITS)
    return dedup, db_by_id, grid, colors, manual


def _write_out(grid, colors, manual):
    sheets_io.ensure_tab(TEMPLATE, TAB_OUT)
    sheets_io.write_grid(TEMPLATE, TAB_OUT, grid)
    sheets_io.set_tab_rtl(TEMPLATE, TAB_OUT)
    sheets_io.color_cells(TEMPLATE, TAB_OUT, colors)
    if len(manual) > 1:
        sheets_io.ensure_tab(TEMPLATE, TAB_MANUAL)
        sheets_io.write_grid(TEMPLATE, TAB_MANUAL, manual)
        sheets_io.set_tab_rtl(TEMPLATE, TAB_MANUAL)


_results: list[tuple[str, bool, str]] = []


def check(name, cond, detail=""):
    _results.append((name, bool(cond), detail))


def main():
    cols = _build_columns()

    # ===== הזרקת נתוני-הדמה =====
    for tab in (TAB_IN, TAB_DB):
        sheets_io.ensure_tab(TEMPLATE, tab)
    sheets_io.write_grid(TEMPLATE, TAB_IN, _input_grid())
    sheets_io.set_tab_rtl(TEMPLATE, TAB_IN)
    sheets_io.write_grid(TEMPLATE, TAB_DB, _db_grid())
    print(f"נכתבו לשוניות-קלט: {TAB_IN}, {TAB_DB}")

    # ===== סבב 1 =====
    dedup, db_by_id, grid, colors, manual = _run_pipeline(cols)
    _write_out(grid, colors, manual)

    c = dedup.counts
    check("מונים (2 חדשים / 4 לעדכון / 1 ריבוי / 1 ללא-זיהוי)",
          c == {"inserts": 2, "upserts": 4, "ambiguous": 1, "unkeyed": 1}, str(c))

    by_key = {p.local_key: p for p in dedup.persons}
    # שרשור: שלוש רשומות-הקלט הראשונות התמזגו לאדם אחד
    chain = next(p for p in dedup.persons if sorted(p.record_indices) == [0, 1, 2])
    check("שרשור פנימי: 3 רשומות → אדם אחד", chain.action == dedup_engine.ACTION_INSERT)

    # מיפוי תרחיש→צבע בגריד הנכתב
    color_by_row = {row0: col for (row0, _c, col) in colors}
    rows_out = grid[2:]
    found = {row[2]: (row[1], color_by_row.get(2 + i)) for i, row in enumerate(rows_out)}
    check("Upsert לפי ת\"ז → 🟢", found.get("SF-0222") == ("1", "green"), str(found.get("SF-0222")))
    check("Upsert לפי שם → 🟡", found.get("SF-NAME") == ("2", "yellow"), str(found.get("SF-NAME")))
    check("הכרעה-בשילוב → 🟠", found.get("SF-333A") == ("שילוב 1+2", "orange"), str(found.get("SF-333A")))
    check("נירמול מקפים בת\"ז → 🟢", found.get("SF-HYPHEN") == ("1", "green"), str(found.get("SF-HYPHEN")))

    # backfill: תאים ריקים בקלט מתמלאים מה-DB, וערך-טמפלייט גובר
    row_0222 = next(row for row in rows_out if row[2] == "SF-0222")
    # [key, נמצא-לפי, Id, ID, FN, LN, נייד, אימייל]
    check("backfill טלפון מה-DB", row_0222[6] == "050-999-9999", row_0222[6])
    check("backfill אימייל מה-DB", row_0222[7] == "yossi.old@x", row_0222[7])
    check("ערך-טמפלייט גובר (שם פרטי)", row_0222[4] == "יוסי", row_0222[4])

    # תווים מיוחדים נשמרים
    row_hyphen = next(row for row in rows_out if row[2] == "SF-HYPHEN")
    check("גרש בשם נשמר (או'הרה)", row_hyphen[4] == "או'הרה", row_hyphen[4])

    # ambiguous + unkeyed יצאו מהגריד הראשי לטיפול ידני
    main_ids = {row[2] for row in rows_out}
    check("ambiguous מוחרג מהטעינה", "SF-444A" not in main_ids and "SF-444B" not in main_ids)
    amb = next(p for p in dedup.persons if p.ambiguous)
    check("ambiguous: 2 מועמדים", sorted(amb.match_ids) == ["SF-444A", "SF-444B"], str(amb.match_ids))
    unk = next(p for p in dedup.persons if p.unkeyed)
    check("unkeyed זוהה", unk.sf_id is None)
    # לשונית הטיפול הידני: כותרת + (מקור+2 מועמדים) + (מקור unkeyed)
    check("לשונית טיפול ידני נבנתה", len(manual) == 1 + 3 + 1, f"{len(manual)} שורות")

    # round-trip: הפלט באמת נכתב לגיליון
    out_back = sheets_io.read_values(TEMPLATE, TAB_OUT)
    check("הפלט נכתב לגיליון (6 שורות-נתונים)", len(out_back) - 2 == 6, f"{len(out_back) - 2}")

    # ===== סבב 2: סימולציית בחירה ידנית =====
    manual_back = sheets_io.read_values(TEMPLATE, TAB_MANUAL)
    hdr = manual_back[0]
    c_id, c_mark = hdr.index("מזהה"), hdr.index("בחר")
    # מוצאים את שורת המועמד SF-444A ומסמנים בה ✓ (כתיבה כירורגית, כמו שהמשתמש היה עושה)
    pick_row = next(i for i, row in enumerate(manual_back)
                    if len(row) > c_id and row[c_id] == "SF-444A")
    sheets_io.write_cells(TEMPLATE, TAB_MANUAL, [(pick_row, c_mark, "✓")])

    manual_back = sheets_io.read_values(TEMPLATE, TAB_MANUAL)
    choices, warns = output_writer.parse_manual_choices(manual_back)
    check("נקלטה בחירה ידנית אחת", len(choices) == 1 and "SF-444A" in choices.values(), str(choices))

    dedup2, _, grid2, colors2, manual2 = _run_pipeline(cols, manual_choices=choices)
    _write_out(grid2, colors2, manual2)
    rows2 = grid2[2:]
    chosen_row = next((row for row in rows2 if row[2] == "SF-444A"), None)
    check("הבחירה הידנית הפכה ל-Upsert בטעינה",
          chosen_row is not None and chosen_row[1] == "נבחר ידנית", str(chosen_row))
    check("הטעינה גדלה ל-7 שורות אחרי הבחירה", len(rows2) == 7, str(len(rows2)))
    # הסימון נשמר בלשונית הידנית (אידמפוטנטיות הסימון)
    y_marked = any(row[c_id] == "SF-444A" and len(row) > c_mark and row[c_mark] == "✓"
                   for row in manual2)
    check("הסימון ✓ נשמר בלשונית הידנית", y_marked)

    # ===== סבב 3: אידמפוטנטיות =====
    _, _, grid3, colors3, _ = _run_pipeline(cols, manual_choices=choices)
    check("אידמפוטנטיות: בנייה חוזרת = אותו גריד", grid3 == grid2)
    check("אידמפוטנטיות: אותם צבעים", sorted(colors3) == sorted(colors2))

    # ===== דו"ח =====
    print("\n" + "=" * 60)
    passed = sum(1 for _, ok, _ in _results if ok)
    for name, ok, detail in _results:
        mark = "✅" if ok else "❌"
        line = f"{mark} {name}"
        if not ok and detail:
            line += f"   ← {detail}"
        print(line)
    print("=" * 60)
    print(f"{passed}/{len(_results)} עברו")
    print(f"\nפתח את הגיליון וראה את הלשוניות: {TAB_OUT} (צבעים 🟢/🟡/🟠) · {TAB_MANUAL}")
    return 0 if passed == len(_results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
