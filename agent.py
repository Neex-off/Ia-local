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


def model_tier(model: str) -> str | None:
    """Nom du profil du catalogue (léger, recherche, standard, puissant) pour un modèle, ou None."""
    return next((t for t in config.MODEL_ORDER if config.MODELS[t]["name"] == model), None)


def has_gpu() -> bool:
    """Carte NVIDIA utilisable (nvidia-smi répond) ou Mac Apple Silicon. Sinon : processeur seul."""
    import platform
    import shutil
    import subprocess

    if sys.platform == "darwin" and platform.machine() == "arm64":
        return True
    if shutil.which("nvidia-smi"):
        try:
            return subprocess.run(["nvidia-smi", "-L"], capture_output=True, timeout=5,
                                  creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).returncode == 0
        except Exception:  # noqa: BLE001
            return False
    return False


def cpu_only_choice(model: str, names: set[str]) -> str | None:
    """Sans carte graphique, un gros modèle met des minutes à répondre : renvoie le plus petit modèle du
    catalogue déjà installé (mini, puis léger) si `model` est plus lourd, sinon None."""
    tier = model_tier(model)
    if tier is None or config.MODEL_ORDER.index(tier) <= 1:
        return None  # déjà mini ou léger
    for t in config.MODEL_ORDER[:2]:
        cand = config.MODELS[t]["name"]
        if cand in names or f"{cand}:latest" in names:
            return cand
    return None


class OllamaUnavailable(RuntimeError):
    """Ollama ne répond pas (pas lancé, ou encore en train de démarrer avec Windows)."""


