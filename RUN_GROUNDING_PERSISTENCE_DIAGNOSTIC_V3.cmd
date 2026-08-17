@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0GROUNDING_PERSISTENCE_DIAGNOSTIC_V3.ps1"
exit /b %ERRORLEVEL%
