#!/usr/bin/env bash
# Ia-local (Jarvis) — Copyright (c) 2026 Neexx (Nixovel) — voir LICENSE
# Installation automatique sur macOS et Linux.
#   ./install.sh            installation complète (modèle standard)
#   ./install.sh --all      + modèles léger, recherche et puissant
#   ./install.sh --no-voice sans reconnaissance ni synthèse vocale (mode texte seulement)
set -e
cd "$(dirname "$0")"
ALL=0; VOICE=1
for a in "$@"; do case "$a" in --all) ALL=1;; --no-voice) VOICE=0;; esac; done
OS="$(uname -s)"
say() { printf "\n\033[1;36m==> %s\033[0m\n" "$*"; }

say "1/6 Python 3.11"
PY=""
for c in python3.11 python3.12 python3; do
  if command -v "$c" >/dev/null 2>&1; then
    v=$("$c" -c 'import sys;print((3,10)<=sys.version_info[:2]<=(3,12))'); [ "$v" = "True" ] && PY="$c" && break
  fi
done
if [ -z "$PY" ]; then
  if [ "$OS" = "Darwin" ]; then
    command -v brew >/dev/null || { echo "Installe Homebrew (https://brew.sh) puis relance."; exit 1; }
    brew install python@3.11; PY=python3.11
  elif command -v apt-get >/dev/null; then
    sudo apt-get update
    sudo apt-get install -y python3.11 python3.11-venv python3.11-dev 2>/dev/null || sudo apt-get install -y python3 python3-venv python3-dev
    PY=python3.11; command -v $PY >/dev/null || PY=python3
  elif command -v dnf >/dev/null; then sudo dnf install -y python3.11; PY=python3.11
  elif command -v pacman >/dev/null; then sudo pacman -S --noconfirm python; PY=python3
  else echo "Installe Python 3.11 puis relance."; exit 1; fi
fi
echo "Python : $($PY --version)"
if [ "$OS" = "Linux" ] && command -v apt-get >/dev/null; then sudo apt-get install -y portaudio19-dev libsndfile1 ffmpeg xdotool >/dev/null 2>&1 || true; fi
if [ "$OS" = "Darwin" ] && command -v brew >/dev/null; then brew list portaudio >/dev/null 2>&1 || brew install portaudio ffmpeg >/dev/null 2>&1 || true; fi

say "2/6 Environnement virtuel"
[ -d .venv ] || "$PY" -m venv .venv
.venv/bin/python -m pip install --upgrade pip wheel >/dev/null

say "3/6 Dépendances de base"
.venv/bin/python -m pip install -r requirements.txt

if [ "$VOICE" = "1" ]; then
  say "4/6 PyTorch et dépendances vocales (plusieurs Go, patience)"
  if [ "$OS" = "Linux" ] && command -v nvidia-smi >/dev/null 2>&1; then
    .venv/bin/python -m pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu128
  else
    .venv/bin/python -m pip install torch torchaudio
  fi
  .venv/bin/python -m pip install --no-deps chatterbox-tts
  .venv/bin/python -m pip install -r requirements-voice.txt
  if [ "$OS" = "Linux" ] && command -v nvidia-smi >/dev/null 2>&1; then .venv/bin/python -m pip install nvidia-cublas-cu12 nvidia-cudnn-cu12; fi
else
  say "4/6 Mode texte : dépendances vocales ignorées (--no-voice)"
fi

say "5/6 Ollama et modèle"
if ! command -v ollama >/dev/null 2>&1; then
  if [ "$OS" = "Darwin" ]; then brew install ollama || { echo "Télécharge Ollama : https://ollama.com/download"; exit 1; }
  else curl -fsSL https://ollama.com/install.sh | sh; fi
fi
(ollama serve >/dev/null 2>&1 &) ; sleep 3
ollama pull gemma4:12b
if [ "$ALL" = "1" ]; then ollama pull gemma4:e4b-it-qat; ollama pull granite4.1:8b; ollama pull gemma4:26b-a4b-it-qat; fi

say "6/6 Terminé"
chmod +x jarvis.sh jarvis-console.sh jarvis-arreter.sh 2>/dev/null || true
mkdir -p workspace
cat <<EOM

Installation terminée.
  Interface Jarvis (fond)   : ./jarvis.sh          puis dis « Bonjour Jarvis »
  Interface Jarvis (console): ./jarvis-console.sh
  Mode texte                : .venv/bin/python agent.py
  Arrêter                   : ./jarvis-arreter.sh
Les modèles de voix (Whisper, Chatterbox, ~4 Go) se téléchargent au premier lancement.
EOM
