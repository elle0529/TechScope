@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0P1E_SQL_FIREWALL_RESUME_V8.ps1"
exit /b %ERRORLEVEL%
