@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0TECHSCOPE_GITHUB_SNAPSHOT_V1.ps1"
exit /b %ERRORLEVEL%
