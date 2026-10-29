@echo off
setlocal EnableExtensions

rem Always resolve paths relative to this file, so it works when double-clicked.
set "ROOT=%~dp0"
set "CORE_DIR=%ROOT%c3a-core"
set "UI_DIR=%CORE_DIR%\c3a-core-ui"
set "API_DIR=%CORE_DIR%\c3a-core-api"
set "AI_DIR=%CORE_DIR%\c3a-core-ai"
set "ENV_SYNC_SCRIPT=%ROOT%tools\sync_env.py"
set "OLLAMA_MODEL=llama3.1:8b-instruct-q4_K_M"
set "SPEECH_COMPOSE_FILE=%CORE_DIR%\docker-compose.speech.yml"
set "SPEECH_HEALTH_URL=http://127.0.0.1:8002/health"
if not defined C3A_SPEECH_MODELS_DIR set "C3A_SPEECH_MODELS_DIR=%USERPROFILE%\.c3a\models"
set "CHECK_ONLY="
set "ENV_SOURCE_DIR="

rem Usage: start-windows.bat [--check] [ENV_FOLDER]
rem ENV_FOLDER holds .env files laid out like this repository, e.g.
rem ENV_FOLDER\c3a-core\c3a-core-api\.env; they are copied in before startup.
:parse_args
if "%~1"=="" goto :args_parsed
if /I "%~1"=="--check" (
    set "CHECK_ONLY=1"
    shift
    goto :parse_args
)
set "C3A_ARG=%~1"
if "%C3A_ARG:~0,1%"=="-" goto :unknown_option
if defined ENV_SOURCE_DIR goto :too_many_env_folders
set "ENV_SOURCE_DIR=%~f1"
shift
goto :parse_args
:args_parsed
set "ENV_SYNC_ARGS="
if defined CHECK_ONLY set "ENV_SYNC_ARGS=--check"
if defined ENV_SOURCE_DIR set ENV_SYNC_ARGS=%ENV_SYNC_ARGS% --import-from "%ENV_SOURCE_DIR%"

if not exist "%UI_DIR%\package.json" goto :missing_ui
if not exist "%API_DIR%\main.py" goto :missing_api
if not exist "%AI_DIR%\main.py" goto :missing_ai
if not exist "%API_DIR%\requirements.txt" goto :missing_api_requirements
if not exist "%AI_DIR%\requirements.txt" goto :missing_ai_requirements
if not exist "%ENV_SYNC_SCRIPT%" goto :missing_env_sync_script
if not exist "%SPEECH_COMPOSE_FILE%" goto :missing_speech_compose
if not exist "%AI_DIR%\Dockerfile.speech" goto :missing_speech_dockerfile
if not exist "%AI_DIR%\requirements.speech.txt" goto :missing_speech_requirements

call :locate_docker
if errorlevel 1 goto :missing_docker
"%DOCKER_EXE%" compose version >nul 2>&1
if errorlevel 1 goto :missing_docker_compose
wsl.exe --version >nul 2>&1
if errorlevel 1 goto :wsl_not_ready
call :validate_speech_models
if errorlevel 1 goto :failed
"%DOCKER_EXE%" compose -f "%SPEECH_COMPOSE_FILE%" config --quiet >nul 2>&1
if errorlevel 1 goto :invalid_speech_compose

where node >nul 2>&1
if errorlevel 1 goto :missing_node
where npm >nul 2>&1
if errorlevel 1 goto :missing_npm
node --version >nul 2>&1
if errorlevel 1 goto :broken_node
call npm --version >nul 2>&1
if errorlevel 1 goto :broken_npm

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
"%API_PYTHON%" %API_PYTHON_ARGS% -m pip --version >nul 2>&1
if errorlevel 1 goto :missing_api_pip
"%AI_PYTHON%" %AI_PYTHON_ARGS% -m pip --version >nul 2>&1
if errorlevel 1 goto :missing_ai_pip

