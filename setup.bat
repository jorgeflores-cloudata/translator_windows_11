@echo off
setlocal
rem Python 3.12 tiene ruedas binarias compatibles con las dependencias de voz.
rem El entorno queda fuera de OneDrive y separado de instalaciones anteriores.
set "VENV=%LOCALAPPDATA%\DovaTranslator\dev-venv-py312"
set "READY=%VENV%\.translator-ready"

py -3.12 -c "import sys; sys.exit(sys.maxsize <= 2**32)" >nul 2>&1
if errorlevel 1 (
    echo ERROR: Se necesita Python 3.12 de 64 bits.
    echo Instalalo con: pymanager install 3.12
    goto :failed
)

if not exist "%VENV%\Scripts\python.exe" (
    py -3.12 -m venv "%VENV%"
    if errorlevel 1 goto :failed
)
"%VENV%\Scripts\python.exe" -c "import sys; sys.exit(sys.version_info[:2] != (3, 12) or sys.maxsize <= 2**32)"
if errorlevel 1 goto :failed

if exist "%READY%" del /q "%READY%"
if exist "%READY%" goto :failed
"%VENV%\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 goto :failed
"%VENV%\Scripts\python.exe" -m pip install --only-binary=:all: -r "%~dp0requirements.txt"
if errorlevel 1 goto :failed
"%VENV%\Scripts\python.exe" -m pip check
if errorlevel 1 goto :failed
"%VENV%\Scripts\python.exe" -c "import tkinter, av, ctranslate2, faster_whisper, sounddevice, keyboard, pyperclip, numpy, anthropic, openai, keyring, websockets, language_tool_python"
if errorlevel 1 goto :failed

>"%READY%" echo Python 3.12 - dependencias verificadas
if errorlevel 1 goto :failed
echo.
echo Listo. Abre la app con run.bat
if /i not "%~1"=="--no-pause" pause
exit /b 0

:failed
echo.
echo ERROR: La instalacion no se completo. Revisa el error anterior.
echo La app no se iniciara hasta completar setup.bat correctamente.
if /i not "%~1"=="--no-pause" pause
exit /b 1
