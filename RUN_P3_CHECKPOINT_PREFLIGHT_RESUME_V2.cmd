@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0P3_CHECKPOINT_PREFLIGHT_RESUME_V2.ps1"
exit /b %ERRORLEVEL%
