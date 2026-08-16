@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0P0_PATCH_AZURECLI_AND_RESUME_V4.ps1"
exit /b %ERRORLEVEL%
