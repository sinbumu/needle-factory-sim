@echo off
setlocal
cd /d "%~dp0"

echo === Needle Factory Sim ===

where uv >nul 2>nul
if errorlevel 1 (
    echo [ERROR] 'uv' was not found on PATH.
    echo Install it first, e.g.:
    echo     python -m pip install uv
    echo or see https://docs.astral.sh/uv/getting-started/installation/
    pause
    exit /b 1
)

echo Syncing dependencies (first run may take a few minutes)...
uv sync
if errorlevel 1 (
    echo [ERROR] uv sync failed. Check that Python 3.11+ is installed and
    echo that you have internet access for the first dependency download.
    pause
    exit /b 1
)

echo Starting Needle Factory Sim...
echo (First launch downloads the local Needle engine + model; needs internet once.)
uv run python -m needle_factory_sim
if errorlevel 1 (
    echo [ERROR] The application exited with an error. See the output above.
    pause
    exit /b 1
)
endlocal
