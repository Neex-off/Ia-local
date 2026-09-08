@echo off
rem Ia-local (Jarvis) - Copyright (c) 2026 Neexx (Nixovel) - voir LICENSE
rem Lance Jarvis en fond : pas de fenetre, priorite basse, icone pres de l'horloge, journal dans jarvis.log
cd /d "%~dp0"
start "" /BELOWNORMAL "%~dp0.venv\Scripts\pythonw.exe" "%~dp0jarvis_server.py" --no-browser %*
