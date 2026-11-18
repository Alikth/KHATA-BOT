@echo off
setlocal
cd /d "%~dp0\.."
py -3.11 -m venv .venv
if errorlevel 1 goto fail
".venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 goto fail
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto fail
if not exist ".env" copy ".env.example" ".env"
echo Setup complete. Edit .env and create the PostgreSQL database before starting.
pause
exit /b 0
:fail
echo Setup failed.
pause
exit /b 1
