@echo off
title EVOcoder Desktop
echo.
echo  ========================================
echo   EVOcoder Desktop
echo  ========================================
echo.

cd /d "%~dp0"

REM Check if pywebview is installed
python -c "import webview" 2>nul
if errorlevel 1 (
    echo [!] Installing pywebview...
    pip install pywebview
    echo.
)

REM Check API key
if not exist ".env" (
    echo [ERROR] .env file not found with DEEPSEEK_API_KEY
    pause
    exit /b 1
)

echo Starting EVOcoder Desktop...
echo Close the window to exit.
echo.
python desktop.py
pause
