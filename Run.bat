@echo off
cd /d "%~dp0"
chcp 65001 >nul 2>&1
echo.
echo   [INIT] Booting automated forge sequence...
echo.
python "Run.py"
if %errorlevel% neq 0 (
    echo.
    echo   [FATAL] Script encountered an error!
)
echo.
pause
