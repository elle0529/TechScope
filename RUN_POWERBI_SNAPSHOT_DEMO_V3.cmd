@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0POWERBI_SNAPSHOT_DEMO_V3.ps1"
exit /b %ERRORLEVEL%
