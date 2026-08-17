@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0GROUNDING_POWERBI_GIT_CHECKPOINT_V1.ps1"
exit /b %ERRORLEVEL%
