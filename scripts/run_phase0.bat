@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0run_phase0.ps1" %*
exit /b %ERRORLEVEL%
