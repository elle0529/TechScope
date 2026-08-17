@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0GROUNDING_FALSE_POSITIVE_RESUME_V2.ps1"
exit /b %ERRORLEVEL%
