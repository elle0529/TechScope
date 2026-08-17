@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0MAIN_FINAL_CHECKPOINT_V1.ps1"
exit /b %ERRORLEVEL%
