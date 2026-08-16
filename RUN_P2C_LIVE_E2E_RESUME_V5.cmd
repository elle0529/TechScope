@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0P2C_LIVE_E2E_RESUME_V5.ps1"
exit /b %ERRORLEVEL%
