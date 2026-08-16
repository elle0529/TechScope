@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0LIVE_UI_POWERBI_SYNC_V4.ps1"
exit /b %ERRORLEVEL%
