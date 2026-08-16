@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0TECHSCOPE_LIVE_ASK_UI_V1.ps1"
exit /b %ERRORLEVEL%
