@echo off
rem Ia-local (Jarvis) - Copyright (c) 2026 Neexx (Nixovel) - voir LICENSE
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"
echo Jarvis en mode console (messages visibles). Dis "Bonjour Jarvis" pour ouvrir la page.
.venv\Scripts\python.exe jarvis_server.py --no-browser %*
pause
