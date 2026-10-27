@echo off
setlocal
cd /d "%~dp0"
py -3 -c "import serial" >nul 2>&1
if errorlevel 1 (
    py -3 -m pip install pyserial
    if errorlevel 1 goto failed
)
py -3 calibrate_usb.py %*
if errorlevel 1 goto failed
pause
exit /b 0
:failed
echo Calibration could not finish. Read the error above.
pause
exit /b 1
