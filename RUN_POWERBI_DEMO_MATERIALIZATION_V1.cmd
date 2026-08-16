@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0POWERBI_DEMO_MATERIALIZATION_V1.ps1"
exit /b %ERRORLEVEL%
