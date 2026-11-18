@echo off
setlocal
cd /d "%~dp0"

if not exist ".env" (
  echo ERROR: .env was not found.
  echo Copy .env.example to .env and fill in the required settings.
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo ERROR: Python environment was not found.
  echo Run scripts\setup_windows.bat first.
  pause
  exit /b 1
)

".venv\Scripts\python.exe" -m bot.main
if errorlevel 1 (
  echo.
  echo Bot stopped with an error. Review the message above and check .env and PostgreSQL.
  pause
  exit /b 1
)
endlocal
