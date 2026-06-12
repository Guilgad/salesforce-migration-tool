"""Smoke tests for screen_build."""
from streamlit.testing.v1 import AppTest


def test_build_screen_renders_without_exception():
    at = AppTest.from_file("main.py", default_timeout=30)
    at.run()
    at.session_state["step"] = 5
    at.run()
    assert not at.exception


def test_build_screen_no_stub_message():
    at = AppTest.from_file("main.py", default_timeout=30)
    at.run()
    at.session_state["step"] = 5
    at.run()
    assert not any("בפרוסה הבאה" in str(e) for e in at.info)
