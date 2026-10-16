@echo off
rem EOIP (Django) one-click start: double-click this file.
rem First run: creates .venv, installs requirements, prepares the database, creates your employee account.
rem Every run: starts the server and opens http://localhost:8000 (the phone uses HTTPS on port 8443)
setlocal
chcp 65001 >nul
cd /d "%~dp0"
title EOIP Server (Django)
if not defined EOIP_PORT set "EOIP_PORT=8000"
if not defined EOIP_PHONE_PORT set "EOIP_PHONE_PORT=8443"

if exist ".venv\Scripts\python.exe" goto :have_venv
echo [1/4] Creating the project environment - first time only...
py -3 -m venv .venv 2>nul || python -m venv .venv
if errorlevel 1 (
    echo [X] Python 3.12 or newer was not found. Install it from https://www.python.org/downloads/
    pause
    exit /b 1
)

:have_venv
if exist ".venv\.installed" goto :have_deps
echo [2/4] Installing requirements - first time only, needs internet, takes a few minutes...
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -q -r requirements.txt
if errorlevel 1 (
    echo [X] Install failed. Check the internet connection and try again.
    pause
    exit /b 1
)
echo ok> ".venv\.installed"

:have_deps
echo [3/4] Preparing the database...
".venv\Scripts\python.exe" manage.py migrate --verbosity 0
if errorlevel 1 (
    echo [X] The database could not be prepared - read the message above.
    pause
    exit /b 1
)
".venv\Scripts\python.exe" -c "import os,sys,django;os.environ.setdefault('DJANGO_SETTINGS_MODULE','eoip_project.settings');django.setup();from django.contrib.auth import get_user_model as U;sys.exit(0 if U().objects.filter(is_active=True).exists() else 1)"
if not errorlevel 1 goto :run

:make_account
echo.
echo [4/4] Create YOUR employee account - first time only
echo     The password does NOT show while you type. That is normal.
echo     !! Switch the keyboard to ENGLISH before typing the password (Alt + Shift).
echo.
".venv\Scripts\python.exe" manage.py employee_add
if errorlevel 1 (
    choice /c YN /m "Try again"
    if errorlevel 2 exit /b 1
    goto :make_account
)

:run
".venv\Scripts\python.exe" manage.py eoip_reset >nul 2>&1
echo.
echo   A fresh event starts when you open the dashboard (the decision log is kept).
echo ==========================================
echo   Server is starting: http://localhost:%EOIP_PORT%
echo   The phone address is printed below (Phone (radio)).
echo   Keep this window OPEN. To stop: Ctrl + C
echo ==========================================
if not defined EOIP_NO_BROWSER start "" powershell -NoProfile -WindowStyle Hidden -Command "Start-Sleep 5; Start-Process 'http://localhost:%EOIP_PORT%'"
:serve
".venv\Scripts\python.exe" manage.py runeoip --host 0.0.0.0 --port %EOIP_PORT% --phone-port %EOIP_PHONE_PORT%
echo.
echo The server stopped. If you saw an error above, send a screenshot of this window.
choice /c YN /t 10 /d Y /m "Restart the server automatically in 10 seconds (Y) or stop (N)"
if errorlevel 2 goto :eof
goto :serve
