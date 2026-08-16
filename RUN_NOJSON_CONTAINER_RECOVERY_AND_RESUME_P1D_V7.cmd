@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0NOJSON_CONTAINER_RECOVERY_AND_RESUME_P1D_V7.ps1"
exit /b %ERRORLEVEL%