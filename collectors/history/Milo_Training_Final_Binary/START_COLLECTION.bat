@echo off
cd /d "%~dp0"
py -c "import tkinter, numpy, paho.mqtt.client" >nul 2>&1
if errorlevel 1 (
  echo Run SETUP_ONCE.bat first to install the required Python packages.
  pause
  exit /b 1
)
start "" pyw "%~dp0collection_gui.py" %*
exit /b
