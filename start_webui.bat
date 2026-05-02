@echo off
setlocal
cd /d "%~dp0"

where powershell >nul 2>nul
if %ERRORLEVEL% EQU 0 (
  powershell -ExecutionPolicy Bypass -File "%~dp0start_webui.ps1" %*
  exit /b %ERRORLEVEL%
)

where pwsh >nul 2>nul
if %ERRORLEVEL% EQU 0 (
  pwsh -ExecutionPolicy Bypass -File "%~dp0start_webui.ps1" %*
  exit /b %ERRORLEVEL%
)

echo PowerShell was not found. Run start_webui.ps1 with PowerShell, or install PowerShell.
exit /b 1
