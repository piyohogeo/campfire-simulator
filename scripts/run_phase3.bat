@echo off
setlocal
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0run_phase3.ps1" %*
exit /b %ERRORLEVEL%
