@echo off
setlocal
cd /d C:\TechScope

if not exist "%~dp0P0_MINIMAL_HOST_BOOTSTRAP.ps1" (
  echo P0_MINIMAL_HOST_BOOTSTRAP.ps1 not found.
  exit /b 1
)

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0P0_MINIMAL_HOST_BOOTSTRAP.ps1"
exit /b %ERRORLEVEL%
