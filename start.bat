@echo off
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1
cd /d D:\ClaudeData\EvoCoder
python cli.py
pause
