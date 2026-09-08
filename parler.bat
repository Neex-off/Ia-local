@echo off
rem Ia-local (Jarvis) - Copyright (c) 2026 Neexx (Nixovel) - voir LICENSE
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"
.venv\Scripts\python.exe agent_vocal.py %*
pause
