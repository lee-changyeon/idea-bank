@echo off
chcp 65001 >nul
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
where python >nul 2>nul
if errorlevel 1 (
  echo Python 3 이 설치되어 있지 않습니다. https://www.python.org 에서 설치한 뒤 다시 실행하세요.
  pause
  exit /b 1
)
python server.py
pause
