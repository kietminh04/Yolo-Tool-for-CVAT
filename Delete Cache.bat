@echo off
cd /d "%~dp0"
chcp 65001 >nul 2>&1
echo.
echo   [INIT] Initiating cache destruction protocol...
echo.
python Delete_Cache.py
echo.
timeout /t 5 /nobreak >nul
