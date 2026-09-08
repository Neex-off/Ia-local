#!/usr/bin/env bash
# Ia-local (Jarvis) — Copyright (c) 2026 Neexx (Nixovel) — voir LICENSE
# Lance Jarvis en fond (Mac / Linux) : pas de fenêtre, icône près de l'horloge si disponible, journal dans jarvis.log
cd "$(dirname "$0")"
if [ ! -x .venv/bin/python ]; then echo "Environnement absent : lance d'abord ./install.sh"; exit 1; fi
nohup nice -n 5 .venv/bin/python jarvis_server.py --no-browser "$@" >> jarvis.log 2>&1 &
echo "Jarvis démarre en fond (pid $!). Dis « Bonjour Jarvis », ou ouvre http://127.0.0.1:8765"
