@echo off
setlocal
set "PYW=%~dp0.venv\Scripts\pythonw.exe"
if exist "%PYW%" goto run
set "PYW=%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\pythonw.exe"
if exist "%PYW%" goto run
where pyw >nul 2>&1
if errorlevel 1 goto missing
start "" pyw -3.12 "%~dp0connector\bridge\app.py"
exit /b
:run
start "" "%PYW%" "%~dp0connector\bridge\app.py"
exit /b
:missing
echo Please install Windows Python 3.12, then run install_dependencies.bat.
pause
