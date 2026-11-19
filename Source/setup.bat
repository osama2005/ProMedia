@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"

echo ============================================================
echo   Pro Media Downloader - setup
echo ============================================================

set "VENV=..\.venv"

set "PYTHON="
where py >nul 2>nul
if not errorlevel 1 set "PYTHON=py -3"
if not defined PYTHON (
    where python >nul 2>nul
    if not errorlevel 1 set "PYTHON=python"
)
if not defined PYTHON (
    echo [X] Python 3.10+ was not found.
    echo     Install it from https://www.python.org/downloads/
    echo     or run: winget install Python.Python.3.12
    pause
    exit /b 1
)

if not exist "%VENV%\Scripts\python.exe" (
    echo [1/3] Creating virtual environment in %VENV%...
    %PYTHON% -m venv "%VENV%"
    if errorlevel 1 (
        echo [X] Could not create the virtual environment.
        pause
        exit /b 1
    )
) else (
    echo [1/3] Virtual environment already exists.
)

echo [2/3] Installing Python packages...
"%VENV%\Scripts\python.exe" -m pip install --upgrade pip >nul
"%VENV%\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
    echo [X] Package installation failed.
    pause
    exit /b 1
)

echo [3/3] Checking external tools...
where ffmpeg >nul 2>nul
if errorlevel 1 (
    if exist "bin\ffmpeg.exe" (
        echo     FFmpeg: found in .\bin
    ) else (
        echo     [!] FFmpeg is NOT installed.
        echo         Run: winget install Gyan.FFmpeg
        echo         or put ffmpeg.exe in the "bin" folder.
    )
) else (
    echo     FFmpeg: OK
)

where deno >nul 2>nul
if errorlevel 1 (
    echo     [!] Deno (JavaScript runtime for YouTube) was not found.
    echo         Run: winget install DenoLand.Deno
) else (
    echo     Deno: OK
)

echo.
echo ============================================================
echo   Setup finished. Start the app with run.bat
echo ============================================================
pause
endlocal
