@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0ZERO_READINESS_VALIDATE_AND_RUN.ps1"
exit /b %ERRORLEVEL%
