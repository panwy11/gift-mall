@echo off
setlocal enabledelayedexpansion
rem Gift Mall - install per-user auto-start (no admin required)
rem Installs a silent VBS launcher into the current user's Startup folder.
rem Remove anytime with autostart-remove.bat
cd /d "%~dp0"

set "PYW="
for /f "delims=" %%i in ('where pythonw 2^>nul') do if not defined PYW set "PYW=%%i"
if not defined PYW (
  for /f "delims=" %%i in ('where python 2^>nul') do (
    if not defined PYW if exist "%%~dpipythonw.exe" set "PYW=%%~dpipythonw.exe"
  )
)

set "ARG=run.py"
if defined PYW if not exist "!PYW!" set "PYW="
if not defined PYW (
  if exist "dist\gift-mall.exe" (
    set "PYW=%~dp0dist\gift-mall.exe"
    set "ARG="
  ) else (
    echo [ERROR] Python not found and dist\gift-mall.exe not found.
    echo Install Python 3.8+ first, or run build_exe.py to create the exe.
    pause
    exit /b 1
  )
)

set "STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "VBS=%STARTUP%\gift-mall-autostart.vbs"

> "%VBS%" (
  echo Set sh = CreateObject^("WScript.Shell"^)
  echo sh.CurrentDirectory = "%~dp0"
  echo sh.Run """!PYW!"" !ARG!", 0, False
)

echo.
echo ===== Auto-start installed (no admin needed) =====
echo   Startup : %VBS%
echo   Command : "!PYW!" !ARG!
echo.
echo The mall service will start silently every time you log on
echo (no black window). Ports default to 9100 + 8010.
echo Remove anytime with autostart-remove.bat
echo.
echo Tip: run "install" only once. If you move this folder,
echo run remove + install again.
pause
