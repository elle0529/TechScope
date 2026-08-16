@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0GITHUB_SQL_SECRET_SHAPE_DIAGNOSTIC_V1.ps1"
exit /b %ERRORLEVEL%
