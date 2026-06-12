"""Smoke tests for screen_lookups (step 4)."""
import pytest
from streamlit.testing.v1 import AppTest
from config.runtime_schema import RuntimeSchema, ObjectDef, IdentityConfig, LookupConfig


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
