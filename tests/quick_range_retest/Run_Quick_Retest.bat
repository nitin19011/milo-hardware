@echo off
cd /d "%~dp0"
py quick_range_retest.py --host 172.20.10.2 --speak %*
pause
