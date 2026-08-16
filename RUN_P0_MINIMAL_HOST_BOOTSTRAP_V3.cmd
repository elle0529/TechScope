@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0P0_VALIDATE_AND_RUN_V3.ps1"
exit /b %ERRORLEVEL%
