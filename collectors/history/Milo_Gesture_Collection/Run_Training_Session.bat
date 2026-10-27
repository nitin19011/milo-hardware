@echo off
cd /d "%~dp0"
py collect_gestures.py --host 172.20.10.2 --reps 10 --speak %*
pause
