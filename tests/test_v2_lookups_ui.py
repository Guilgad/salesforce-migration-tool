"""Smoke tests for screen_lookups (step 4)."""
import pytest
from streamlit.testing.v1 import AppTest
from config.runtime_schema import RuntimeSchema, ObjectDef, IdentityConfig, LookupConfig, JunctionConfig
import main as main_module


BASE_SCHEMA = RuntimeSchema(
    objects=[ObjectDef("Contact", "אנשי קשר"), ObjectDef("Account", "חשבונות")],
    identity={
        "Contact": IdentityConfig(mechanisms=[["Email"]]),
        "Account": IdentityConfig(mechanisms=[["Name"]]),
    },
)


def _at_step4(schema=None):
    at = AppTest.from_file("main.py", default_timeout=10)
    at.session_state["step"] = 4
    at.session_state["schema"] = schema or BASE_SCHEMA
    at.run()
    return at


def test_step4_renders_without_exception():
    at = _at_step4()
    assert not at.exception


def test_step4_shows_lookup_section():
    at = _at_step4()
    all_text = " ".join(str(e.value) for e in list(at.markdown) + list(at.subheader) + list(at.caption) + list(at.info))
    assert "Lookup" in all_text or "קשר" in all_text


def test_step4_shows_load_order_section():
    at = _at_step4()
    all_text = " ".join(str(e.value) for e in list(at.markdown) + list(at.subheader) + list(at.caption) + list(at.info))
    assert "סדר" in all_text or "טעינה" in all_text


def test_step4_with_existing_lookup():
    schema = RuntimeSchema(
        objects=[ObjectDef("Contact", "אנשי קשר"), ObjectDef("Account", "חשבונות")],
        identity={
            "Contact": IdentityConfig(mechanisms=[["Email"]]),
            "Account": IdentityConfig(mechanisms=[["Name"]]),
        },
        lookups=[LookupConfig("Contact", 3, "Account", "AccountId", ["Name"])],
    )
    at = _at_step4(schema)
    assert not at.exception
    all_text = " ".join(str(e.value) for e in list(at.markdown) + list(at.subheader) + list(at.caption) + list(at.info))
    assert "AccountId" in all_text or "Account" in all_text


def test_load_order_junction_after_parents():
    """Junction object loads after both parents."""
    schema = RuntimeSchema(
        objects=[ObjectDef("Contact", "אנשי קשר"), ObjectDef("Campaign", "קמפיינים")],
        junctions=[JunctionConfig(
            object_a="Contact", block_a="C",
            object_b="Campaign", block_b="K",
            junction_object="CampaignMember",
            id_field_a="ContactId", id_field_b="CampaignId",
        )],
    )
    tiers = main_module._load_order(schema)
    flat = [obj for tier in tiers for obj in tier]
    assert flat.index("CampaignMember") > flat.index("Contact")
    assert flat.index("CampaignMember") > flat.index("Campaign")


def test_load_order_junction_object_included():
    schema = RuntimeSchema(
        objects=[ObjectDef("Contact", "אנשי קשר")],
        junctions=[JunctionConfig(
            object_a="Contact", block_a="C", object_b="Contact", block_b="D",
            junction_object="npe4__Relationship__c",
            id_field_a="npe4__Contact__c", id_field_b="npe4__RelatedContact__c",
            symmetric=True,
        )],
    )
    tiers = main_module._load_order(schema)
    flat = [obj for tier in tiers for obj in tier]
    assert "npe4__Relationship__c" in flat


def test_load_order_no_junctions_unchanged():
    """Without junctions, behaviour identical to P4 implementation."""
    schema = RuntimeSchema(
        objects=[ObjectDef("Contact", "אנשי קשר"), ObjectDef("Account", "חשבונות")],
        lookups=[LookupConfig("Contact", 3, "Account", "AccountId", ["Name"])],
    )
    tiers = main_module._load_order(schema)
    flat = [obj for tier in tiers for obj in tier]
    assert flat.index("Account") < flat.index("Contact")
