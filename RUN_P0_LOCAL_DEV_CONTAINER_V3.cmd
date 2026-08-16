@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0P0_VALIDATE_AND_RESUME_LOCAL_DEV_CONTAINER_V3.ps1"
exit /b %ERRORLEVEL%
