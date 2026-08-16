@echo off
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0P2C_PASSWORDLESS_SQL_SETUP_V1.ps1"
exit /b %ERRORLEVEL%
