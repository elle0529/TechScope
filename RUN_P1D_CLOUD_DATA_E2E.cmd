@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0P1D_VALIDATE_AND_RUN.ps1"
exit /b %ERRORLEVEL%
