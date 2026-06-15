"""
בדיקת-עשן מאוחדת: כל 5 מסכי-ה-wizard נטענים בלי קריסה — גלאי-קריסות זול יחיד.

מחליפה את בדיקות ה-"renders_without_exception" שהיו מפוזרות פר-מסך. בדיקות-עשן מסוג
"אין חריגה" אינן מוכיחות נכונות (פיצ'ר מת עובר אותן) — לכן הן מרוכזות כאן במקום אחד
ושקוף, ולא מתחזות לכיסוי. **כיסוי-הנכונות האמיתי** יושב ב-`test_v2_pipeline_e2e.py`
(הצינור מקצה-לקצה) ובבדיקות-המנוע.
"""
import pytest
from streamlit.testing.v1 import AppTest


@pytest.mark.parametrize("step", [1, 2, 3, 4, 5])
def test_screen_renders_without_exception(step):
    at = AppTest.from_file("main.py", default_timeout=30)
    at.run()
    at.session_state["step"] = step
    at.run()
    assert not at.exception, f"מסך שלב {step} קרס"
