@echo off
setlocal
cd /d "%~dp0\.."
if not exist ".venv\Scripts\python.exe" (
  echo Run scripts\setup_windows.bat first.
  exit /b 1
)
".venv\Scripts\python.exe" scripts\backup.py
if errorlevel 1 (
  echo Backup FAILED. Do not proceed with database migrations.
  pause
  exit /b 1
)
pause