def wait_for_ollama(seconds: float = 90, on_wait=None) -> set[str]:
    """Attend qu'Ollama réponde (au démarrage du PC il met parfois 10 à 30 s), en essayant de le lancer
    s'il ne tourne pas. Renvoie les noms des modèles installés. Lève OllamaUnavailable sinon."""
    import subprocess
    import time as _time

    deadline = _time.time() + seconds
    launched = False
    last = ""
    while True:
        try:
            return {m.model for m in ollama.list().models}
        except Exception as exc:  # noqa: BLE001
            last = str(exc)
        if not launched:
            launched = True
            try:  # « ollama serve » : sans effet s'il tourne déjà, le lance sinon (Windows, Mac, Linux)
                subprocess.Popen(["ollama", "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                 creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            except Exception:  # noqa: BLE001
                pass
        if _time.time() > deadline:
            raise OllamaUnavailable(f"Impossible de joindre Ollama après {seconds:.0f} s : {last}. "
                                    "Lance Ollama (icône près de l'horloge, ou « ollama serve ») puis relance Jarvis.")
        if on_wait is not None:
            on_wait(int(deadline - _time.time()))
        console.print("[yellow]Ollama ne répond pas encore, nouvel essai…[/yellow]")
        _time.sleep(2)


def ensure_model(model: str, fallback: bool = True) -> str:
    """Vérifie qu'Ollama répond et renvoie le modèle à utiliser.

    Si `model` est présent : lui. Sinon, avec fallback, le premier modèle du catalogue déjà installé
    (le léger d'abord) pour pouvoir tester tout de suite pendant qu'un autre se télécharge.
    Sinon, télécharge `model`.
    """
    names = wait_for_ollama()

    def present(m: str) -> bool:
        return m in names or f"{m}:latest" in names

    if present(model):
        if fallback and config.CPU_AUTO_SMALL and not has_gpu():
            small = cpu_only_choice(model, names)
            if small:
                console.print(f"[yellow]Pas de carte graphique : {model} serait très lent, démarrage avec {small} "
                              f"(profil {model_tier(small)}). Pour forcer {model} : /model {model}, ou MODEL dans config.py "
                              f"et CPU_AUTO_SMALL = False.[/yellow]")
                return small
        return model
    if fallback:
        for tier in config.MODEL_ORDER:
            cand = config.MODELS[tier]["name"]
            if present(cand):
                console.print(f"[yellow]Modèle {model} pas encore installé : démarrage avec {cand} (profil {tier}). "
                              f"Pour l'avoir : ollama pull {model}[/yellow]")
                return cand
    console.print(f"[yellow]Modèle {model} absent, téléchargement...[/yellow]")
    for chunk in ollama.pull(model, stream=True):
        if chunk.total and chunk.completed:
            pct = 100 * chunk.completed / chunk.total
            console.print(f"  {chunk.status} {pct:5.1f}%", end="\r")
    console.print()
    return model


_ARTIFACTS = re.compile(r"^\s*\.?thought\b\s*|<\|?channel\|?>|<\|?end\|?>|<\|?message\|?>|<start_of_turn>|<end_of_turn>", re.I)
_FILE_BLOCK = re.compile(r"<<<FICHIER\s*:\s*([^>\n]+?)\s*>>>\s*\n?(.*?)\n?\s*(?:<<<FIN>>>|\Z)", re.S)


def clean_answer(text: str) -> str:
    """Retire les jetons de canal que gemma4 laisse parfois échapper (« .thought », « <channel|> »…)."""
    cleaned = _ARTIFACTS.sub("", text)
    return cleaned.strip()  # vide si le modèle n'a émis que des jetons de canal : run_turn relance alors


def extract_file_blocks(text: str) -> str:
    """Enregistre les blocs « <<<FICHIER: nom>>> … <<<FIN>>> » de la réponse et les remplace par une phrase.

    Permet au modèle d'écrire de gros fichiers (sites HTML…) sans passer par un argument JSON d'outil,
    qu'Ollama n'arrive pas toujours à lire quand il est très long.
    """
    from tools import write_file

    def repl(m: re.Match) -> str:
        name, content = m.group(1).strip().strip('"'), m.group(2)
        content = re.sub(r"^```[a-zA-Z]*\n|\n```$", "", content.strip())
        note = ""
        if content.lower().count("<html") and "</html>" not in content.lower():
            note = " (attention : le fichier semble incomplet, la génération a été coupée ; demande-moi de le terminer)"
        return write_file(name, content + "\n") + note

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


class RunawayThinking(Exception):
    """Le modèle réfléchit dans le vide au lieu de répondre (jetons de canal, pensée cachée sans fin)."""


NUDGE = {"role": "user", "content": "(Réponds maintenant directement, en une ou deux phrases, sans réfléchir à voix haute.)"}


def chat_stream(model: str, messages: list, cancel_event=None, timeout: float | None = None, on_content=None):
    """Appel au modèle en flux continu, interruptible : renvoie un Message assemblé.
    on_content(texte_cumulé) est appelé à chaque morceau reçu (pour parler dès la première phrase)."""
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
                if on_content is not None:
                    try:
                        on_content(content)
                    except Exception:  # noqa: BLE001
                        pass
            if m.thinking:
                thinking += m.thinking
            if m.tool_calls:
                tool_calls.extend(m.tool_calls)
            if not config.THINK and not tool_calls and (len(thinking) > 1200 or
                                                        (len(content) > 300 and not _ARTIFACTS.sub("", content).strip())):
                # gemma4 part parfois dans une « réflexion » cachée interminable malgré think=False (surtout après un
                # outil) : on coupe tout de suite au lieu d'attendre 80 s, run_turn relance avec une consigne.
                raise RunawayThinking()
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


def run_turn(messages: list[dict], model: str, show: bool = True, on_tool=None, cancel_event=None,
             on_tool_start=None, on_content=None) -> str:
    """Un tour complet : le modèle réfléchit, appelle des outils si besoin, puis répond.

    on_tool       : appelé avec (nom, arguments, résultat) après chaque outil, pour une interface.
    on_tool_start : appelé avec (nom, arguments, texte_du_modèle) AVANT d'exécuter un outil (pour annoncer à voix haute).
    cancel_event  : threading.Event ; s'il est posé, la génération en cours s'arrête.
    Renvoie le texte final de l'assistant (chaîne vide si aucun).
    """
    empty_retries = 0
    for _round in range(config.MAX_TOOL_ROUNDS):
        prune_images(messages)
        try:
            try:
                try:
                    msg = chat_stream(model, messages, cancel_event, config.MODEL_CALL_TIMEOUT, on_content)
                except RunawayThinking:
                    console.print("[yellow]Réflexion parasite du modèle : je relance avec une consigne directe.[/yellow]")
                    messages.append(NUDGE)
                    try:
                        msg = chat_stream(model, messages, cancel_event, config.MODEL_CALL_TIMEOUT, on_content)
                    except RunawayThinking:
                        from ollama import Message
                        msg = Message(role="assistant", content="")  # traité comme une réponse vide : nouvel essai ci-dessous
                    finally:
                        messages.remove(NUDGE)
            except ollama.ResponseError as exc:
                if "tokenize" in str(exc).lower() and strip_all_images(messages):
                    console.print("[yellow]Historique d'images invalide pour Ollama : captures retirées, nouvel essai.[/yellow]")
                    msg = chat_stream(model, messages, cancel_event, config.MODEL_CALL_TIMEOUT, on_content)
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
            if on_tool_start is not None:
                try:
                    on_tool_start(name, args, (msg.content or "").strip())
                except Exception:  # noqa: BLE001
                    pass
            if show:
                console.print(f"[cyan]→ outil[/cyan] {name}({', '.join(f'{k}={v!r}' for k, v in args.items())})")
            if fn is None:
                result = f"Erreur : outil inconnu '{name}'"
            else:
                import time as _time

                import noyau

                refus = noyau.before_call(name, args)  # permissions, arrêt d'urgence, commandes interdites
                if refus is not None:
                    result = refus
                else:
                    t_outil = _time.time()
                    try:
                        result = fn(**args)
                    except TypeError as exc:
                        result = f"Erreur d'arguments : {exc}"
                    except Exception as exc:  # noqa: BLE001
                        result = f"Erreur dans l'outil {name} : {exc}"
                    noyau.after_call(name, args, str(result), _time.time() - t_outil)  # journal d'audit
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
    try:
        model = ensure_model(model)
    except OllamaUnavailable as exc:
        console.print(f"[red]{exc}[/red]")
        sys.exit(1)
    file_index.get().start_background()  # index des fichiers du PC, sans bloquer

    import tools as _tools
    _tools.CURRENT_MODEL = model
    if (tier := model_tier(model)) is not None:
        config.ACTIVE_TOOLS = config.MODELS[tier].get("tools")
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
                             + "\n\n" + memory.prompt_section() + "\n\n" + memory.knowledge_prompt_section()}]

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
            model = ensure_model(model, fallback=False)
            console.print(f"[dim]Modèle : {model}[/dim]")
            continue

        import agenda
        messages.append({"role": "user", "content": f"{user}\n\n[Aujourd'hui : {agenda.today_line()}]"})
        try:
            run_turn(messages, state["model"])
        except KeyboardInterrupt:
            console.print("\n[dim]Interrompu.[/dim]")
        except Exception as exc:  # noqa: BLE001
            console.print(f"[red]Erreur : {exc}[/red]")


if __name__ == "__main__":
    main()
