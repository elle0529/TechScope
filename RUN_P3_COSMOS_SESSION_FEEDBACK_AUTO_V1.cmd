@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0P3_COSMOS_SESSION_FEEDBACK_AUTO_V1.ps1"
exit /b %ERRORLEVEL%
