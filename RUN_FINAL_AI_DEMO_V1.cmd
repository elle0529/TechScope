@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0FINAL_AI_DEMO_V1.ps1"
exit /b %ERRORLEVEL%
