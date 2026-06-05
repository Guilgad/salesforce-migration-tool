"""qa_probe.py — חקירה לקריאה-בלבד לקראת QA. שולף מה-DB ערכים אמיתיים לנתוני-הדמה.

לא כותב כלום. כלי-עזר חד-פעמי (כמו check_access.py / qa_e2e.py).
"""
from __future__ import annotations

import sys
from collections import defaultdict

sys.stdout.reconfigure(encoding="utf-8")

from config import template_config
from modules import sheets_io, field_dictionary, mapper

TPL = "1K9ZtCe14IOt5KTOaJVCan-5iWD1NeHjM-PixH1J8LiQ"
DB = "1aauowFwIV6wpYYR9WU9BJBcv7ehEj7otkbUbKSLS6wU"
SOQL = "1gtWdPGep5-5nA3Gq6880itaLo01M2cf73peJLGmzSBo"


def digits(s):
    return "".join(ch for ch in str(s or "") if ch.isdigit())


def run_mapping():
    dict_rows = sheets_io.read_values(SOQL, None)
    parsed = field_dictionary.parse_field_dictionary(dict_rows, template_config.DEFAULT_OBJECTS)
    tmpl = sheets_io.read_values(TPL, template_config.TEMPLATE_TAB)
    cols = mapper.extract_columns(
        tmpl, block_row=template_config.TEMPLATE_BLOCK_ROW,
        label_row=template_config.TEMPLATE_LABEL_ROW, api_row=template_config.TEMPLATE_API_ROW,
    )
    mapper.assign_objects(cols, template_config.BLOCK_TO_OBJECT, template_config.WANDERING_OVERRIDES)
    mapper.validate_columns(cols, parsed.objects, control_columns=template_config.CONTROL_COLUMNS)
    return cols, parsed


def main():
    print("=" * 70)
    print("MAPPING — valid fields per object")
    cols, parsed = run_mapping()
    by_obj = defaultdict(list)
    for c in cols:
        if c.status == mapper.STATUS_VALID and c.clean_api:
            by_obj[c.object_api].append(c.clean_api)
    for obj, fs in by_obj.items():
        print(f"  {obj}: {sorted(set(fs))}")
    print("  dictionary objects:", list(parsed.objects.keys()))
    print("  warnings:", parsed.warnings)

    # ---- Contact DB ----
    print("=" * 70)
    c_rows = sheets_io.read_values(DB, template_config.DB_TAB_NAMES["Contact"])
    c_recs = sheets_io.rows_to_dicts(c_rows)
    print(f"Contact DB: {len(c_recs)} records. header={c_rows[0][:8]}")
    # ID_Number -> set of Ids
    id_to_ids = defaultdict(set)
    for r in c_recs:
        idn = digits(r.get("ID_Number__c"))
        sid = (r.get("Id") or "").strip()
        if idn and sid:
            id_to_ids[idn].add(sid)
    single = [(idn, list(ids)[0]) for idn, ids in id_to_ids.items() if len(ids) == 1]
    multi = [(idn, sorted(ids)) for idn, ids in id_to_ids.items() if len(ids) >= 2]
    print(f"  unique-ID_Number count={len(single)}  duplicate-ID_Number(>=2 Ids) count={len(multi)}")
    if single:
        print("  D6 candidate (ID_Number -> single Id):", single[0])
    if multi:
        print("  D8 candidate (ID_Number -> 2+ Ids):", multi[0])
    else:
        print("  D8: NO natural duplicate-ID found in DB")

    # LastName+MobilePhone uniqueness for D7
    lp_to_ids = defaultdict(set)
    rec_by_id = {}
    for r in c_recs:
        sid = (r.get("Id") or "").strip()
        rec_by_id[sid] = r
        ln = (r.get("LastName") or "").strip().casefold()
        ph = digits(r.get("MobilePhone"))
        if ln and ph and sid:
            lp_to_ids[(ln, ph)].add(sid)
    lp_single = [(k, list(v)[0]) for k, v in lp_to_ids.items() if len(v) == 1]
    print(f"  LastName+Phone unique pairs: {len(lp_single)}")
    # pick a D7 candidate whose chosen Id has an ID_Number too (for backfill demo)
    for (ln, ph), sid in lp_single:
        r = rec_by_id.get(sid, {})
        print("  D7 candidate: LastName=%r MobilePhone=%r -> Id=%s (ID_Number in DB=%r, FirstName=%r)" % (
            r.get("LastName"), r.get("MobilePhone"), sid, r.get("ID_Number__c"), r.get("FirstName")))
        break

    # ---- Campaign DB ----
    print("=" * 70)
    camp_rows = sheets_io.read_values(DB, template_config.DB_TAB_NAMES["Campaign"])
    camp_recs = sheets_io.rows_to_dicts(camp_rows)
    print(f"Campaign DB: {len(camp_recs)} records. header={camp_rows[0][:6]}")
    name_to_ids = defaultdict(set)
    for r in camp_recs:
        nm = (r.get("Name") or "").strip()
        sid = (r.get("Id") or "").strip()
        if nm and sid:
            name_to_ids[nm].add(sid)
    camp_single = [(nm, list(ids)[0]) for nm, ids in name_to_ids.items() if len(ids) == 1]
    if camp_single:
        nm, sid = camp_single[0]
        r = next((x for x in camp_recs if (x.get("Id") or "").strip() == sid), {})
        print("  D13 candidate: Name=%r -> Id=%s  StartDate=%r" % (nm, sid, r.get("StartDate")))

    # ---- Relationship DB: find a pair whose BOTH contacts have ID_Number ----
    print("=" * 70)
    rel_rows = sheets_io.read_values(DB, template_config.DB_TAB_NAMES["npe4__Relationship__c"])
    rel_recs = sheets_io.rows_to_dicts(rel_rows)
    print(f"Relationship DB: {len(rel_recs)} records. header={rel_rows[0][:6]}")
    # id -> ID_Number (only contacts that map to a SINGLE id by ID_Number, for clean upsert)
    id_to_idn = {}
    for idn, ids in id_to_ids.items():
        if len(ids) == 1:
            id_to_idn[list(ids)[0]] = idn
    found = 0
    for r in rel_recs:
        a = (r.get("npe4__Contact__c") or "").strip()
        b = (r.get("npe4__RelatedContact__c") or "").strip()
        t = (r.get("npe4__Type__c") or "").strip()
        if a in id_to_idn and b in id_to_idn and a != b:
            ra, rb = rec_by_id.get(a, {}), rec_by_id.get(b, {})
            print("  D11 candidate pair:")
            print("    A: Id=%s ID_Number=%s Name=%s %s" % (a, id_to_idn[a], ra.get("FirstName"), ra.get("LastName")))
            print("    B: Id=%s ID_Number=%s Name=%s %s" % (b, id_to_idn[b], rb.get("FirstName"), rb.get("LastName")))
            print("    Type=%r" % t)
            found += 1
            if found >= 3:
                break
    if not found:
        print("  D11: NO relationship pair where both contacts have unique ID_Number")


if __name__ == "__main__":
    main()
