@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0POWERBI_FINAL_DEMO_V7.ps1"
exit /b %ERRORLEVEL%
