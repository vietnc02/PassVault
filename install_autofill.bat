@echo off
chcp 65001 >nul
cd /d "%~dp0"
".venv\Scripts\python.exe" native\install.py %*
echo.
echo Tiep theo: mo chrome://extensions, bat "Developer mode",
echo bam "Load unpacked" va chon thu muc:
echo   %~dp0extension
echo.
pause
