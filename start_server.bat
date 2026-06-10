@echo off
echo ========================================
echo   EvoCoder WebSocket Server
echo ========================================
echo.

cd /d "%~dp0"

REM Check if websockets is installed
python -c "import websockets" 2>nul
if errorlevel 1 (
    echo Installing websockets...
    pip install websockets
)

echo Starting server on ws://127.0.0.1:8765
echo Press Ctrl+C to stop
echo.
python web_server.py --host 127.0.0.1 --port 8765
pause
