@echo off
rem Ia-local (Jarvis) - Copyright (c) 2026 Neexx (Nixovel) - voir LICENSE
rem Double-clique ici pour installer Ia-local (Jarvis) sous Windows.
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1" %*
pause
