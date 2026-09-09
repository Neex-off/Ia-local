@echo off
rem Ia-local (Jarvis) - Copyright (c) 2026 Neexx (Nixovel) - voir LICENSE
rem Lance Jarvis en ADMINISTRATEUR : il peut alors piloter et fermer les applications elevees (Epic Games, Steam...).
rem Attention : ses commandes tournent aussi avec ces droits.
powershell -NoProfile -Command "Start-Process -FilePath '%~dp0jarvis.bat' -WorkingDirectory '%~dp0' -Verb RunAs"
