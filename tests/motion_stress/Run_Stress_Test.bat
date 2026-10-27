@echo off
cd /d "%~dp0"
py stress_glove_test.py --host 172.20.10.2 --speak %*
pause
