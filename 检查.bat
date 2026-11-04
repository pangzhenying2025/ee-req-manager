@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Run: python scripts\dev.py setup
  pause
  exit /b 1
)
".venv\Scripts\python.exe" scripts\dev.py check %*
if errorlevel 1 pause
