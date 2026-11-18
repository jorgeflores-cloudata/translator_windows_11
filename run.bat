@echo off
setlocal
set "VENV=%LOCALAPPDATA%\DovaTranslator\dev-venv-py312"
if not exist "%VENV%\Scripts\pythonw.exe" goto :setup
if not exist "%VENV%\.translator-ready" goto :setup
goto :launch

:setup
call "%~dp0setup.bat" --no-pause
if errorlevel 1 (
    pause
    exit /b 1
)

:launch
start "" /d "%~dp0" "%VENV%\Scripts\pythonw.exe" -I -B "%~dp0app\launcher.py"
