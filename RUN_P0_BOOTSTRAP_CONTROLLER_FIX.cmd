@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0P0_FIX_AND_RUN_BOOTSTRAP_CONTROLLER.ps1"
exit /b %ERRORLEVEL%
