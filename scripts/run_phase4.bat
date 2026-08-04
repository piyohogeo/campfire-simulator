@echo off
setlocal
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0run_phase4.ps1" %*
exit /b %ERRORLEVEL%
