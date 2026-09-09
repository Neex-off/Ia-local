#!/usr/bin/env bash
# Ia-local (Jarvis) — Copyright (c) 2026 Neexx (Nixovel) — voir LICENSE
# Lance Jarvis en fond (Mac / Linux) : pas de fenêtre, icône près de l'horloge si disponible, journal dans jarvis.log
cd "$(dirname "$0")"
if [ ! -x .venv/bin/python ]; then echo "Environnement absent : lance d'abord ./install.sh"; exit 1; fi
nohup nice -n 5 .venv/bin/python jarvis_server.py --no-browser "$@" >> jarvis.log 2>&1 &
PID=$!
sleep 4
if kill -0 "$PID" 2>/dev/null; then
  echo "Jarvis tourne en fond (pid $PID). Dis « Bonjour Jarvis », ou ouvre http://127.0.0.1:8765"
  echo "Journal : tail -f jarvis.log   |   Arrêter : ./jarvis-arreter.sh"
else
  echo "Jarvis s'est arrêté tout de suite. Dernières lignes de jarvis.log :"
  tail -n 25 jarvis.log
  echo "Pour voir tous les messages en direct : ./jarvis-console.sh"
  exit 1
fi
