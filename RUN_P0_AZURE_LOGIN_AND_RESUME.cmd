@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0P0_VALIDATE_AZURE_LOGIN_AND_RESUME.ps1"
exit /b %ERRORLEVEL%
