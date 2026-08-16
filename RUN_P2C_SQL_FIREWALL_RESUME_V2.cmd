@echo off
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0P2C_SQL_FIREWALL_RESUME_V2.ps1"
exit /b %ERRORLEVEL%
