@echo off
setlocal
cd /d "%~dp0\.."
if "%~1"=="" (
  echo Usage: scripts\restore.bat path\to\backup.dump
  exit /b 1
)
if "%RESTORE_DATABASE_URL%"=="" (
  echo Set RESTORE_DATABASE_URL to a separate EMPTY PostgreSQL database before restoring.
  exit /b 1
)
if not exist ".venv\Scripts\python.exe" (
  echo Run scripts\setup_windows.bat first.
  exit /b 1
)
".venv\Scripts\python.exe" scripts\restore.py "%~1"
if errorlevel 1 (
  echo Restore FAILED. Inspect the error above.
  pause
  exit /b 1
)
pause
