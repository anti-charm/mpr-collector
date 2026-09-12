@echo off
setlocal
cd /d "%~dp0"
py -3 -c "import sys, tkinter; assert sys.version_info >= (3, 10)" >nul 2>nul
if not errorlevel 1 goto run_py
python -c "import sys, tkinter; assert sys.version_info >= (3, 10)" >nul 2>nul
if not errorlevel 1 goto run_python
echo MPR Collector needs Python 3.10 or newer with Tkinter.
echo Install Python for Windows from https://www.python.org/downloads/windows/
echo Keep the Tcl/Tk and IDLE option enabled during installation.
echo Then double-click this file again. No pip packages are needed.
pause
exit /b 1
:run_py
py -3 "%~dp0mpr_collector.py"
goto finished
:run_python
python "%~dp0mpr_collector.py"
:finished
if errorlevel 1 (
    echo MPR Collector could not start or stopped unexpectedly.
    pause
    exit /b 1
)
exit /b 0
