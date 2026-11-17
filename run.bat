@echo off
rem Double-click to start the Document Verification dashboard.
rem Portable: copy this folder to any Windows 10/11 PC and run this file.
rem - Installs Python 3.12 (per-user, via winget) if no Python 3.10+ is found.
rem - Rebuilds .venv if it is missing or was copied from another PC.
cd /d "%~dp0"

rem Find a real Python 3.10+ (the Microsoft Store "python" alias does not count).
set "PYEXE="
set "PYARGS="
python -c "import sys; sys.exit(sys.version_info < (3, 10))" >nul 2>nul
if not errorlevel 1 set "PYEXE=python"
if not defined PYEXE (
    py -3 -c "import sys; sys.exit(sys.version_info < (3, 10))" >nul 2>nul
    if not errorlevel 1 (
        set "PYEXE=py"
        set "PYARGS=-3"
    )
)
if not defined PYEXE (
    echo Python not found - installing Python 3.12 for this user with winget...
    winget install -e --id Python.Python.3.12 --scope user --silent --accept-package-agreements --accept-source-agreements
    if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" set "PYEXE=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
)
if not defined PYEXE (
    echo Python 3.10+ is required. Install it from https://www.python.org/downloads/ and run this file again.
    pause
    exit /b 1
)

.venv\Scripts\python.exe -c "import fastapi, uvicorn, multipart, pypdf, PIL, stdnum" >nul 2>nul
if errorlevel 1 (
    echo First run on this PC - setting up the environment, please wait...
    if exist .venv rmdir /s /q .venv
    "%PYEXE%" %PYARGS% -m venv .venv
    if errorlevel 1 (
        echo Could not create the virtual environment.
        pause
        exit /b 1
    )
    .venv\Scripts\python.exe -m pip install --disable-pip-version-check -q -r requirements.txt
    if errorlevel 1 (
        echo Installing dependencies failed. Check the internet connection and try again.
        pause
        exit /b 1
    )
)

rem Open the browser once the server has had a moment to start.
start "" /min powershell -NoProfile -WindowStyle Hidden -Command "Start-Sleep 2; Start-Process 'http://127.0.0.1:8000'"
echo Dashboard: http://127.0.0.1:8000   (keep this window open; close it to stop the server)
.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
pause
