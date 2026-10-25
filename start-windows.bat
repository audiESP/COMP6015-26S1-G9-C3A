@echo off
setlocal EnableExtensions

rem Always resolve paths relative to this file, so it works when double-clicked.
set "ROOT=%~dp0"
set "CORE_DIR=%ROOT%c3a-core"
set "UI_DIR=%CORE_DIR%\c3a-core-ui"
set "API_DIR=%CORE_DIR%\c3a-core-api"
set "AI_DIR=%CORE_DIR%\c3a-core-ai"
set "OLLAMA_MODEL=llama3.1:8b-instruct-q4_K_M"

if not exist "%UI_DIR%\package.json" goto :missing_ui
if not exist "%API_DIR%\main.py" goto :missing_api
if not exist "%AI_DIR%\main.py" goto :missing_ai

where npm >nul 2>&1
if errorlevel 1 goto :missing_npm

set "OLLAMA_EXE="
ollama --version >nul 2>&1
if not errorlevel 1 set "OLLAMA_EXE=ollama"
if not defined OLLAMA_EXE if exist "%LOCALAPPDATA%\Programs\Ollama\ollama.exe" set "OLLAMA_EXE=%LOCALAPPDATA%\Programs\Ollama\ollama.exe"
if not defined OLLAMA_EXE goto :missing_ollama

set "API_PYTHON="
set "AI_PYTHON="
set "API_PYTHON_ARGS="
set "AI_PYTHON_ARGS="
set "SYSTEM_PYTHON="
set "SYSTEM_PYTHON_ARGS="

if exist "%CORE_DIR%\.venv\Scripts\python.exe" (
    set "API_PYTHON=%CORE_DIR%\.venv\Scripts\python.exe"
    set "AI_PYTHON=%CORE_DIR%\.venv\Scripts\python.exe"
)
if not defined API_PYTHON if exist "%API_DIR%\.venv\Scripts\python.exe" set "API_PYTHON=%API_DIR%\.venv\Scripts\python.exe"
if not defined AI_PYTHON if exist "%AI_DIR%\.venv\Scripts\python.exe" set "AI_PYTHON=%AI_DIR%\.venv\Scripts\python.exe"

where py >nul 2>&1
if not errorlevel 1 (
    set "SYSTEM_PYTHON=py"
    set "SYSTEM_PYTHON_ARGS=-3"
)

if not defined SYSTEM_PYTHON (
    where python >nul 2>&1
    if not errorlevel 1 set "SYSTEM_PYTHON=python"
)

if not defined API_PYTHON (
    set "API_PYTHON=%SYSTEM_PYTHON%"
    set "API_PYTHON_ARGS=%SYSTEM_PYTHON_ARGS%"
)
if not defined AI_PYTHON (
    set "AI_PYTHON=%SYSTEM_PYTHON%"
    set "AI_PYTHON_ARGS=%SYSTEM_PYTHON_ARGS%"
)

if not defined API_PYTHON goto :missing_python
if not defined AI_PYTHON goto :missing_python

if /I "%~1"=="--check" (
    echo C3A startup preflight passed.
    echo API Python: %API_PYTHON% %API_PYTHON_ARGS%
    echo AI Python:  %AI_PYTHON% %AI_PYTHON_ARGS%
    echo npm: available
    echo Ollama: %OLLAMA_EXE%
    echo AI model: %OLLAMA_MODEL%
    "%OLLAMA_EXE%" list >nul 2>&1
    if errorlevel 1 (
        echo Ollama server: not running; normal startup will start it
    ) else (
        echo Ollama server: running
        "%OLLAMA_EXE%" show "%OLLAMA_MODEL%" >nul 2>&1
        if errorlevel 1 (
            echo AI model status: not installed; normal startup will pull it
        ) else (
            echo AI model status: installed
        )
    )
    exit /b 0
)

"%OLLAMA_EXE%" list >nul 2>&1
if errorlevel 1 (
    echo Starting Ollama server...
    start "C3A Ollama" /MIN cmd /k ""%OLLAMA_EXE%" serve"
    call :wait_for_ollama
    if errorlevel 1 goto :ollama_start_failed
) else (
    echo Ollama server is already running.
)

"%OLLAMA_EXE%" show "%OLLAMA_MODEL%" >nul 2>&1
if errorlevel 1 (
    echo Pulling Ollama model %OLLAMA_MODEL% ^(about 4.9 GB^)...
    "%OLLAMA_EXE%" pull "%OLLAMA_MODEL%"
    if errorlevel 1 goto :ollama_pull_failed
) else (
    echo Ollama model is ready: %OLLAMA_MODEL%
)

echo Starting C3A AI, API, and UI with model %OLLAMA_MODEL%...
echo Close each service window or press Ctrl+C in it to stop that service.

start "C3A AI" /D "%AI_DIR%" cmd /k ""%AI_PYTHON%" %AI_PYTHON_ARGS% main.py"
start "C3A API" /D "%API_DIR%" cmd /k ""%API_PYTHON%" %API_PYTHON_ARGS% main.py"
start "C3A UI" /D "%UI_DIR%" cmd /k "npm start"

echo All three service windows have been opened.
exit /b 0

:wait_for_ollama
for /L %%I in (1,1,30) do (
    "%OLLAMA_EXE%" list >nul 2>&1
    if not errorlevel 1 exit /b 0
    timeout /t 1 /nobreak >nul
)
exit /b 1

:missing_ui
echo ERROR: UI entrypoint not found: "%UI_DIR%\package.json"
goto :failed

:missing_api
echo ERROR: API entrypoint not found: "%API_DIR%\main.py"
goto :failed

:missing_ai
echo ERROR: AI entrypoint not found: "%AI_DIR%\main.py"
goto :failed

:missing_npm
echo ERROR: npm was not found on PATH. Install Node.js and reopen this window.
goto :failed

:missing_python
echo ERROR: Python was not found. Create .venv in this folder or install Python 3.
goto :failed

:missing_ollama
echo ERROR: Ollama was not found. Install Ollama and reopen this window.
goto :failed

:ollama_start_failed
echo ERROR: Ollama server did not become ready within 30 seconds.
goto :failed

:ollama_pull_failed
echo ERROR: Failed to pull Ollama model %OLLAMA_MODEL%.
goto :failed

:failed
echo.
pause
exit /b 1
