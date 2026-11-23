@echo off
rem Gift Mall - test data cleanup tool (GUI, needs tkinter)
cd /d "%~dp0"
rem 1) pythonw / python on PATH
where pythonw >nul 2>nul && (
  start "" pythonw "cleanup-data.py"
  exit /b
)
where python >nul 2>nul && (
  start "" python "cleanup-data.py"
  exit /b
)
echo [X] Python with tkinter not found. Run cleanup-data.py --auto instead.
pause
