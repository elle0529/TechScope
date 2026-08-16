@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0VALIDATE_AND_RUN_REMEDIATION_R1.ps1"
exit /b %ERRORLEVEL%
