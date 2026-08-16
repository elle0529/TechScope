@echo off
setlocal
cd /d C:\TechScope

if not exist "P0_CREATE_SCAFFOLD.ps1" (
  echo P0_CREATE_SCAFFOLD.ps1 not found in C:\TechScope
  exit /b 1
)

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%CD%\P0_CREATE_SCAFFOLD.ps1"
exit /b %ERRORLEVEL%
