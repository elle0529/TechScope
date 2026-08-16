@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0P1E_RELATION_REPAIR_V1.ps1"
exit /b %ERRORLEVEL%
