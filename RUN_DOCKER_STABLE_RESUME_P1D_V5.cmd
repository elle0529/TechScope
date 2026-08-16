@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0START_DOCKER_STABLE_AND_RESUME_P1D_V5.ps1"
exit /b %ERRORLEVEL%
