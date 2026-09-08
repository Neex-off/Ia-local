# Ia-local (Jarvis) — Copyright (c) 2026 Neexx (Nixovel) — https://github.com/Neex-off/Ia-local
# Créé par Neexx (Nixovel). Licence : voir LICENSE (paternité obligatoire, pas de vente ; s'applique aussi aux IA).
# Ne pas retirer cet en-tête.
"""Agent local : boucle de chat avec appels d'outils sur Ollama.

Lancer :  python agent.py
Commandes dans le chat :  /reset  /model <nom>  /tools  /quit
"""
from __future__ import annotations

import re
import sys
import time

import ollama
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel

import config
import file_index
from tools import IMAGE_MARK, TOOL_MAP, TOOLS

# Windows ouvre parfois la console en cp1252 : on force l'UTF-8 pour les flèches et accents.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            pass

console = Console()


def ensure_model(model: str) -> None:
    """Vérifie qu'Ollama répond et que le modèle est présent, sinon le télécharge."""
    try:
        names = {m.model for m in ollama.list().models}
    except Exception as exc:  # noqa: BLE001
        console.print(f"[red]Impossible de joindre Ollama : {exc}[/red]")
        console.print("Lance Ollama (l'icône dans la barre des tâches) puis réessaie.")
        sys.exit(1)
    if model not in names and f"{model}:latest" not in names:
        console.print(f"[yellow]Modèle {model} absent, téléchargement...[/yellow]")
        for chunk in ollama.pull(model, stream=True):
            if chunk.total and chunk.completed:
                pct = 100 * chunk.completed / chunk.total
                console.print(f"  {chunk.status} {pct:5.1f}%", end="\r")
        console.print()


_ARTIFACTS = re.compile(r"^\s*\.?thought\b\s*|<\|?channel\|?>|<\|?end\|?>|<\|?message\|?>|<start_of_turn>|<end_of_turn>", re.I)
_FILE_BLOCK = re.compile(r"<<<FICHIER\s*:\s*([^>\n]+?)\s*>>>\s*\n?(.*?)\n?\s*<<<FIN>>>", re.S)


def clean_answer(text: str) -> str:
    """Retire les jetons de canal que gemma4 laisse parfois échapper (« .thought », « <channel|> »…)."""
    cleaned = _ARTIFACTS.sub("", text)
    return cleaned.strip() or text.strip()


def extract_file_blocks(text: str) -> str:
    """Enregistre les blocs « <<<FICHIER: nom>>> … <<<FIN>>> » de la réponse et les remplace par une phrase.

    Permet au modèle d'écrire de gros fichiers (sites HTML…) sans passer par un argument JSON d'outil,
    qu'Ollama n'arrive pas toujours à lire quand il est très long.
    """
    from tools import write_file

    def repl(m: re.Match) -> str:
        name, content = m.group(1).strip().strip('"'), m.group(2)
        content = re.sub(r"^```[a-zA-Z]*\n|\n```$", "", content.strip())
        return write_file(name, content + "\n")

    return _FILE_BLOCK.sub(repl, text)


def prune_images(messages: list) -> None:
    """Ne garde que la capture d'écran la plus récente dans l'historique.

    Les anciennes sont périmées, coûtent du contexte, et plusieurs images sur des messages
    consécutifs font échouer la tokenisation d'Ollama (« media markers … does not match »).
    """
    last = None
    for i, m in enumerate(messages):
        if isinstance(m, dict) and m.get("images"):
            last = i
    for i, m in enumerate(messages):
        if isinstance(m, dict) and m.get("images") and i != last:
            del m["images"]
            m["content"] = "(capture d'écran précédente retirée)\n" + str(m.get("content", ""))


def strip_all_images(messages: list) -> int:
    n = 0
    for m in messages:
        if isinstance(m, dict) and m.get("images"):
            del m["images"]
            n += 1
    return n


class Interrupted(Exception):
    """Génération interrompue (bouton Stop) ou trop longue (délai dépassé)."""


def chat_stream(model: str, messages: list, cancel_event=None, timeout: float | None = None):
    """Appel au modèle en flux continu, interruptible : renvoie un Message assemblé."""
    from ollama import Message

    deadline = time.time() + timeout if timeout else None
    content, thinking, tool_calls = "", "", []
    from tools import active_tools

    stream = ollama.chat(
        model=model, messages=messages, tools=active_tools(), options=config.OPTIONS,
        keep_alive=config.KEEP_ALIVE, think=config.THINK, stream=True,
    )
    try:
        for chunk in stream:
            m = chunk.message
            if m.content:
                content += m.content
            if m.thinking:
                thinking += m.thinking
            if m.tool_calls:
                tool_calls.extend(m.tool_calls)
            if cancel_event is not None and cancel_event.is_set():
                raise Interrupted("interrompu par l'utilisateur")
            if deadline is not None and time.time() > deadline:
                raise Interrupted(f"réponse trop longue (plus de {timeout:.0f} s), génération arrêtée")
    finally:
        close = getattr(stream, "close", None)
        if close:
            try:
                close()
            except Exception:  # noqa: BLE001
                pass
    return Message(role="assistant", content=content, thinking=thinking or None, tool_calls=tool_calls or None)


