@echo off
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel%==0 (
    py -3 mpr_collector.py
) else (
    python mpr_collector.py
)
if errorlevel 1 pause
