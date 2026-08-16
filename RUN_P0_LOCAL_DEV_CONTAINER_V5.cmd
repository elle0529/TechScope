@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0P0_PATCH_DOTNET_AND_RESUME_V5.ps1"
exit /b %ERRORLEVEL%
