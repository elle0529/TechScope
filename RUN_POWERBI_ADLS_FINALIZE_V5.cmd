@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0POWERBI_ADLS_FINALIZE_V5.ps1"
exit /b %ERRORLEVEL%
