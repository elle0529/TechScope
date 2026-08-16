@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0POWERBI_SNAPSHOT_LAUNCH_V1.ps1"
exit /b %ERRORLEVEL%
