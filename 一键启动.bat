@echo off
rem Gift Mall - one click start
cd /d "%~dp0"
set GM_OPEN=1
where py >nul 2>nul && (py -3 run.py & goto :done)
where python >nul 2>nul && (python run.py & goto :done)
echo [ERROR] Python 3 not found. Please install Python 3.8+ (check "Add to PATH").
echo Download: https://www.python.org/downloads/
pause
exit /b 1
:done
pause
