@echo off
rem Ia-local (Jarvis) - Copyright (c) 2026 Neexx (Nixovel) - voir LICENSE
rem Arrete Jarvis (le serveur en fond)
powershell -NoProfile -Command "$c = Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue; if ($c) { Stop-Process -Id $c.OwningProcess -Force; 'Jarvis arrete.' } else { 'Jarvis ne tournait pas.' }"
pause
