"""
campaign_member_builder — גזירת CampaignMember מרשומות-קלט.

טהור (בלי I/O): לכל (שורה × בלוק-איש-קשר) שבו "משתתף באירוע"=TRUE — נוצרת
רשומת CampaignMember המקשרת Contact ל-Campaign. v1: אין בדיקת-קיום מול DB.

תנאי-קדם: Contacts ו-Campaigns כבר נטענו וה-Ids הודבקו בחזרה בגיליונות הפלט.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from modules import dedup_engine, mapper, splitter

# כותרות גריד CampaignMember (שורת-עברית + שורת-API)
_DISPLAY_COL_HE = "שם איש-קשר"   # עמודה 0 — לתצוגה בלבד, לא נטענת
_DISPLAY_COL_API = ""
_HEADER_ROWS = 2
_DISPLAY_COL_IDX = 0              # עמודה "שם" צבועה אדום-בהיר (לא-נטענת)

_NOT_PARTICIPATING = {"", "0", "false", "לא", "no"}


@dataclass
class CMRecord:
    """רשומת CampaignMember אחת (Contact אחד בקמפיין אחד)."""
    source_row: int
    block: str                         # בלוק-איש-הקשר (PRIMARY / SECONDARY)
    contact_local_key: str
    campaign_local_key: str
    contact_id: str                    # SF Id (ריק = לא נטען עדיין)
    campaign_id: str
    field_values: dict[str, str]       # שדות STATUS_VALID של CampaignMember
    contact_name: str                  # לתצוגה בלבד
    warning: str | None


def _is_participating(value: str) -> bool:
    """TRUE אם הערך מסמן "משתתף" — כל ערך שאינו ריק/False/0/לא."""
    return str(value).strip().casefold() not in _NOT_PARTICIPATING


def _cell(row: list[str], i: int) -> str:
    if 0 <= i < len(row) and row[i] is not None:
        return str(row[i]).strip()
    return ""


def _display_name(values: dict) -> str:
    first = str(values.get("FirstName", "") or "").strip()
    last = str(values.get("LastName", "") or "").strip()
    return (first + " " + last).strip()


def _cm_field_columns(
    columns: list[mapper.TemplateColumn], object_api: str
) -> list[tuple[str, str]]:
    """Union ייחודי של (clean_api, label) לשדות STATUS_VALID של האובייקט (כל הבלוקים)."""
    pairs: list[tuple[str, str]] = []
    seen: set[str] = set()
    for c in columns:
        if (
            c.object_api == object_api
            and c.status == mapper.STATUS_VALID
            and c.clean_api
            and c.clean_api not in seen
        ):
            seen.add(c.clean_api)
            pairs.append((c.clean_api, c.label))
    return pairs


def derive_campaign_members(
    tmpl_rows: list[list[str]],
    columns: list[mapper.TemplateColumn],
    contact_split: list[splitter.SplitRecord],
    contact_dedup: dedup_engine.DedupResult,
    campaign_split: list[splitter.SplitRecord],
    campaign_dedup: dedup_engine.DedupResult,
    contact_id_map: dict[str, str],
    campaign_id_map: dict[str, str],
    *,
    data_start_row: int,
    block_primary: str,
    block_secondary: str,
    cm_object: str,
    cm_participating_label: str,
) -> list[CMRecord]:
    """
    גוזר רשומות CampaignMember מהטמפלייט.

    contact_split + contact_dedup: ריצת Contacts (local_key_prefix="C").
    campaign_split + campaign_dedup: ריצת Campaigns (local_key_prefix="K").
    contact_id_map / campaign_id_map: local_key → sf_id מגיליונות הפלט (לאחר טעינה).
    """
    # record_idx → local_key לאנשי-קשר ולקמפיינים
    contact_idx_to_key: dict[int, str] = {
        idx: p.local_key
        for p in contact_dedup.persons
        for idx in p.record_indices
    }
    campaign_idx_to_key: dict[int, str] = {
        idx: p.local_key
        for p in campaign_dedup.persons
        for idx in p.record_indices
    }

    # (source_row, block) → record_idx — שמרנו רק הראשון לכל זוג
    contact_row_block: dict[tuple[int, str], int] = {}
    for i, rec in enumerate(contact_split):
        contact_row_block.setdefault((rec.source_row, rec.block), i)

    # source_row → campaign_local_key (בלוק קמפיין = "פרטי האירוע")
    campaign_row_to_key: dict[int, str] = {}
    for i, rec in enumerate(campaign_split):
        key = campaign_idx_to_key.get(i, "")
        campaign_row_to_key.setdefault(rec.source_row, key)

    # עמודת-בקרה ("משתתף באירוע") per block: {block → col_index}
    control_col: dict[str, int] = {}
    for c in columns:
        if (
            c.status == mapper.STATUS_CONTROL
            and c.label == cm_participating_label
            and c.block not in control_col
        ):
            control_col[c.block] = c.index

    # שדות STATUS_VALID per block: {block → [(clean_api, col_index)]}
    field_cols_by_block: dict[str, list[tuple[str, int]]] = {}
    for c in columns:
        if c.object_api == cm_object and c.status == mapper.STATUS_VALID and c.clean_api:
            field_cols_by_block.setdefault(c.block, []).append((c.clean_api, c.index))

    results: list[CMRecord] = []
    for block in (block_primary, block_secondary):
        ctrl_idx = control_col.get(block)
        if ctrl_idx is None:
            continue  # אין עמודת-בקרה לבלוק זה — לא יוצרים CM
        block_fields = field_cols_by_block.get(block, [])

        for r in range(data_start_row, len(tmpl_rows)):
            val = _cell(tmpl_rows[r], ctrl_idx)
            if not _is_participating(val):
                continue

            contact_rec_idx = contact_row_block.get((r, block))
            contact_key = contact_idx_to_key.get(contact_rec_idx, "") if contact_rec_idx is not None else ""
            campaign_key = campaign_row_to_key.get(r, "")

            contact_id = contact_id_map.get(contact_key, "") if contact_key else ""
            campaign_id = campaign_id_map.get(campaign_key, "") if campaign_key else ""

            contact_name = (
                _display_name(contact_split[contact_rec_idx].values)
                if contact_rec_idx is not None else ""
            ) or contact_key

            field_values = {
                api: _cell(tmpl_rows[r], idx)
                for api, idx in block_fields
            }

            warning: str | None = None
            if not contact_id:
                warning = f"Id חסר לאיש-קשר {contact_key} — יש לטעון את Contacts קודם"
            elif not campaign_id:
                warning = f"Id חסר לקמפיין {campaign_key} — יש לטעון את Campaigns קודם"

            results.append(CMRecord(
                source_row=r,
                block=block,
                contact_local_key=contact_key,
                campaign_local_key=campaign_key,
                contact_id=contact_id,
                campaign_id=campaign_id,
                field_values=field_values,
                contact_name=contact_name,
                warning=warning,
            ))
    return results


def build_campaign_member_grid(
    cm_records: list[CMRecord],
    field_cols: list[tuple[str, str]],
) -> tuple[list[list[str]], list[tuple[int, int, str]]]:
    """
    בונה גריד CampaignMember: 2 שורות-כותרת ואז שורה לכל רשומה ללא warning.

    field_cols: (clean_api, label) עבור שדות STATUS_VALID נוספים (מ-_cm_field_columns).
    מחזיר (grid, cell_colors) — cell_colors לצביעת עמודת "שם" באדום-בהיר.
    """
    field_apis = [api for api, _ in field_cols]
    field_labels = [lbl for _, lbl in field_cols]

    header_he = [_DISPLAY_COL_HE, "איש-קשר (Id)", "קמפיין (Id)"] + field_labels
    header_api = [_DISPLAY_COL_API, "ContactId", "CampaignId"] + field_apis
    grid: list[list[str]] = [header_he, header_api]
    cell_colors: list[tuple[int, int, str]] = []

    row_idx = 0
    for rec in cm_records:
        if rec.warning:
            continue
        row = [rec.contact_name, rec.contact_id, rec.campaign_id] + [
            rec.field_values.get(api, "") for api in field_apis
        ]
        grid.append(row)
        cell_colors.append((_HEADER_ROWS + row_idx, _DISPLAY_COL_IDX, "red"))
        row_idx += 1

    return grid, cell_colors
