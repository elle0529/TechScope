@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0P2C_SQL_PERSISTENCE_E2E_V1.ps1"
exit /b %ERRORLEVEL%
