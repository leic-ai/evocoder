@echo off
cd /d "D:\ClaudeData\EvoCoder"
taskkill /F /IM pythonw.exe 2>nul
taskkill /F /IM python.exe 2>nul
timeout /t 1 /nobreak >nul
start "" pythonw desktop.py
