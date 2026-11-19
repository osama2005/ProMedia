@echo off
setlocal
cd /d "%~dp0"

rem Source\ holds the code; the virtual environment stays at the project root.
set "PY=.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=..\.venv\Scripts\python.exe"

if exist "%PY%" (
    "%PY%" main.py
) else (
    echo [!] Virtual environment not found. Run setup.bat first.
    echo     Trying the system Python...
    python main.py
)

if errorlevel 1 (
    echo.
    echo [!] The application exited with an error. See the log above.
    pause
)
endlocal
