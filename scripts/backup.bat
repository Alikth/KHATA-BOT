@echo off
setlocal
cd /d "%~dp0\.."
if not exist ".env" (
  echo Missing .env
  exit /b 1
)
for /f "tokens=1,* delims==" %%A in ('findstr /b "DATABASE_URL=" .env') do set DATABASE_URL=%%B
if "%DATABASE_URL%"=="" (
  echo DATABASE_URL missing in .env
  exit /b 1
)
if not exist "var\backups" mkdir "var\backups"
for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd-HHmmss"') do set STAMP=%%i
echo NOTE: DATABASE_URL must be converted to pg_dump connection parameters if it uses SQLAlchemy URL syntax.
echo Use the Python backup module for a verified backup in a later release.
echo Backup script is a placeholder; do not treat this as a completed backup.
pause
