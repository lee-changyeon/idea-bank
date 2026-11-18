@echo off
rem IdeaBank - set the admin password for ceo. Run by double-click.
chcp 65001 >nul
set PYTHONUTF8=1
cd /d "%~dp0"
python web\manage_admins.py passwd ceo
pause
