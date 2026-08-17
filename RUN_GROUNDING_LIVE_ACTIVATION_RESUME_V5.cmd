@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0GROUNDING_LIVE_ACTIVATION_RESUME_V5.ps1"
exit /b %ERRORLEVEL%
