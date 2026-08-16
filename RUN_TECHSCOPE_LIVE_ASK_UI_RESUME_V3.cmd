@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0TECHSCOPE_LIVE_ASK_UI_RESUME_V3.ps1"
exit /b %ERRORLEVEL%
