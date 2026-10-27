@echo off
setlocal
cd /d "%~dp0"
py -3 -c "import tkinter, serial" >nul 2>&1
if errorlevel 1 (
    py -3 -m pip install -r requirements.txt
    if errorlevel 1 goto failed
)
py -3 collector_ui.py
if errorlevel 1 goto failed
exit /b 0
:failed
echo The collector could not start. Check the error above and your Python installation.
pause
exit /b 1