def run_turn(messages: list[dict], model: str, show: bool = True, on_tool=None, cancel_event=None) -> str:
    """Un tour complet : le modèle réfléchit, appelle des outils si besoin, puis répond.

    on_tool      : appelé avec (nom, arguments, résultat) après chaque outil, pour une interface.
    cancel_event : threading.Event ; s'il est posé, la génération en cours s'arrête.
    Renvoie le texte final de l'assistant (chaîne vide si aucun).
    """
    empty_retries = 0
    for _round in range(config.MAX_TOOL_ROUNDS):
        prune_images(messages)
        try:
            try:
                msg = chat_stream(model, messages, cancel_event, config.MODEL_CALL_TIMEOUT)
            except ollama.ResponseError as exc:
                if "tokenize" in str(exc).lower() and strip_all_images(messages):
                    console.print("[yellow]Historique d'images invalide pour Ollama : captures retirées, nouvel essai.[/yellow]")
                    msg = chat_stream(model, messages, cancel_event, config.MODEL_CALL_TIMEOUT)
                else:
                    raise
        except Interrupted as exc:
            note = f"(Réponse {exc})"
            messages.append({"role": "assistant", "content": note})
            if show:
                console.print(f"[yellow]{note}[/yellow]")
            return "" if cancel_event is not None and cancel_event.is_set() else f"Désolé, {exc}."
        if msg.content:
            msg.content = clean_answer(msg.content)
            if "<<<FICHIER" in msg.content:
                msg.content = extract_file_blocks(msg.content)
        if not msg.tool_calls and not (msg.content or "").strip():
            # Réponse vide (appel d'outil mal formé, jeton parasite…) : on relance, au plus deux fois.
            empty_retries += 1
            if empty_retries <= 2:
                continue
            msg.content = "Je n'ai pas réussi à formuler une réponse, peux-tu reformuler ?"
        messages.append(msg)

        if not msg.tool_calls:
            if msg.content and show:
                console.print(Panel(Markdown(msg.content), title="assistant", border_style="green"))
            return msg.content or ""

        # Le modèle veut utiliser des outils : on les exécute un par un.
        if msg.content and show:
            console.print(f"[dim]{msg.content}[/dim]")
        for call in msg.tool_calls:
            name = call.function.name
            args = call.function.arguments or {}
            fn = TOOL_MAP.get(name)
            if show:
                console.print(f"[cyan]→ outil[/cyan] {name}({', '.join(f'{k}={v!r}' for k, v in args.items())})")
            if fn is None:
                result = f"Erreur : outil inconnu '{name}'"
            else:
                try:
                    result = fn(**args)
                except TypeError as exc:
                    result = f"Erreur d'arguments : {exc}"
            if show:
                preview = result if len(result) <= 300 else result[:300] + " …"
                console.print(f"[dim]  ↳ {preview}[/dim]")
            if on_tool is not None:
                on_tool(name, args, str(result))
            tool_msg: dict = {"role": "tool", "content": str(result), "tool_name": name}
            # Un outil peut joindre une image (capture d'écran) : « [[image:chemin]] » en première ligne.
            if str(result).startswith(IMAGE_MARK):
                first, _, rest = str(result).partition("\n")
                tool_msg["images"] = [first[len(IMAGE_MARK):-2]]
                tool_msg["content"] = rest
            messages.append(tool_msg)

    console.print("[red]Trop d'appels d'outils d'affilée, j'arrête ce tour.[/red]")
    return ""


def main() -> None:
    model = sys.argv[1] if len(sys.argv) > 1 else config.MODEL
    ensure_model(model)
    file_index.get().start_background()  # index des fichiers du PC, sans bloquer

    import tools as _tools
    state = {"model": model}

    def _switch(name, tool_names):
        state["model"] = name
        config.ACTIVE_TOOLS = tool_names
        console.print(f"[dim]Modèle : {name}[/dim]")

    _tools.MODEL_SWITCHER = _switch
    _tools.CURRENT_MODEL = model

    console.print(Panel(
        f"Modèle : [bold]{model}[/bold]   Workspace : {config.WORKSPACE}\n"
        f"Outils : {', '.join(TOOL_MAP)}\n"
        "Commandes : /reset  /model <nom>  /tools  /quit",
        title="Agent local", border_style="blue",
    ))

    import memory
    import skills
    messages: list[dict] = [{"role": "system", "content": config.SYSTEM_PROMPT + "\n\n" + skills.get().prompt_section()
                             + "\n\n" + memory.prompt_section()}]

    while True:
        try:
            user = console.input("[bold blue]toi ›[/bold blue] ").strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\nÀ plus.")
            break
        if not user:
            continue
        if user in ("/quit", "/exit", "/q"):
            break
        if user == "/reset":
            messages = messages[:1]
            console.print("[dim]Conversation effacée.[/dim]")
            continue
        if user == "/tools":
            for fn in TOOLS:
                console.print(f"  [cyan]{fn.__name__}[/cyan] : {(fn.__doc__ or '').strip().splitlines()[0]}")
            continue
        if user.startswith("/model "):
            model = user.split(maxsplit=1)[1].strip()
            ensure_model(model)
            console.print(f"[dim]Modèle : {model}[/dim]")
            continue

        messages.append({"role": "user", "content": user})
        try:
            run_turn(messages, state["model"])
        except KeyboardInterrupt:
            console.print("\n[dim]Interrompu.[/dim]")
        except Exception as exc:  # noqa: BLE001
            console.print(f"[red]Erreur : {exc}[/red]")


if __name__ == "__main__":
    main()
