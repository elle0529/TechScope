@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0P3_TEAMS_PROTOTYPE_AUTO_V1.ps1"
exit /b %ERRORLEVEL%
