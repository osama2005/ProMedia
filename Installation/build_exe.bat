@echo off
setlocal
cd /d "%~dp0"

rem Code lives in ..\Source ; the virtual environment stays at the project root.
set "PY=..\.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=python"

echo Building the standalone Windows executable...
"%PY%" -m PyInstaller ^
    --noconfirm --clean --onefile --windowed ^
    --name "ProMediaDownloader" ^
    --icon "..\Source\assets\app.ico" ^
    --add-data "..\Source\assets;assets" ^
    --collect-submodules qrcode ^
    --collect-all tkinterdnd2 ^
    ..\Source\main.py

if not exist "dist\ProMediaDownloader.exe" (
    echo.
    echo [X] Build failed. Read the PyInstaller output above.
    pause
    exit /b 1
)
echo.
echo Done: Installation\dist\ProMediaDownloader.exe

set "ISCC=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
if exist "%ISCC%" (
    echo.
    echo Building the installer...
    "%ISCC%" "installer\taif_setup.iss"
    if exist "dist\Taif_Setup_v1.0.9.exe" (
        echo Done: Installation\dist\Taif_Setup_v1.0.9.exe
    )
) else (
    echo.
    echo [i] Inno Setup was not found; skipping the installer.
    echo     Install it from https://jrsoftware.org/isinfo.php then rerun this file.
)

pause
endlocal
