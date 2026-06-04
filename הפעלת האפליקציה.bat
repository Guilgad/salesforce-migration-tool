@echo off
cd /d "%~dp0"
:: עצור תהליכים ישנים על פורט 8501 לפני הפעלה
for /f "tokens=5" %%a in ('netstat -aon 2^>nul ^| findstr ":8501"') do (
    taskkill /F /PID %%a 2>nul
)
python -m streamlit run main.py
