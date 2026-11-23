@echo off
rem Gift Mall - remove per-user auto-start
set "VBS=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\gift-mall-autostart.vbs"
if exist "%VBS%" (
  del "%VBS%"
  echo Auto-start removed.
) else (
  echo Auto-start is not installed.
)
echo Note: this does NOT stop a service that is already running.
pause
