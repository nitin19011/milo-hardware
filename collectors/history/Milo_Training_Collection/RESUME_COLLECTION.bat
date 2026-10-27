@echo off
cd /d "%~dp0"
py collect_training.py --resume-latest %*
pause
