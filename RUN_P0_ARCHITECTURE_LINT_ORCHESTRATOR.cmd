@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0P0_VALIDATE_AND_INSTALL_ARCHITECTURE_LINT_ORCHESTRATOR.ps1"
exit /b %ERRORLEVEL%
