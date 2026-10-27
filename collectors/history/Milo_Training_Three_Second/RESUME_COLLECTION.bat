@echo off
cd /d "%~dp0"
start "" pyw "%~dp0collection_gui.py" --resume-latest %*
exit /b
