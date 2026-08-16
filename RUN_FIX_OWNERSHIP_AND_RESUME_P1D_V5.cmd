@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0FIX_OWNERSHIP_AND_RESUME_P1D_V5.ps1"
exit /b %ERRORLEVEL%
