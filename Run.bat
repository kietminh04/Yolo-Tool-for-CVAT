@echo off
cd /d "%~dp0"
chcp 65001 >nul 2>&1
echo.
echo   [INIT] Booting automated forge sequence...
echo.
for %%f in (*.py) do (
    python "%%f"
    goto :end
)
echo   [FATAL] Missing core module (.py not found)!
:end
echo.
timeout /t 5 /nobreak >nul
