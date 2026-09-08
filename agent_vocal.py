# Ia-local (Jarvis) — Copyright (c) 2026 Neexx (Nixovel) — https://github.com/Neex-off/Ia-local
# Créé par Neexx (Nixovel). Licence : voir LICENSE (paternité obligatoire, pas de vente ; s'applique aussi aux IA).
# Ne pas retirer cet en-tête.
"""Jarvis en mode terminal (sans interface graphique). Pour l'interface façon Iron Man : jarvis.bat.

Lancer :  parler.bat   (ou .venv\\Scripts\\python agent_vocal.py)
- Dis « Bonjour Jarvis » pour le réveiller, « Merci Jarvis » pour le rendormir.
- Tu peux aussi taper une phrase puis Entrée. « q » quitte.
"""
from __future__ import annotations

import sys
import threading

from rich.console import Console
from rich.panel import Panel

import config
from jarvis_core import JarvisCore

console = Console()

_ICONS = {"idle": "💤", "listening": "🎤", "thinking": "🧠", "tool": "🔧", "speaking": "🔊", "loading": "⏳"}


def show(ev: dict) -> None:
    kind = ev["type"]
    if kind == "loading":
        console.print(f"[dim]⏳ {ev['step']}[/dim]")
    elif kind == "state":
        if ev["state"] in ("idle", "listening"):
            console.print(f"[dim]{_ICONS[ev['state']]} {'à l’écoute' if ev['awake'] else 'en veille'}[/dim]", end="\r")
    elif kind == "heard":
        if ev["for_me"]:
            console.print(f"[green]🔔 Réveillé par « {ev['text']} »[/green]")
        else:
            console.print(f"[dim]  (entendu : « {ev['text']} », pas pour moi)[/dim]")
    elif kind == "user":
        console.print(f"[bold blue]toi ›[/bold blue] {ev['text']}")
    elif kind == "tool":
        console.print(f"[cyan]🔧 {ev['name']}[/cyan] {ev['args']}")
    elif kind == "assistant":
        console.print(f"[bold green]{config.ASSISTANT_NAME} ›[/bold green] {ev['text']}  [dim]({ev['seconds']}s)[/dim]")
    elif kind == "error":
        console.print(f"[red]Erreur : {ev['text']}[/red]")


def main() -> None:
    core = JarvisCore(emit=show, model=sys.argv[1] if len(sys.argv) > 1 else None)
    console.print(Panel(
        f"Modèle : [bold]{core.model}[/bold]   Nom : [bold]{config.ASSISTANT_NAME}[/bold]\n"
        f"Dis « Bonjour {config.ASSISTANT_NAME} » pour le réveiller, « Merci {config.ASSISTANT_NAME} » pour le rendormir.\n"
        "Tape une phrase + Entrée pour lui écrire, « q » pour quitter.",
        title="Agent vocal", border_style="magenta",
    ))
    core.load()
    threading.Thread(target=core.run, daemon=True).start()
    while True:
        try:
            line = console.input("").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if line == "q":
            break
        if line == "r":
            core.reset()
            console.print("[dim]Conversation effacée.[/dim]")
        elif line:
            core.submit_text(line)
    core.stop_speaking()
    console.print("À plus.")


if __name__ == "__main__":
    main()
