@echo off
setlocal
set "PYW=%~dp0.venv\Scripts\pythonw.exe"
if exist "%PYW%" goto run
set "PYW=%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\pythonw.exe"
if exist "%PYW%" goto run
start "" pyw -3.12 "%~dp0xiangqi.py"
exit /b
:run
start "" "%PYW%" "%~dp0xiangqi.py"
