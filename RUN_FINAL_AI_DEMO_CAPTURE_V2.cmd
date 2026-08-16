@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0FINAL_AI_DEMO_CAPTURE_V2.ps1"
exit /b %ERRORLEVEL%
