#!/usr/bin/env bash
# Ia-local (Jarvis) — Copyright (c) 2026 Neexx (Nixovel) — voir LICENSE
# Lance Jarvis dans le terminal (messages visibles)
cd "$(dirname "$0")"
if [ ! -x .venv/bin/python ]; then echo "Environnement absent : lance d'abord ./install.sh"; exit 1; fi
echo "Jarvis en mode console. Dis « Bonjour Jarvis » pour ouvrir la page."
exec .venv/bin/python jarvis_server.py --no-browser "$@"
