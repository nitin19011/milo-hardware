@echo off
cd /d "%~dp0"
py -c "import tkinter, paho.mqtt.client" >nul 2>&1
if errorlevel 1 (
  echo Run SETUP_ONCE.bat first, then launch this file again.
  pause
  exit /b 1
)
py launch_collection.py
if errorlevel 1 pause
