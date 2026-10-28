@echo off
cd /d "%~dp0"
py -3.12 tools\setup.py
if errorlevel 1 pause
