@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0P0_VALIDATE_AND_FINALIZE_V6.ps1"
exit /b %ERRORLEVEL%
