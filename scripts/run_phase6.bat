@echo off
setlocal
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0run_phase6.ps1" %*
exit /b %ERRORLEVEL%
