@echo off
rem Gift Mall - start or restart silently
rem 1) kill previous instance(s): netstat 有时看不到本机 0.0.0.0 的 LISTENING 行，
rem    这里直接按进程名清理（本机 pythonw 只有本项目在用），可一并清掉抢不到端口的僵尸实例
rem 2) start service in background（优先 pythonw，其次 python，均要求在 PATH 中）
cd /d "%~dp0"
taskkill /f /im pythonw.exe >nul 2>&1
ping -n 2 127.0.0.1 >nul
where pythonw >nul 2>nul && (
  start "" pythonw run.py 9100,8010
  exit /b
)
where python >nul 2>nul && (
  start "" python run.py 9100,8010
  exit /b
)
echo [X] Python not found in PATH. Install Python 3.8+,
echo     or edit this script to point to your pythonw.exe.
pause
