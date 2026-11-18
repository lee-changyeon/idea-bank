@echo off
rem IdeaBank online - web app. Close this window to stop the server.
chcp 65001 >nul
set PYTHONUTF8=1
cd /d "%~dp0"
python web\server.py --seed-if-empty --open
if errorlevel 1 pause
