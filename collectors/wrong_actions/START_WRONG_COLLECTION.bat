@echo off
setlocal
cd /d "%~dp0"
py -3 -c "import tkinter, serial, numpy" >nul 2>&1
if errorlevel 1 (
    py -3 -m pip install -r requirements.txt
    if errorlevel 1 goto failed
)
py -3 collector_ui.py
if errorlevel 1 goto failed
exit /b 0
:failed
echo The collector could not start. Read the error above.
pause
exit /b 1
