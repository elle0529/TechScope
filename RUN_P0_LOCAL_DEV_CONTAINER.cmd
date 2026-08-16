@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0P0_VALIDATE_AND_BUILD_LOCAL_DEV_CONTAINER.ps1"
exit /b %ERRORLEVEL%