if defined CHECK_ONLY (
    call :run_env_sync
    if errorlevel 1 goto :failed
    echo C3A startup preflight passed.
    echo API Python: %API_PYTHON% %API_PYTHON_ARGS%
    echo AI Python:  %AI_PYTHON% %AI_PYTHON_ARGS%
    echo Python requirements: found; normal startup will install them
    node --version
    call npm --version
    call :check_ui_dependencies
    if errorlevel 1 (
        echo UI dependencies: missing or invalid; normal startup will run npm ci
    ) else (
        echo UI dependencies: installed and valid
    )
    echo Ollama: %OLLAMA_EXE%
    echo AI model: %OLLAMA_MODEL%
    echo Docker: %DOCKER_EXE%
    "%DOCKER_EXE%" compose version
    echo Speech models: %C3A_SPEECH_MODELS_DIR%
    "%DOCKER_EXE%" info >nul 2>&1
    if errorlevel 1 (
        echo Docker engine: not running; normal startup will start Docker Desktop
    ) else (
        echo Docker engine: running
    )
    call :speech_is_healthy
    if errorlevel 1 (
        echo Speech service: not ready; normal startup will build or start it
    ) else (
        echo Speech service: healthy and models loaded
    )
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

call :run_env_sync
if errorlevel 1 goto :failed

echo Installing API Python requirements...
"%API_PYTHON%" %API_PYTHON_ARGS% -m pip install -r "%API_DIR%\requirements.txt"
if errorlevel 1 goto :api_requirements_failed

echo Installing AI Python requirements...
"%AI_PYTHON%" %AI_PYTHON_ARGS% -m pip install -r "%AI_DIR%\requirements.txt"
if errorlevel 1 goto :ai_requirements_failed

call :ensure_ui_dependencies
if errorlevel 1 goto :ui_requirements_failed

call :ensure_speech_service
if errorlevel 1 goto :failed

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

echo All three service windows have been opened. The speech container is healthy on port 8002.
exit /b 0

:locate_docker
set "DOCKER_EXE="
set "DOCKER_DESKTOP_EXE="
for /f "delims=" %%D in ('where docker 2^>nul') do if not defined DOCKER_EXE set "DOCKER_EXE=%%D"
if not defined DOCKER_EXE if exist "%LOCALAPPDATA%\Programs\DockerDesktop\resources\bin\docker.exe" set "DOCKER_EXE=%LOCALAPPDATA%\Programs\DockerDesktop\resources\bin\docker.exe"
if not defined DOCKER_EXE if exist "%ProgramFiles%\Docker\Docker\resources\bin\docker.exe" set "DOCKER_EXE=%ProgramFiles%\Docker\Docker\resources\bin\docker.exe"
if exist "%LOCALAPPDATA%\Programs\DockerDesktop\Docker Desktop.exe" set "DOCKER_DESKTOP_EXE=%LOCALAPPDATA%\Programs\DockerDesktop\Docker Desktop.exe"
if not defined DOCKER_DESKTOP_EXE if exist "%ProgramFiles%\Docker\Docker\Docker Desktop.exe" set "DOCKER_DESKTOP_EXE=%ProgramFiles%\Docker\Docker\Docker Desktop.exe"
if not defined DOCKER_EXE exit /b 1
for %%D in ("%DOCKER_EXE%") do set "PATH=%%~dpD;%PATH%"
"%DOCKER_EXE%" --version >nul 2>&1
if errorlevel 1 exit /b 1
exit /b 0

:validate_speech_models
if not exist "%C3A_SPEECH_MODELS_DIR%\whisper-base\base-encoder.int8.onnx" (
    set "C3A_STARTUP_ERROR=Whisper encoder not found: %C3A_SPEECH_MODELS_DIR%\whisper-base\base-encoder.int8.onnx"
    exit /b 1
)
if not exist "%C3A_SPEECH_MODELS_DIR%\whisper-base\base-decoder.int8.onnx" (
    set "C3A_STARTUP_ERROR=Whisper decoder not found: %C3A_SPEECH_MODELS_DIR%\whisper-base\base-decoder.int8.onnx"
    exit /b 1
)
if not exist "%C3A_SPEECH_MODELS_DIR%\whisper-base\base-tokens.txt" (
    set "C3A_STARTUP_ERROR=Whisper tokens not found: %C3A_SPEECH_MODELS_DIR%\whisper-base\base-tokens.txt"
    exit /b 1
)
for %%F in ("%C3A_SPEECH_MODELS_DIR%\whisper-base\base-encoder.int8.onnx") do if %%~zF LSS 20000000 (
    set "C3A_STARTUP_ERROR=Whisper encoder is incomplete or corrupt: %%~fF"
    exit /b 1
)
for %%F in ("%C3A_SPEECH_MODELS_DIR%\whisper-base\base-decoder.int8.onnx") do if %%~zF LSS 100000000 (
    set "C3A_STARTUP_ERROR=Whisper decoder is incomplete or corrupt: %%~fF"
    exit /b 1
)
for %%F in ("%C3A_SPEECH_MODELS_DIR%\whisper-base\base-tokens.txt") do if %%~zF LSS 500000 (
    set "C3A_STARTUP_ERROR=Whisper tokens file is incomplete or corrupt: %%~fF"
    exit /b 1
)
exit /b 0

:ensure_speech_service
call :speech_is_healthy
if not errorlevel 1 (
    echo Speech service is already healthy on port 8002.
    exit /b 0
)

"%DOCKER_EXE%" info >nul 2>&1
if errorlevel 1 (
    if not defined DOCKER_DESKTOP_EXE (
        set "C3A_STARTUP_ERROR=Docker engine is not running and Docker Desktop could not be located."
        exit /b 1
    )
    echo Starting Docker Desktop...
    start "Docker Desktop" "%DOCKER_DESKTOP_EXE%"
    call :wait_for_docker
    if errorlevel 1 (
        set "C3A_STARTUP_ERROR=Docker Desktop did not become ready within 3 minutes. Open Docker Desktop, accept any first-run prompt, and retry."
        exit /b 1
    )
)

echo Building and starting the local speech service...
"%DOCKER_EXE%" compose -f "%SPEECH_COMPOSE_FILE%" up -d --build
if errorlevel 1 (
    set "C3A_STARTUP_ERROR=Failed to build or start the local speech container."
    exit /b 1
)
call :wait_for_speech
if errorlevel 1 (
    "%DOCKER_EXE%" compose -f "%SPEECH_COMPOSE_FILE%" logs --tail 40 c3a-speech
    set "C3A_STARTUP_ERROR=Speech service did not load its models within 2 minutes. The latest container logs are shown above."
    exit /b 1
)
echo Speech service is healthy and its models are loaded.
exit /b 0

:speech_is_healthy
powershell -NoProfile -ExecutionPolicy Bypass -Command "$h = Invoke-RestMethod -Uri '%SPEECH_HEALTH_URL%' -TimeoutSec 3; if (-not ($h.enabled -and $h.loaded -and $h.backend -eq 'whisper_onnx' -and $h.model -eq 'whisper-base-int8')) { exit 1 }" >nul 2>&1
exit /b %ERRORLEVEL%

:wait_for_docker
for /L %%I in (1,1,180) do (
    "%DOCKER_EXE%" info >nul 2>&1
    if not errorlevel 1 exit /b 0
    timeout /t 1 /nobreak >nul
)
exit /b 1

:wait_for_speech
for /L %%I in (1,1,120) do (
    call :speech_is_healthy
    if not errorlevel 1 exit /b 0
    timeout /t 1 /nobreak >nul
)
exit /b 1

:wait_for_ollama
for /L %%I in (1,1,30) do (
    "%OLLAMA_EXE%" list >nul 2>&1
    if not errorlevel 1 exit /b 0
    timeout /t 1 /nobreak >nul
)
exit /b 1

:run_env_sync
set "ENV_SYNC_LOG=%TEMP%\c3a-env-sync-%RANDOM%-%RANDOM%.log"
"%API_PYTHON%" %API_PYTHON_ARGS% "%ENV_SYNC_SCRIPT%" --root "%ROOT%." %ENV_SYNC_ARGS% >"%ENV_SYNC_LOG%" 2>&1
set "ENV_SYNC_EXIT=%ERRORLEVEL%"
if "%ENV_SYNC_EXIT%"=="0" goto :env_sync_succeeded
set "C3A_STARTUP_ERROR=Environment validation or synchronization failed. See the terminal for details."
for /f "usebackq delims=" %%L in ("%ENV_SYNC_LOG%") do set "C3A_STARTUP_ERROR=%%L"
set "C3A_STARTUP_ERROR=%C3A_STARTUP_ERROR:ERROR: =%"
del /q "%ENV_SYNC_LOG%" >nul 2>&1
exit /b 1

:env_sync_succeeded
type "%ENV_SYNC_LOG%"
del /q "%ENV_SYNC_LOG%" >nul 2>&1
exit /b 0

:ensure_ui_dependencies
pushd "%UI_DIR%"
if errorlevel 1 exit /b 1
if not exist "node_modules" goto :install_ui_dependencies
call npm ls --depth=0 >nul 2>&1
if errorlevel 1 goto :install_ui_dependencies
echo UI dependencies are installed and valid.
popd
exit /b 0

:install_ui_dependencies
echo Installing UI dependencies...
if not exist "package-lock.json" goto :install_ui_without_lock
call npm ci
if errorlevel 1 goto :ui_install_failed
popd
exit /b 0

:install_ui_without_lock
call npm install
if errorlevel 1 goto :ui_install_failed
popd
exit /b 0

:ui_install_failed
popd
exit /b 1

:check_ui_dependencies
pushd "%UI_DIR%"
if errorlevel 1 exit /b 1
if not exist "node_modules" goto :ui_dependencies_invalid
call npm ls --depth=0 >nul 2>&1
if errorlevel 1 goto :ui_dependencies_invalid
popd
exit /b 0

:ui_dependencies_invalid
popd
exit /b 1

:unknown_option
set "C3A_STARTUP_ERROR=Unknown option: %C3A_ARG%"
goto :failed

:too_many_env_folders
set "C3A_STARTUP_ERROR=Only one environment folder may be given."
goto :failed

:missing_ui
set "C3A_STARTUP_ERROR=UI entrypoint not found: %UI_DIR%\package.json"
goto :failed

:missing_api
set "C3A_STARTUP_ERROR=API entrypoint not found: %API_DIR%\main.py"
goto :failed

:missing_ai
set "C3A_STARTUP_ERROR=AI entrypoint not found: %AI_DIR%\main.py"
goto :failed

:missing_api_requirements
set "C3A_STARTUP_ERROR=API requirements not found: %API_DIR%\requirements.txt"
goto :failed

:missing_ai_requirements
set "C3A_STARTUP_ERROR=AI requirements not found: %AI_DIR%\requirements.txt"
goto :failed

:missing_env_sync_script
set "C3A_STARTUP_ERROR=Environment checker not found: %ENV_SYNC_SCRIPT%"
goto :failed

:missing_speech_compose
set "C3A_STARTUP_ERROR=Speech Compose file not found: %SPEECH_COMPOSE_FILE%"
goto :failed

:missing_speech_dockerfile
set "C3A_STARTUP_ERROR=Speech Dockerfile not found: %AI_DIR%\Dockerfile.speech"
goto :failed

:missing_speech_requirements
set "C3A_STARTUP_ERROR=Speech requirements not found: %AI_DIR%\requirements.speech.txt"
goto :failed

:missing_docker
set "C3A_STARTUP_ERROR=Docker Desktop was not found. Install Docker Desktop and reopen this window."
goto :failed

:missing_docker_compose
set "C3A_STARTUP_ERROR=Docker Compose is unavailable. Repair or update Docker Desktop and retry."
goto :failed

:wsl_not_ready
set "C3A_STARTUP_ERROR=WSL 2 is unavailable or a pending Windows restart has not completed. Restart Windows, then retry."
goto :failed

:invalid_speech_compose
set "C3A_STARTUP_ERROR=Speech Compose configuration is invalid. Check C3A_SPEECH_MODELS_DIR and docker-compose.speech.yml."
goto :failed

:missing_node
set "C3A_STARTUP_ERROR=Node.js was not found on PATH. Install Node.js and reopen this window."
goto :failed

:missing_npm
set "C3A_STARTUP_ERROR=npm was not found on PATH. Install Node.js and reopen this window."
goto :failed

:broken_node
set "C3A_STARTUP_ERROR=Node.js was found but could not run."
goto :failed

:broken_npm
set "C3A_STARTUP_ERROR=npm was found but could not run."
goto :failed

:missing_python
set "C3A_STARTUP_ERROR=Python was not found. Create c3a-core\.venv or install Python 3."
goto :failed

:missing_api_pip
set "C3A_STARTUP_ERROR=pip is unavailable for the API Python environment."
goto :failed

:missing_ai_pip
set "C3A_STARTUP_ERROR=pip is unavailable for the AI Python environment."
goto :failed

:missing_ollama
set "C3A_STARTUP_ERROR=Ollama was not found. Install Ollama and reopen this window."
goto :failed

:ollama_start_failed
set "C3A_STARTUP_ERROR=Ollama server did not become ready within 30 seconds."
goto :failed

:ollama_pull_failed
set "C3A_STARTUP_ERROR=Failed to pull Ollama model %OLLAMA_MODEL%."
goto :failed

:api_requirements_failed
set "C3A_STARTUP_ERROR=Failed to install API Python requirements."
goto :failed

:ai_requirements_failed
set "C3A_STARTUP_ERROR=Failed to install AI Python requirements."
goto :failed

:ui_requirements_failed
set "C3A_STARTUP_ERROR=Failed to install or validate UI dependencies."
goto :failed

:failed
echo.
if not defined C3A_STARTUP_ERROR set "C3A_STARTUP_ERROR=An unknown startup error occurred."
echo ERROR: %C3A_STARTUP_ERROR%
where powershell >nul 2>&1
if not errorlevel 1 (
    powershell -NoProfile -ExecutionPolicy Bypass -Command "Add-Type -AssemblyName PresentationFramework; [void][System.Windows.MessageBox]::Show($env:C3A_STARTUP_ERROR, 'C3A Startup Warning', 'OK', 'Warning')" >nul 2>&1
)
pause
exit /b 1
