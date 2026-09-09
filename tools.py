# Ia-local (Jarvis) — Copyright (c) 2026 Neexx (Nixovel) — https://github.com/Neex-off/Ia-local
# Créé par Neexx (Nixovel). Licence : voir LICENSE (paternité obligatoire, pas de vente ; s'applique aussi aux IA).
# Ne pas retirer cet en-tête.
"""Outils mis à disposition du modèle.

Chaque fonction publique de ce module est exposée au modèle : sa docstring
sert de description et ses annotations de types servent de schéma.
Toutes renvoient une chaîne de caractères (le modèle ne lit que du texte).
"""
from __future__ import annotations

import ast
import math
import operator
import os
import re
import socket
import subprocess
import sys
import time
import unicodedata
import webbrowser
from datetime import datetime
from pathlib import Path

import requests

import config
import file_index
from config import AUTO_APPROVE_COMMANDS, COMMAND_TIMEOUT, WORKSPACE

MAX_OUTPUT = 8000  # caractères renvoyés au modèle, au-delà on tronque
# Sous-processus sans fenêtre console (Jarvis tourne sans console via pythonw).
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
IS_WINDOWS = sys.platform.startswith("win")
IS_MAC = sys.platform == "darwin"
HOME = Path.home()


def _open_with_system(target: str) -> None:
    """Ouvre un fichier, un dossier ou une URL avec l'application par défaut du système."""
    if IS_WINDOWS:
        os.startfile(target)  # noqa: S606
    elif IS_MAC:
        subprocess.Popen(["open", target])
    else:
        subprocess.Popen(["xdg-open", target], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

# --------------------------------------------------------------------------
# Helpers internes (préfixe _ : non exposés au modèle)
# --------------------------------------------------------------------------


def _truncate(text: str, limit: int = MAX_OUTPUT) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n... [tronqué, {len(text) - limit} caractères de plus]"


def _safe_path(path: str) -> Path:
    """Résout un chemin : absolu tel quel (si FULL_DISK_ACCESS), relatif dans le workspace."""
    path = path.strip().strip('"').strip("'")
    path = os.path.expandvars(os.path.expanduser(path))
    root = WORKSPACE.resolve()
    target = (Path(path) if os.path.isabs(path) else root / path).resolve()
    if not config.FULL_DISK_ACCESS and target != root and root not in target.parents:
        raise PermissionError(f"Accès refusé : {path} est en dehors de {WORKSPACE}")
    return target


def _online(host: str = "1.1.1.1", port: int = 53, timeout: float = 1.5) -> bool:
    try:
        socket.create_connection((host, port), timeout=timeout).close()
        return True
    except OSError:
        return False


OFFLINE_MSG = "Erreur : pas de connexion internet. Cet outil est indisponible hors ligne."

# --------------------------------------------------------------------------
# Outils exposés au modèle
# --------------------------------------------------------------------------


def get_datetime() -> str:
    """Renvoie la date et l'heure locales actuelles."""
    return datetime.now().strftime("%A %d %B %Y, %H:%M:%S")


_ALLOWED_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}
_ALLOWED_NAMES = {k: getattr(math, k) for k in dir(math) if not k.startswith("_")}
_ALLOWED_NAMES.update({"abs": abs, "round": round, "min": min, "max": max})


def calculate(expression: str) -> str:
    """Évalue une expression mathématique de façon sûre, par exemple "2**10 + sqrt(16)" ou "sin(pi/2)".

    Args:
        expression: L'expression à calculer, en syntaxe Python (fonctions du module math disponibles).
    """

    def _eval(node):
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return node.value
        if isinstance(node, ast.BinOp) and type(node.op) in _ALLOWED_OPS:
            return _ALLOWED_OPS[type(node.op)](_eval(node.left), _eval(node.right))
        if isinstance(node, ast.UnaryOp) and type(node.op) in _ALLOWED_OPS:
            return _ALLOWED_OPS[type(node.op)](_eval(node.operand))
        if isinstance(node, ast.Name) and node.id in _ALLOWED_NAMES:
            return _ALLOWED_NAMES[node.id]
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in _ALLOWED_NAMES
        ):
            return _ALLOWED_NAMES[node.func.id](*[_eval(a) for a in node.args])
        raise ValueError(f"Élément non autorisé : {ast.dump(node)}")

    try:
        tree = ast.parse(expression, mode="eval")
        return str(_eval(tree.body))
    except Exception as exc:  # noqa: BLE001
        return f"Erreur de calcul : {exc}"


def _fmt_size(n: int) -> str:
    for unit in ("o", "Ko", "Mo", "Go"):
        if n < 1024:
            return f"{n:.0f} {unit}"
        n /= 1024
    return f"{n:.1f} To"


def search_files(query: str, folder: str = "", extension: str = "", max_results: int = 15) -> str:
    """Recherche instantanée d'un fichier ou dossier par son nom sur tout le PC (index de tous les disques).

    Args:
        query: Un ou plusieurs mots du nom du fichier, par exemple "facture edf" ou "cv 2025".
        folder: Optionnel : ne garder que les résultats dont le chemin contient ce texte, par exemple "Documents" ou "D:\\Jeux".
        extension: Optionnel : extension sans point, par exemple "pdf", "jpg", "docx".
        max_results: Nombre maximum de résultats (1 à 50).
    """
    idx = file_index.get()
    try:
        hits = idx.search(query, folder=folder, ext=extension, limit=max(1, min(int(max_results), 50)))
    except Exception as exc:  # noqa: BLE001
        return f"Erreur de recherche : {exc}"
    if hits and "error" in hits[0]:
        return f"Erreur : {hits[0]['error']} ({idx.status()})"
    if not hits:
        return f"Aucun résultat pour « {query} ». ({idx.status()})"
    lines = []
    for h in hits:
        kind = "dossier" if h["is_dir"] else _fmt_size(h["size"])
        date = datetime.fromtimestamp(h["mtime"]).strftime("%d/%m/%Y")
        lines.append(f"{h['path']}  ({kind}, {date})")
    note = f"\n({idx.status()})" if idx.building else ""
    return "\n".join(lines) + note


def open_file(path: str) -> str:
    """Ouvre un fichier ou un dossier avec l'application par défaut de Windows (PDF, image, vidéo, dossier dans l'Explorateur…).

    Args:
        path: Chemin complet du fichier ou dossier, par exemple "~/Documents/cv.pdf".
    """
    try:
        target = _safe_path(path)
        if not target.exists():
            return f"Introuvable : {path}"
        _open_with_system(str(target))
        return f"Ouvert : {target}"
    except Exception as exc:  # noqa: BLE001
        return f"Erreur : {exc}"


def list_files(directory: str = ".") -> str:
    """Liste le contenu d'un dossier (chemin absolu Windows, ou relatif au dossier de travail).

    Args:
        directory: Par exemple "~/Downloads" ou un chemin complet. "." pour le dossier de travail.
    """
    try:
        base = _safe_path(directory)
        if not base.exists():
            return f"Le dossier {directory} n'existe pas."
        entries = []
        for p in sorted(base.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower())):
            try:
                kind = "dossier" if p.is_dir() else _fmt_size(p.stat().st_size)
            except OSError:
                kind = "?"
            entries.append(f"{p.name}  ({kind})")
        if len(entries) > 200:
            entries = entries[:200] + [f"… et {len(entries) - 200} autres"]
        return f"{base}\n" + ("\n".join(entries) or "(dossier vide)")
    except Exception as exc:  # noqa: BLE001
        return f"Erreur : {exc}"


def read_file(path: str) -> str:
    """Lit le contenu d'un fichier texte (txt, md, py, json, csv…) n'importe où sur le PC.

    Args:
        path: Chemin complet, par exemple "~/Documents/notes.txt" (ou relatif au dossier de travail).
    """
    try:
        target = _safe_path(path)
        if not target.is_file():
            return f"Le fichier {path} n'existe pas."
        return _truncate(target.read_text(encoding="utf-8", errors="replace"))
    except Exception as exc:  # noqa: BLE001
        return f"Erreur : {exc}"


def write_file(path: str, content: str) -> str:
    """Écrit un fichier texte. Sans chemin complet, il va dans le dossier de travail.

    Args:
        path: Chemin complet ou relatif au dossier de travail, par exemple "rapport.md".
        content: Le contenu complet à écrire.
    """
    try:
        target = _safe_path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return f"Fichier écrit : {target} ({len(content)} caractères)"
    except Exception as exc:  # noqa: BLE001
        return f"Erreur : {exc}"


def run_command(command: str) -> str:
    """Exécute une commande shell dans le dossier de travail (PowerShell sous Windows, bash sur Mac et Linux) et renvoie sa sortie.

    Args:
        command: La commande à exécuter, par exemple "python script.py" ou "ls".
    """
    if not AUTO_APPROVE_COMMANDS:
        print(f"\n\033[33m[commande demandée]\033[0m {command}")
        answer = input("\033[33mAutoriser ? (o/N) \033[0m").strip().lower()
        if answer not in ("o", "oui", "y", "yes"):
            return "L'utilisateur a refusé l'exécution de cette commande."
    shell = (["powershell", "-NoProfile", "-NonInteractive", "-Command", command] if IS_WINDOWS
             else ["bash", "-lc", command])
    try:
        proc = subprocess.run(
            shell,
            cwd=WORKSPACE,
            capture_output=True,
            text=True,
            timeout=COMMAND_TIMEOUT,
            encoding="utf-8",
            errors="replace",
            creationflags=NO_WINDOW,
        )
        out = proc.stdout.strip()
        err = proc.stderr.strip()
        result = f"Code de sortie : {proc.returncode}"
        if out:
            result += f"\n--- stdout ---\n{out}"
        if err:
            result += f"\n--- stderr ---\n{err}"
        return _truncate(result)
    except subprocess.TimeoutExpired:
        return f"Erreur : la commande a dépassé {COMMAND_TIMEOUT} s et a été interrompue."
    except Exception as exc:  # noqa: BLE001
        return f"Erreur : {exc}"


def web_search(query: str, max_results: int = 5) -> str:
    """Recherche sur le web (DuckDuckGo) et renvoie titres, liens et extraits. Nécessite internet.

    Args:
        query: Les mots-clés de la recherche.
        max_results: Nombre de résultats à renvoyer (1 à 10).
    """
    if not _online():
        return OFFLINE_MSG
    try:
        from ddgs import DDGS

        results = DDGS().text(query, max_results=max(1, min(int(max_results), 10)))
        if not results:
            return "Aucun résultat."
        lines = []
        for i, r in enumerate(results, 1):
            lines.append(f"{i}. {r.get('title', '')}\n   {r.get('href', '')}\n   {r.get('body', '')}")
        return "\n\n".join(lines)
    except Exception as exc:  # noqa: BLE001
        return f"Erreur de recherche : {exc}"


def fetch_url(url: str) -> str:
    """Télécharge une page web et renvoie son texte lisible (sans HTML). Nécessite internet.

    Args:
        url: L'adresse complète de la page, avec http:// ou https://.
    """
    if not _online():
        return OFFLINE_MSG
    try:
        from bs4 import BeautifulSoup

        resp = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0 (agent local)"})
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header", "noscript"]):
            tag.decompose()
        text = "\n".join(line.strip() for line in soup.get_text("\n").splitlines() if line.strip())
        return _truncate(text)
    except Exception as exc:  # noqa: BLE001
        return f"Erreur de téléchargement : {exc}"


def _start_menu_dirs() -> list[Path]:
    dirs = []
    for env, sub in (("ProgramData", "Microsoft/Windows/Start Menu/Programs"),
                     ("APPDATA", "Microsoft/Windows/Start Menu/Programs")):
        base = os.environ.get(env)
        if base and (Path(base) / sub).is_dir():
            dirs.append(Path(base) / sub)
    desktop = Path.home() / "Desktop"
    if desktop.is_dir():
        dirs.append(desktop)
    return dirs


def _norm_app(s: str) -> str:
    s = unicodedata.normalize("NFKD", s.lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def find_app(name: str) -> Path | None:
    """Cherche un raccourci (.lnk/.url) du menu Démarrer ou du bureau dont le nom ressemble à `name`."""
    want = _norm_app(name)
    want_words = set(want.split())
    best: tuple[float, Path] | None = None
    for d in _start_menu_dirs():
        for p in d.rglob("*"):
            if p.suffix.lower() not in (".lnk", ".url", ".exe"):
                continue
            stem = _norm_app(p.stem)
            if not stem:
                continue
            if stem == want:
                score = 3.0
            elif want in stem or stem in want:
                score = 2.0 + min(len(want), len(stem)) / max(len(want), len(stem))
            else:
                common = want_words & set(stem.split())
                if not common:
                    continue
                score = len(common) / max(len(want_words), 1)
            # On évite les désinstalleurs et l'aide
            if any(bad in stem for bad in ("uninstall", "desinstaller", "readme", "help")):
                score -= 1
            if best is None or score > best[0]:
                best = (score, p)
    return best[1] if best and best[0] >= 0.5 else None


_start_apps_cache: tuple[float, list[tuple[str, str]]] = (0.0, [])


def _start_apps() -> list[tuple[str, str]]:
    """Applications installées : [(nom, identifiant de lancement)]. Cache 10 min.

    Windows : menu Démarrer (y compris Microsoft Store) ; macOS : dossiers Applications ;
    Linux : fichiers .desktop.
    """
    global _start_apps_cache
    ts, apps = _start_apps_cache
    if apps and time.time() - ts < 600:
        return apps
    try:
        if IS_WINDOWS:
            out = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command",
                 "Get-StartApps | ForEach-Object { $_.Name + '|' + $_.AppID }"],
                capture_output=True, text=True, timeout=20, encoding="utf-8", errors="replace", creationflags=NO_WINDOW,
            ).stdout
            apps = [tuple(line.split("|", 1)) for line in out.splitlines() if "|" in line]
        elif IS_MAC:
            apps = []
            for d in (Path("/Applications"), Path("/System/Applications"), HOME / "Applications"):
                if d.is_dir():
                    apps += [(p.stem, str(p)) for p in d.glob("*.app")]
        else:
            apps = []
            for d in (Path("/usr/share/applications"), Path("/usr/local/share/applications"),
                      HOME / ".local/share/applications", Path("/var/lib/flatpak/exports/share/applications")):
                if not d.is_dir():
                    continue
                for p in d.glob("*.desktop"):
                    try:
                        text = p.read_text(encoding="utf-8", errors="replace")
                    except OSError:
                        continue
                    if "NoDisplay=true" in text:
                        continue
                    m = re.search(r"^Name=(.+)$", text, re.M)
                    if m:
                        apps.append((m.group(1).strip(), str(p)))
        _start_apps_cache = (time.time(), apps)
    except Exception:  # noqa: BLE001
        pass
    return apps


def _launch_app(app_id: str) -> None:
    if IS_WINDOWS:
        subprocess.Popen(["explorer.exe", f"shell:AppsFolder\\{app_id}"], creationflags=NO_WINDOW)
    elif IS_MAC:
        subprocess.Popen(["open", "-a", app_id])
    else:
        subprocess.Popen(["gio", "launch", app_id], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def find_start_app(name: str) -> tuple[str, str] | None:
    want = _norm_app(name)
    want_words = set(want.split())
    best: tuple[float, tuple[str, str]] | None = None
    for app_name, app_id in _start_apps():
        n = _norm_app(app_name)
        if not n:
            continue
        if n == want:
            score = 3.0
        elif want in n or n in want:
            score = 2.0 + min(len(want), len(n)) / max(len(want), len(n))
        else:
            common = want_words & set(n.split())
            if not common:
                continue
            score = len(common) / max(len(want_words), 1)
        if any(bad in n for bad in ("uninstall", "desinstaller", "readme", "help")):
            score -= 1
        if best is None or score > best[0]:
            best = (score, (app_name, app_id))
    return best[1] if best and best[0] >= 0.5 else None


def open_app(name: str) -> str:
    """Ouvre un logiciel, un jeu ou une application par son nom (ex : "Spotify", "Steam", "Discord", "Chrome", "Calculatrice").

    Args:
        name: Le nom du logiciel tel qu'il apparaît dans le menu des applications.
    """
    # 1. Applications installées (menu Démarrer / dossiers Applications / fichiers .desktop)
    hit = find_start_app(name)
    if hit is not None:
        app_name, app_id = hit
        try:
            _launch_app(app_id)
            time.sleep(4)  # laisse l'application s'ouvrir avant un see_screen
            return f"Lancé : {app_name} (4 s d'attente ; si see_screen montre une autre fenêtre, focus_window('{app_name}') puis see_screen)"
        except Exception as exc:  # noqa: BLE001
            return f"Erreur au lancement de {app_name} : {exc}"
    # 2. Raccourcis (.lnk) du menu Démarrer et du bureau (Windows)
    target = find_app(name) if IS_WINDOWS else None
    if target is None:
        return f"Je n'ai trouvé aucun logiciel ressemblant à « {name} » sur cet ordinateur."
    try:
        _open_with_system(str(target))
        return f"Lancé : {target.stem}"
    except Exception as exc:  # noqa: BLE001
        return f"Erreur au lancement de {target.name} : {exc}"


def _resolve_app(name: str) -> tuple[str, str]:
    """(type, cible) : ("url", adresse) / ("app", nom d'appli installée) / ("", "") si inconnu."""
    key = _norm_app(name)
    for alias, target in config.APP_ALIASES.items():
        a = _norm_app(alias)
        if key == a or key.startswith(a + " ") or key.endswith(" " + a):
            return ("url", target) if target.startswith("http") else ("app", target)
    if re.match(r"^(https?://|www\.)", name.strip()):
        return ("url", name.strip() if name.startswith("http") else "https://" + name.strip())
    hit = find_start_app(name)
    if hit is not None:
        return ("app", hit[0])
    return ("", "")


def _window_matching(name: str) -> str | None:
    """Titre d'une fenêtre ouverte correspondant au nom (pour remettre devant au lieu de relancer)."""
    try:
        import computer

        want = _norm_app(name)
        for t in computer.list_windows():
            if want and want in _norm_app(t):
                return t
    except Exception:  # noqa: BLE001
        pass
    return None


def list_apps(query: str = "") -> str:
    """Cherche une application installée ou un site connu par un mot-clé (ex : "discord", "photos", "mail") et renvoie les noms utilisables avec check_app / open_app.

    Args:
        query: Un mot du nom de l'application. Vide = les raccourcis connus.
    """
    key = _norm_app(query)
    aliases = [f"{a} -> {t}" for a, t in config.APP_ALIASES.items() if not key or key in _norm_app(a) or key in _norm_app(t)]
    apps = [n for n, _id in _start_apps() if not key or key in _norm_app(n)]
    out = []
    if aliases:
        out.append("Raccourcis : " + "; ".join(aliases[:15]))
    if apps:
        out.append(f"Applications installées ({len(apps)}) : " + ", ".join(sorted(apps)[:40]))
    return "\n".join(out) or f"Rien ne ressemble à « {query} »."


def check_app(name: str) -> str:
    """Va voir une application ou un site (Discord, WhatsApp, Steam, YouTube, mails, agenda…) : l'ouvre ou la remet au premier plan, attend qu'elle s'affiche, et te renvoie l'écran avec la liste de ses éléments pour que tu lises ce qu'il y a (messages, notifications, contenu). À utiliser dès que l'utilisateur veut savoir ce qu'il se passe dans une appli.

    Args:
        name: Le nom de l'application ou du site, tel que dit par l'utilisateur.
    """
    kind, target = _resolve_app(name)
    if not kind:
        return f"Je ne connais pas « {name} ». {list_apps(name)}"
    try:
        import computer

        already = _window_matching(target if kind == "app" else name)
        if already:
            computer.focus_window(already)
            time.sleep(1.5)
            how = f"fenêtre « {already} » remise au premier plan"
            note = computer.window_elevated_note(already)
            if note:
                how += f". ATTENTION : {note} Je peux la regarder mais pas cliquer dedans"
        elif kind == "url":
            webbrowser.open(target)
            time.sleep(4)
            for title in ("Chrome", "Edge", "Firefox", "Opera", "Brave"):
                if _window_matching(title):
                    computer.focus_window(title)
                    break
            how = f"site ouvert : {target}"
        else:
            hit = find_start_app(target)
            if hit is None:
                return f"Application « {target} » introuvable. {list_apps(target)}"
            _launch_app(hit[1])
            time.sleep(5)
            w = _window_matching(hit[0])
            if w:
                computer.focus_window(w)
                time.sleep(1)
            how = f"application lancée : {hit[0]}"
        path, text = computer.describe_screen(0)
        return f"{IMAGE_MARK}{path}]]\n{how}.\n{text}\nDécris à l'utilisateur ce que tu vois d'utile (nouveaux messages, notifications, contenu à l'écran) ; si ce n'est pas la bonne fenêtre, focus_window puis see_screen."
    except Exception as exc:  # noqa: BLE001
        return f"Erreur en allant voir {name} : {exc}"


def _close_app_unix(name: str, app: str, force: bool) -> str:
    """Fermeture d'une application sous macOS (osascript) ou Linux (wmctrl / pkill), avec vérification."""
    import subprocess as sp

    app = Path(app).stem if app.endswith(".app") or "/" in app else app

    def alive() -> bool:
        return sp.run(["pgrep", "-if", app], capture_output=True).returncode == 0

    if not alive():
        return f"Aucun processus « {app} » en cours : l'application n'est pas lancée (ou porte un autre nom ; list_windows() pour voir)."
    if force:
        sp.run(["pkill", "-9", "-if", app], capture_output=True)
        time.sleep(1)
        return f"Processus arrêté de force : {app}." if not alive() else f"Impossible d'arrêter {app} (droits insuffisants ?)."
    if IS_MAC:
        sp.run(["osascript", "-e", f'tell application "{app}" to quit'], capture_output=True, timeout=15)
    else:
        if sp.run(["which", "wmctrl"], capture_output=True).returncode == 0:
            sp.run(["wmctrl", "-c", app], capture_output=True)
        else:
            sp.run(["pkill", "-if", app], capture_output=True)  # SIGTERM = fermeture propre
    time.sleep(2.5)
    if alive():
        return f"J'ai demandé à {app} de se fermer mais il tourne encore (une boîte de dialogue « Enregistrer ? » peut bloquer : see_screen). Dis « force » pour l'arrêter."
    return f"Fermé : {app} (processus terminé)."


def close_app(name: str, force: bool = False) -> str:
    """Ferme une application par son nom : envoie la commande de fermeture à ses fenêtres (comme la croix) puis VÉRIFIE qu'elles ont disparu. Si l'appli reste en arrière-plan (Spotify, Epic Games, Discord se réduisent près de l'horloge), le dit ; force=True arrête alors complètement le processus.

    Args:
        name: Le nom de l'application, tel que dit par l'utilisateur.
        force: True pour tuer le processus si la fermeture normale ne suffit pas (à faire seulement si l'utilisateur le demande ou l'a déjà dit).
    """
    try:
        import subprocess as sp

        import computer

        kind, target = _resolve_app(name)
        if not IS_WINDOWS:
            return _close_app_unix(name, target if kind == "app" else name, force)
        titles_to_try = [name] + ([target] if kind == "app" and target != name else [])
        for t in titles_to_try:
            note = computer.window_elevated_note(t)
            if note:
                return f"Impossible : {note}"
        closed, pids = [], []
        for t in titles_to_try:
            c, p = computer.close_window(t)
            closed += c
            pids += p
        pids = sorted(set(pids))
        if not closed and not pids:
            return f"Aucune fenêtre ouverte pour « {name} » : l'application n'est pas à l'écran (peut-être déjà fermée, ou seulement en arrière-plan). {list_windows()}"
        time.sleep(2.5)
        still = [w.window_text() for t in titles_to_try for w in computer.windows_matching(t)]
        if still:
            # 2e essai : la fenêtre devant, puis Alt+F4 (exactement comme la croix)
            import pyautogui

            for t in still:
                computer.focus_window(t)
                time.sleep(0.6)
                # Sécurité : Alt+F4 seulement si c'est bien CETTE fenêtre qui est devant (sinon on fermerait autre chose)
                if _norm_app(t) in _norm_app(computer.foreground_title()):
                    pyautogui.hotkey("alt", "f4")
                    time.sleep(2.5)
            still = [w.window_text() for t in titles_to_try for w in computer.windows_matching(t)]
        if still:
            # 3e essai : clic sur la croix dessinée par l'application, en haut à droite de sa fenêtre
            import pyautogui

            for t in titles_to_try:
                for w in computer.windows_matching(t):
                    try:
                        computer.focus_window(w.window_text())
                        time.sleep(0.5)
                        if _norm_app(w.window_text()) not in _norm_app(computer.foreground_title()):
                            continue
                        r = w.rectangle()
                        pyautogui.moveTo(r.right - 22, r.top + 18, duration=0.2)
                        pyautogui.click()
                        time.sleep(2.5)
                    except Exception:  # noqa: BLE001
                        continue
            still = [w.window_text() for t in titles_to_try for w in computer.windows_matching(t)]
        alive = []
        for pid in pids:
            out = sp.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"], capture_output=True, text=True, creationflags=NO_WINDOW).stdout
            if str(pid) in out:
                alive.append(pid)
        if still:
            if not force:
                return f"J'ai envoyé la fermeture à {', '.join(closed)}, mais une fenêtre est encore ouverte : {', '.join(still)} (une boîte de dialogue « Enregistrer ? » peut bloquer : see_screen). Dis « force » pour arrêter le processus."
        if alive and force:
            for pid in alive:
                sp.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True, creationflags=NO_WINDOW)
            time.sleep(1)
            return f"Processus arrêté de force : {', '.join(closed)} (pid {', '.join(map(str, alive))})."
        if alive:
            return f"Fenêtre fermée : {', '.join(closed)}. L'application tourne encore en arrière-plan (icône près de l'horloge) ; si tu veux l'arrêter complètement, dis-le et j'utiliserai force=True."
        return f"Fermé : {', '.join(closed)} (fenêtre disparue, processus terminé)."
    except Exception as exc:  # noqa: BLE001
        return f"Erreur en fermant {name} : {exc}"


def open_site(name: str) -> str:
    """Ouvre un site web à partir de son NOM (ex : "mon intranet", "leboncoin", "Netflix") : cherche l'adresse réelle sur le web et ouvre le premier résultat. À utiliser quand tu ne connais pas l'URL exacte, au lieu de la deviner.

    Args:
        name: Le nom du site ou du service tel que l'utilisateur l'a dit.
    """
    if not _online():
        return OFFLINE_MSG
    try:
        from ddgs import DDGS

        results = DDGS().text(f"{name} site officiel", max_results=5) or DDGS().text(name, max_results=5)
        if not results:
            return f"Aucun site trouvé pour « {name} »."
        skip = ("wikipedia.", "youtube.com/watch", "facebook.com", "linkedin.com/posts", "x.com", "twitter.com")
        pick = next((r for r in results if not any(s in r.get("href", "") for s in skip)), results[0])
        url = pick.get("href", "")
        webbrowser.open(url)
        time.sleep(3.5)
        others = "; ".join(f"{r.get('title', '')[:40]} ({r.get('href', '')})" for r in results[:3] if r is not pick)
        return f"Ouvert : {pick.get('title', '')} -> {url}\nAutres résultats : {others}"
    except Exception as exc:  # noqa: BLE001
        return f"Erreur : {exc}"


def open_url(url: str) -> str:
    """Ouvre une adresse web EXACTE dans le navigateur (uniquement si tu es sûr de l'URL, sinon utilise open_site).

    Args:
        url: L'adresse complète, par exemple "https://www.youtube.com".
    """
    if not re.match(r"^https?://", url):
        url = "https://" + url
    try:
        webbrowser.open(url)
        time.sleep(3.5)  # laisse le navigateur passer au premier plan et charger avant un see_screen
        return f"Ouvert dans le navigateur : {url} (la page a eu 3 s pour charger ; si see_screen montre une autre fenêtre, focus_window sur le navigateur puis see_screen)"
    except Exception as exc:  # noqa: BLE001
        return f"Erreur : {exc}"


# --------------------------------------------------------------------------
# Mémoire
# --------------------------------------------------------------------------


def remember(fact: str, category: str = "autre") -> str:
    """Enregistre dans ta mémoire durable un fait sur l'utilisateur (prénom, ville, goûts, projets, habitudes, personnes…). À utiliser dès qu'il te dit quelque chose sur lui ou te demande de retenir.

    Args:
        fact: Le fait, en une phrase claire, par exemple "L'utilisateur fait de la musculation 4 fois par semaine".
        category: "identité", "préférence", "projet", "habitude", "personne" ou "autre".
    """
    import memory

    f = memory.remember(fact, category)
    return f"Mémorisé (n°{f['id']}, {f['categorie']}) : {f['texte']}"


def recall(query: str = "") -> str:
    """Cherche dans ta mémoire durable et dans les anciennes conversations. Vide = tout ce que tu sais de l'utilisateur.

    Args:
        query: Mots-clés, par exemple "muscu", "projet flutter", "anniversaire".
    """
    import memory

    facts = memory.search(query, limit=15) if query.strip() else memory.all_facts()
    lines = [f"Faits mémorisés ({len(facts)}) :"] + [f"  n°{f['id']} [{f['categorie']}] {f['texte']} ({f['date'][:10]})" for f in facts]
    know = memory.knowledge_search(query, limit=5) if query.strip() else memory.all_knowledge()[-10:]
    if know:
        lines.append(f"Connaissances apprises ({len(know)}) :")
        lines += [f"  n°{k['id']} {k['sujet']} ({k['date'][:10]}) : {k['resume'][:400]}" + (f" [sources : {k['sources'][:120]}]" if k['sources'] else "") for k in know]
    if query.strip():
        convs = memory.search_conversations(query, limit=6)
        if convs:
            lines.append("Extraits d'anciennes conversations :")
            lines += [f"  {m['date'][:16]} {m['role']} : {m['text'][:160]}" for m in convs]
    return "\n".join(lines) if len(lines) > 1 else "Je n'ai encore rien mémorisé à ce sujet."


def research(topic: str, max_pages: int = 3) -> str:
    """Se renseigner sur un sujet : cherche sur le web, lit les meilleures pages et te renvoie la matière à résumer. À utiliser pour apprendre quelque chose de nouveau, puis enregistre l'essentiel avec learn. Nécessite internet.

    Args:
        topic: Le sujet ou la question, par exemple "règles du padel" ou "nouveautés Flutter 4".
        max_pages: Nombre de pages à lire (1 à 5).
    """
    if not _online():
        return OFFLINE_MSG
    try:
        from bs4 import BeautifulSoup
        from ddgs import DDGS

        results = DDGS().text(topic, max_results=8) or []
        if not results:
            return f"Aucun résultat web pour « {topic} »."
        out = [f"Recherche « {topic} » : {len(results)} résultats.", ""]
        read = 0
        for r in results:
            url = r.get("href", "")
            if read >= max(1, min(int(max_pages), 5)):
                break
            if not url.startswith("http") or url.lower().endswith((".pdf", ".zip")) or "youtube.com" in url:
                continue
            try:
                resp = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0 (agent local)"})
                resp.raise_for_status()
                soup = BeautifulSoup(resp.text, "html.parser")
                for tag in soup(["script", "style", "nav", "footer", "header", "noscript", "aside"]):
                    tag.decompose()
                text = "\n".join(line.strip() for line in soup.get_text("\n").splitlines() if len(line.strip()) > 40)
                if len(text) < 300:
                    continue
                out.append(f"=== Source {read + 1} : {r.get('title', '')} — {url}\n{text[:2500]}\n")
                read += 1
            except Exception:  # noqa: BLE001
                continue
        if read == 0:
            out.append("Pages illisibles ; extraits des résultats :")
            out += [f"- {r.get('title', '')} : {r.get('body', '')} ({r.get('href', '')})" for r in results[:5]]
        out.append("Maintenant : résume en 3 à 8 phrases ce que tu as appris, puis enregistre-le avec learn(sujet, résumé, sources).")
        return _truncate("\n".join(out), 9000)
    except Exception as exc:  # noqa: BLE001
        return f"Erreur de recherche : {exc}"


def learn(topic: str, summary: str, sources: str = "") -> str:
    """Enregistre durablement une connaissance apprise (après research, ou donnée par l'utilisateur) dans ton carnet de connaissances.

    Args:
        topic: Le sujet, court, par exemple "Règles du padel".
        summary: Ce que tu as compris, en 3 à 8 phrases claires et factuelles.
        sources: Les adresses des pages utilisées, séparées par des espaces (facultatif).
    """
    import memory

    it = memory.learn(topic, summary, sources)
    return f"Appris et mémorisé (n°{it['id']}) : {it['sujet']}. Tu pourras le retrouver avec recall."


def forget(fact_id: int) -> str:
    """Efface un fait de ta mémoire durable (à la demande de l'utilisateur), par son numéro donné par recall.

    Args:
        fact_id: Le numéro du fait à oublier.
    """
    import memory

    return f"Fait n°{fact_id} oublié." if memory.forget(int(fact_id)) else f"Aucun fait n°{fact_id}."


# --------------------------------------------------------------------------
# Vue projets (interface)
# --------------------------------------------------------------------------

# Défini par le serveur : fonction(event: dict) qui envoie un événement à l'interface web.
UI_EMIT = None


def show_projects(source: str = "tous") -> str:
    """Affiche les projets de l'utilisateur à l'écran (nom, type, branche git, branches, dossiers liés, dépôts GitHub) et te renvoie la liste. À appeler quand il dit « montre-moi les projets » ou « mes projets GitHub ».

    Args:
        source: "tous" (PC + GitHub), "local" (seulement le PC) ou "github" (seulement les dépôts GitHub).
    """
    import projets

    src = (source or "tous").strip().lower()
    projects = projets.scan(include_github=src in ("tous", "github"), include_local=src in ("tous", "local"))
    if UI_EMIT is not None:
        UI_EMIT({"type": "view", "view": "projects", "projects": projects})
    return projets.summary(projects) + ("\n(Affichés à l'écran.)" if UI_EMIT else "")


def hide_projects() -> str:
    """Referme la vue projets et remet l'interface normale (« ferme les projets », « retour »)."""
    if UI_EMIT is not None:
        UI_EMIT({"type": "view", "view": "home"})
    return "Vue projets fermée."


# --------------------------------------------------------------------------
# Agenda
# --------------------------------------------------------------------------


def _agenda_refresh() -> None:
    if UI_EMIT is not None:
        import agenda

        UI_EMIT({"type": "agenda", **agenda.view_payload()})


def show_agenda() -> str:
    """Affiche l'agenda à l'écran (calendrier du mois avec les rendez-vous, et les prochains rendez-vous) et te renvoie les 14 prochains jours. À appeler pour « montre l'agenda », « ouvre le calendrier »."""
    import agenda

    global _AGENDA_OPEN
    from datetime import date

    if UI_EMIT is not None:
        UI_EMIT({"type": "view", "view": "agenda", **agenda.view_payload()})
    _AGENDA_OPEN = True
    _AGENDA_SHOWN[:] = [date.today().year, date.today().month]
    ups = agenda.upcoming(14)
    body = "\n".join(agenda.fmt(e) for e in ups) if ups else "Rien de prévu dans les 14 prochains jours."
    return f"Aujourd'hui : {agenda.today_line()}.\n{body}\n(Agenda affiché à l'écran.)"


def agenda_month(month: str = "", year: int = 0) -> str:
    """Change le mois affiché dans l'agenda à l'écran et te renvoie les rendez-vous de ce mois. month : « suivant », « précédent », un nom (« octobre ») ou un numéro 1-12 ; year facultatif. À appeler pour « mois suivant », « montre octobre », « reviens à ce mois-ci » (month="actuel")."""
    import calendar
    from datetime import date

    import agenda

    cur = _AGENDA_SHOWN or [date.today().year, date.today().month]
    y, m = cur
    q = agenda._norm(str(month))
    if q in ("suivant", "prochain", "apres", "next", "+1"):
        m += 1
    elif q in ("precedent", "avant", "dernier", "prev", "-1"):
        m -= 1
    elif q in ("", "actuel", "courant", "ce mois", "ce mois-ci", "aujourd'hui", "aujourdhui"):
        y, m = date.today().year, date.today().month
    elif q.isdigit():
        m = int(q)
    else:
        names = [agenda._norm(n) for n in agenda.MOIS]
        hits = [i for i, n in enumerate(names) if n.startswith(q[:3])]
        if not hits:
            return f"Mois non compris : {month!r} (attendu « suivant », « précédent », un nom de mois ou 1-12)."
        m = hits[0] + 1
        if not year and (y, m) < (date.today().year, date.today().month):
            y += 1  # un mois déjà passé cette année -> l'an prochain
    if year:
        y = int(year)
    while m > 12:
        m -= 12
        y += 1
    while m < 1:
        m += 12
        y -= 1
    _AGENDA_SHOWN[:] = [y, m]
    if UI_EMIT is not None:
        if not _AGENDA_OPEN:
            UI_EMIT({"type": "view", "view": "agenda", **agenda.view_payload()})
        UI_EMIT({"type": "agenda_goto", "year": y, "month": m - 1})
    start = date(y, m, 1)
    evs = agenda.between(start, date(y, m, calendar.monthrange(y, m)[1]))
    body = "\n".join(agenda.fmt(e) for e in evs) if evs else "Rien de prévu ce mois-là."
    return f"Agenda affiché sur {agenda.MOIS[m - 1]} {y}.\n{body}"


_AGENDA_SHOWN: list[int] = []  # [année, mois] affichés dans l'interface
_AGENDA_OPEN = False


def hide_agenda() -> str:
    """Referme l'agenda et remet l'interface normale (« ferme l'agenda », « retour »)."""
    global _AGENDA_OPEN
    if UI_EMIT is not None:
        UI_EMIT({"type": "view", "view": "home"})
    _AGENDA_OPEN = False
    _AGENDA_SHOWN.clear()
    return "Agenda fermé."


def add_event(title: str, date: str, time: str = "", note: str = "") -> str:
    """Ajoute un rendez-vous ou un rappel dans l'agenda. Calcule d'abord la date exacte à partir d'aujourd'hui (donné dans le message) : « jeudi » = le prochain jeudi, « demain » = aujourd'hui + 1.

    Args:
        title: L'intitulé, par exemple "Dentiste" ou "Appeler Marc".
        date: La date au format AAAA-MM-JJ (ou JJ/MM/AAAA).
        time: L'heure au format HH:MM (vide si toute la journée).
        note: Détail facultatif (lieu, personne…).
    """
    import agenda

    try:
        ev = agenda.add(title, date, time, note)
    except ValueError as exc:
        return f"Erreur : {exc}"
    _agenda_refresh()
    return f"Ajouté : {agenda.fmt(ev)}"


def remove_event(query: str) -> str:
    """Supprime un rendez-vous par son numéro, ou tous ceux dont le titre contient le texte donné.

    Args:
        query: Le numéro (ex. "3") ou un mot du titre (ex. "dentiste").
    """
    import agenda

    gone = agenda.remove(query)
    if not gone:
        return f"Aucun rendez-vous ne correspond à « {query} »."
    _agenda_refresh()
    return "Supprimé : " + " ; ".join(agenda.fmt(e) for e in gone)


def list_events(days: int = 7) -> str:
    """Liste les rendez-vous à venir (« qu'est-ce que j'ai cette semaine ? », « mon programme demain »).

    Args:
        days: Nombre de jours à partir d'aujourd'hui (1 = aujourd'hui seulement, 7 = la semaine, 30 = le mois).
    """
    import agenda
    from datetime import date as _date, timedelta

    today = _date.today()
    evs = agenda.between(today, today + timedelta(days=max(0, int(days) - 1)))
    head = f"Aujourd'hui : {agenda.today_line()}."
    return head + ("\n" + "\n".join(agenda.fmt(e) for e in evs) if evs else f"\nRien de prévu sur {days} jour(s).")


# --------------------------------------------------------------------------
# Modèles : bascule à chaud
# --------------------------------------------------------------------------

# Défini par jarvis_core / agent : fonction(nom_du_modele) qui applique le changement.
MODEL_SWITCHER = None
CURRENT_MODEL = config.MODEL


def _installed_models() -> set[str]:
    try:
        import ollama

        return {m.model for m in ollama.list().models}
    except Exception:  # noqa: BLE001
        return set()


def _model_tiers() -> list[tuple[int, str, dict]]:
    """[(numéro, tier, infos)] dans l'ordre du plus léger au plus lourd."""
    order = [t for t in config.MODEL_ORDER if t in config.MODELS] + [t for t in config.MODELS if t not in config.MODEL_ORDER]
    return [(i + 1, t, config.MODELS[t]) for i, t in enumerate(order)]


def list_models() -> str:
    """Liste les modèles de langage disponibles, numérotés (1, 2, 3…), avec leur poids par rapport au modèle actuel, ce que chacun apporte et ce qu'il ne permet plus. À lire à l'utilisateur quand il veut changer de modèle."""
    installed = _installed_models()
    tiers = _model_tiers()
    current_idx = next((i for i, _t, m in tiers if m["name"] == CURRENT_MODEL), None)
    lines = [f"Modèle actif : {CURRENT_MODEL}. Options (réponds avec le numéro) :"]
    for i, tier, m in tiers:
        ok = m["name"] in installed or f"{m['name']}:latest" in installed
        state = "installé" if ok else "PAS installé, téléchargement nécessaire"
        if current_idx is None:
            rel = ""
        elif i == current_idx:
            rel = "c'est le modèle actuel"
        elif i < current_idx:
            rel = "plus léger que l'actuel"
        else:
            rel = "plus lourd que l'actuel"
        lines.append(f"{i}. {tier} — {m['name']} — {m['vram']} — {rel} — {state}\n"
                     f"   apporte : {m['plus']}\n   limites : {m['moins']}")
    return "\n".join(lines)


_NUMBER_WORDS = {"1": 1, "un": 1, "une": 1, "premier": 1, "premiere": 1, "2": 2, "deux": 2, "deuxieme": 2, "second": 2,
                 "3": 3, "trois": 3, "troisieme": 3, "4": 4, "quatre": 4, "5": 5, "cinq": 5}


def switch_model(choice: str) -> str:
    """Bascule sur un autre modèle de langage d'après le choix de l'utilisateur : un nom (« léger », « recherche », « standard », « puissant »), un numéro (« 2 », « option 2 »), ou relatif (« plus léger », « plus puissant »). À appeler directement dès que l'utilisateur nomme le modèle. L'ancien est éteint, la conversation conservée.

    Args:
        choice: Le nom, le numéro, ou « plus léger » / « plus puissant ».
    """
    global CURRENT_MODEL
    key = _norm_app(choice)
    entry = None
    tiers = _model_tiers()
    cur = next((i for i, _t, m in tiers if m["name"] == CURRENT_MODEL), None)
    words = key.split()
    # 1. un nom de profil ou de modèle (« léger », « recherche », « le standard », « gemma4:12b »)
    for _i, t, m in tiers:
        if _norm_app(t) in words or key == _norm_app(m["name"]):
            entry = (t, m)
            break
    # 2. relatif : « plus léger » -> le profil léger ; « plus puissant » -> le profil juste au-dessus
    if entry is None and cur is not None:
        if any(w in words for w in ("leger", "petit", "rapide", "bas")) or "moins lourd" in key:
            entry = next(((t, m) for i, t, m in tiers if i == 1), None)
        elif any(w in words for w in ("puissant", "gros", "lourd", "fort", "haut", "intelligent", "gras")):
            entry = next(((t, m) for i, t, m in tiers if i == min(len(tiers), cur + 1)), None)
    # 3. un numéro seul (« 2 », « option 2 », « la deux », « numéro trois »)
    if entry is None:
        rest = [w for w in words if w not in ("option", "l", "la", "le", "numero", "n", "choix", "modele", "profil")]
        if len(rest) == 1 and rest[0] in _NUMBER_WORDS:
            n = _NUMBER_WORDS[rest[0]]
            entry = next(((t, m) for i, t, m in tiers if i == n), None)
    # 2. un nom de tier ou de modèle
    if entry is None:
        for _i, t, m in tiers:
            if key in (_norm_app(t), _norm_app(m["name"])) or _norm_app(t) in key:
                entry = (t, m)
                break
    if entry is None:
        if choice in _installed_models():
            entry = (choice, {"name": choice, "tools": None, "plus": "", "moins": ""})
        else:
            return f"Choix non reconnu : « {choice} ». Options : " + ", ".join(f"{i} = {t}" for i, t, _m in tiers) + "."
    t, m = entry
    if m["name"] not in _installed_models() and f"{m['name']}:latest" not in _installed_models():
        return f"Le modèle {m['name']} n'est pas installé. Il faut lancer « ollama pull {m['name']} » (environ {m.get('vram', '?')} à télécharger)."
    if m["name"] == CURRENT_MODEL:
        return f"Le modèle {t} ({m['name']}) est déjà actif."
    if MODEL_SWITCHER is None:
        return "Changement de modèle indisponible dans ce mode."
    try:
        MODEL_SWITCHER(m["name"], m.get("tools"))
    except Exception as exc:  # noqa: BLE001
        return f"Erreur au changement de modèle : {exc}"
    old = CURRENT_MODEL
    CURRENT_MODEL = m["name"]
    kept = "tous les outils" if not m.get("tools") else "seulement : " + ", ".join(m["tools"])
    return (f"Modèle basculé sur {t} ({m['name']}) ; {old} est éteint et la conversation est conservée. "
            f"Outils disponibles maintenant : {kept}. Le nouveau modèle répond à partir de la prochaine question.")


# --------------------------------------------------------------------------
# Compétences
# --------------------------------------------------------------------------


def list_skills(query: str = "") -> str:
    """Cherche des compétences (instructions d'expert) par mots-clés : design, site web, flutter, python, sécurité, marketing, django, docker… Renvoie les noms à passer à use_skill.

    Args:
        query: Un ou plusieurs mots-clés, en français ou en anglais (ex. "flutter", "site web", "sécurité api", "marketing"). Vide = les principales.
    """
    import skills

    reg = skills.get()
    hits = reg.search(query, limit=25) if query.strip() else [s for s in reg.skills.values() if s.category == "maison" or s.name in config.SKILLS_FEATURED]
    if not hits:
        return f"Aucune compétence pour « {query} » parmi les {len(reg.skills)}. Essaie un autre mot-clé (en anglais aussi : security, mobile, testing…)."
    lines = [f"{len(hits)} compétence(s) sur {len(reg.skills)} :"]
    for s in hits:
        lines.append(f"  - {s.name} [{s.category}] : {s.description[:150]}")
    return "\n".join(lines)


def use_skill(name: str) -> str:
    """Charge une compétence : renvoie ses instructions détaillées à suivre pour la tâche en cours. À appeler avant de commencer un site, un design, du code, un document…

    Args:
        name: Le nom de la compétence, par exemple "site-web", "impeccable", "python-patterns", "article-writing".
    """
    import skills

    reg = skills.get()
    s = reg.get(name)
    if s is None:
        return f"Compétence « {name} » introuvable. Compétences disponibles :\n{list_skills()}"
    limit = config.SKILL_MAX_CHARS_ACTIVE if hasattr(config, "SKILL_MAX_CHARS_ACTIVE") else config.SKILL_MAX_CHARS
    return f"=== Compétence « {s.name} » ({s.category}) ===\n{s.content(limit)}"


# --------------------------------------------------------------------------
# Documents : PDF, Word
# --------------------------------------------------------------------------

def _find_font() -> Path | None:
    """Une police TrueType Unicode du système (accents), selon l'OS."""
    candidates = [
        Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts" / "arial.ttf",
        Path("/Library/Fonts/Arial.ttf"), Path("/System/Library/Fonts/Supplemental/Arial.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"), Path("/usr/share/fonts/TTF/DejaVuSans.ttf"),
        Path("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"),
    ]
    return next((p for p in candidates if p.is_file()), None)


_FONT = _find_font() or Path("arial.ttf")


def create_pdf(path: str, title: str, content: str) -> str:
    """Crée un document PDF avec un titre et du texte (paragraphes séparés par des lignes vides, lignes commençant par "# " = sous-titres, "- " = puces).

    Args:
        path: Chemin du fichier à créer, par exemple "~/Documents/rapport.pdf" ou "rapport.pdf" (dossier de travail).
        title: Le titre affiché en haut du document.
        content: Le texte du document.
    """
    try:
        from fpdf import FPDF

        target = _safe_path(path if path.lower().endswith(".pdf") else path + ".pdf")
        target.parent.mkdir(parents=True, exist_ok=True)
        pdf = FPDF()
        pdf.set_auto_page_break(auto=True, margin=18)
        pdf.add_page()
        if _FONT.is_file():
            pdf.add_font("Body", "", str(_FONT))
            bold = next((_FONT.with_name(n) for n in ("arialbd.ttf", "Arial Bold.ttf", "DejaVuSans-Bold.ttf",
                                                       "LiberationSans-Bold.ttf") if _FONT.with_name(n).is_file()), _FONT)
            pdf.add_font("Body", "B", str(bold))
            font = "Body"
        else:
            font = "Helvetica"
        pdf.set_font(font, "B", 20)
        pdf.multi_cell(0, 10, title, new_x="LMARGIN", new_y="NEXT")
        pdf.ln(4)
        for block in content.replace("\r", "").split("\n"):
            line = block.rstrip()
            if not line:
                pdf.ln(3)
                continue
            if line.startswith("# "):
                pdf.set_font(font, "B", 14)
                pdf.multi_cell(0, 8, line[2:], new_x="LMARGIN", new_y="NEXT")
                pdf.set_font(font, "", 11)
            elif line.startswith(("- ", "• ")):
                pdf.set_font(font, "", 11)
                pdf.multi_cell(0, 6, "• " + line[2:], new_x="LMARGIN", new_y="NEXT")
            else:
                pdf.set_font(font, "", 11)
                pdf.multi_cell(0, 6, line, new_x="LMARGIN", new_y="NEXT")
        pdf.output(str(target))
        return f"PDF créé : {target} ({pdf.pages_count} page(s))"
    except Exception as exc:  # noqa: BLE001
        return f"Erreur de création du PDF : {exc}"


def create_docx(path: str, title: str, content: str) -> str:
    """Crée un document Word (.docx) avec un titre et du texte (lignes "# " = sous-titres, "- " = puces).

    Args:
        path: Chemin du fichier à créer, par exemple "lettre.docx" (dossier de travail) ou un chemin complet.
        title: Le titre du document.
        content: Le texte du document.
    """
    try:
        import docx

        target = _safe_path(path if path.lower().endswith(".docx") else path + ".docx")
        target.parent.mkdir(parents=True, exist_ok=True)
        d = docx.Document()
        d.add_heading(title, level=0)
        for line in content.replace("\r", "").split("\n"):
            line = line.rstrip()
            if not line:
                continue
            if line.startswith("# "):
                d.add_heading(line[2:], level=1)
            elif line.startswith(("- ", "• ")):
                d.add_paragraph(line[2:], style="List Bullet")
            else:
                d.add_paragraph(line)
        d.save(str(target))
        return f"Document Word créé : {target}"
    except Exception as exc:  # noqa: BLE001
        return f"Erreur de création du document : {exc}"


# --------------------------------------------------------------------------
# Écran, souris, clavier
# --------------------------------------------------------------------------

IMAGE_MARK = "[[image:"


def see_screen(monitor: int = 0, window: str = "") -> str:
    """Regarde l'écran : capture d'écran (avec grille de coordonnées) et liste des boutons, champs et liens de la fenêtre active. Donne `window` pour remettre d'abord une fenêtre au premier plan (sinon elle peut être cachée derrière une autre).

    Args:
        monitor: 0 = l'écran où se trouve la fenêtre active (par défaut), 1 = écran principal, 2 = second écran.
        window: Optionnel : un morceau du titre de la fenêtre à mettre devant avant de regarder (ex. "Epic Games", "Chrome").
    """
    try:
        import computer

        note = ""
        if window and window.strip():
            note = computer.focus_window(window.strip()) + "\n"
            time.sleep(0.8)
        path, text = computer.describe_screen(int(monitor))
        text = note + text
        return f"{IMAGE_MARK}{path}]]\n{text}"
    except Exception as exc:  # noqa: BLE001
        return f"Erreur de capture : {exc}"


def click(x: int, y: int, double: bool = False, right: bool = False) -> str:
    """Clique à des coordonnées écran (celles de la grille rouge de see_screen ou d'un élément listé).

    Args:
        x: Position horizontale en pixels.
        y: Position verticale en pixels.
        double: True pour un double-clic.
        right: True pour un clic droit.
    """
    try:
        import computer

        return computer.click(x, y, button="right" if right else "left", double=bool(double))
    except Exception as exc:  # noqa: BLE001
        return f"Erreur de clic : {exc}"


def click_element(name: str, double: bool = False) -> str:
    """Clique sur un élément listé par see_screen, par son nom (bouton, lien, champ…). Plus fiable que click(x, y).

    Args:
        name: Le nom exact ou approché de l'élément, tel que listé par see_screen.
        double: True pour un double-clic.
    """
    try:
        import computer

        return computer.click_element(name, double=bool(double))
    except Exception as exc:  # noqa: BLE001
        return f"Erreur de clic : {exc}"


def type_text(text: str, press_enter: bool = False) -> str:
    """Tape du texte au clavier dans le champ qui a le focus (clique d'abord dans le champ). Sert aussi pour un e-mail ou un mot de passe dicté par l'utilisateur sur une page de connexion.

    Args:
        text: Le texte à taper, accents compris.
        press_enter: True pour appuyer sur Entrée après.
    """
    try:
        import computer

        return computer.type_text(text, press_enter=bool(press_enter))
    except Exception as exc:  # noqa: BLE001
        return f"Erreur de saisie : {exc}"


def press_keys(keys: str) -> str:
    """Appuie sur une touche ou un raccourci clavier.

    Args:
        keys: Par exemple "enter", "esc", "tab", "ctrl+s", "ctrl+c", "alt+tab", "win+d", "ctrl+shift+t".
    """
    try:
        import computer

        return computer.press_keys(keys)
    except Exception as exc:  # noqa: BLE001
        return f"Erreur clavier : {exc}"


def scroll(amount: int) -> str:
    """Fait défiler la fenêtre sous la souris.

    Args:
        amount: Nombre de crans : positif vers le haut, négatif vers le bas (par exemple -5).
    """
    try:
        import computer

        return computer.scroll(int(amount))
    except Exception as exc:  # noqa: BLE001
        return f"Erreur de défilement : {exc}"


def change_volume(action: str, steps: int = 5) -> str:
    """Règle le son de l'ordinateur : monter, baisser ou couper/rétablir le volume.

    Args:
        action: "up" (monter), "down" (baisser) ou "mute" (couper / rétablir).
        steps: Nombre de crans pour up/down (1 cran = 2 %). 5 crans = 10 %.
    """
    try:
        import pyautogui

        action = action.strip().lower()
        key = {"up": "volumeup", "monter": "volumeup", "down": "volumedown", "baisser": "volumedown",
               "mute": "volumemute", "couper": "volumemute", "muet": "volumemute"}.get(action)
        if key is None:
            return "Action inconnue : utilise up, down ou mute."
        n = 1 if key == "volumemute" else max(1, min(int(steps), 50))
        pyautogui.press(key, presses=n, interval=0.02)
        return {"volumeup": f"Volume monté de {2 * n} %", "volumedown": f"Volume baissé de {2 * n} %",
                "volumemute": "Son coupé ou rétabli"}[key]
    except Exception as exc:  # noqa: BLE001
        return f"Erreur volume : {exc}"


def _audio_sessions():
    if not IS_WINDOWS:
        raise RuntimeError("le volume par application n'existe que sous Windows (mélangeur) ; utilise change_volume pour le volume général")
    from pycaw.pycaw import AudioUtilities

    out = []
    for s in AudioUtilities.GetAllSessions():
        if s.Process:
            out.append((s.Process.name(), s))
    return out


def list_audio_apps() -> str:
    """Liste les applications qui ont un canal audio ouvert (mélangeur Windows) avec leur volume et si elles sont coupées."""
    try:
        seen = {}
        for name, s in _audio_sessions():
            v = round(s.SimpleAudioVolume.GetMasterVolume() * 100)
            seen[name] = f"{name} : {v} %" + (" (muet)" if s.SimpleAudioVolume.GetMute() else "")
        return "\n".join(seen.values()) if seen else "Aucune application ne joue de son actuellement."
    except Exception as exc:  # noqa: BLE001
        return f"Erreur mélangeur : {exc}"


def app_volume(app: str, action: str = "set", level: int = 50) -> str:
    """Règle le volume d'UNE application précise (Spotify, Discord, Chrome, un jeu…) dans le mélangeur Windows, sans toucher aux autres.

    Args:
        app: Nom de l'application (ex. "spotify", "discord", "chrome").
        action: "set" (mettre à level %), "up" (+10 %), "down" (-10 %), "mute" (couper), "unmute" (rétablir).
        level: Pourcentage 0 à 100, utilisé avec "set".
    """
    try:
        key = _norm_app(app).replace(" ", "")
        hits = [(n, s) for n, s in _audio_sessions() if key in _norm_app(n).replace(" ", "").replace(".exe", "")]
        if not hits:
            return f"Aucune application audio ne ressemble à « {app} ». " + list_audio_apps()
        action = (action or "set").strip().lower()
        results = []
        for name, s in hits:
            vol = s.SimpleAudioVolume
            cur = vol.GetMasterVolume()
            if action in ("mute", "couper", "muet"):
                vol.SetMute(1, None); results.append(f"{name} : son coupé")
            elif action in ("unmute", "retablir", "rétablir"):
                vol.SetMute(0, None); results.append(f"{name} : son rétabli")
            elif action in ("up", "monter", "plus"):
                new = min(1.0, cur + 0.10); vol.SetMasterVolume(new, None); results.append(f"{name} : {round(new*100)} %")
            elif action in ("down", "baisser", "moins"):
                new = max(0.0, cur - 0.10); vol.SetMasterVolume(new, None); results.append(f"{name} : {round(new*100)} %")
            else:
                new = max(0, min(100, int(level))) / 100; vol.SetMasterVolume(new, None); vol.SetMute(0, None)
                results.append(f"{name} : {round(new*100)} %")
        return "Volume réglé : " + " ; ".join(dict.fromkeys(results))
    except Exception as exc:  # noqa: BLE001
        return f"Erreur volume d'application : {exc}"


def media_control(action: str) -> str:
    """Contrôle le lecteur multimédia en cours (Spotify, YouTube, VLC…) : lecture/pause, piste suivante, précédente, stop.

    Args:
        action: "playpause", "next", "previous" ou "stop".
    """
    try:
        import pyautogui

        key = {"playpause": "playpause", "play": "playpause", "pause": "playpause", "lecture": "playpause",
               "next": "nexttrack", "suivant": "nexttrack", "previous": "prevtrack", "precedent": "prevtrack",
               "précédent": "prevtrack", "stop": "stop"}.get(action.strip().lower())
        if key is None:
            return "Action inconnue : playpause, next, previous ou stop."
        pyautogui.press(key)
        return f"Commande multimédia envoyée : {key}"
    except Exception as exc:  # noqa: BLE001
        return f"Erreur multimédia : {exc}"


def move_mouse(x: int, y: int) -> str:
    """Déplace la souris à des coordonnées écran sans cliquer (survol, menus qui s'ouvrent au passage, viser avant un clic).

    Args:
        x: Position horizontale en pixels.
        y: Position verticale en pixels.
    """
    try:
        import computer

        return computer.move(x, y)
    except Exception as exc:  # noqa: BLE001
        return f"Erreur souris : {exc}"


def drag(x1: int, y1: int, x2: int, y2: int) -> str:
    """Glisser-déposer à la souris : déplacer un fichier, une fenêtre, un curseur de réglage, sélectionner du texte.

    Args:
        x1: Départ horizontal.
        y1: Départ vertical.
        x2: Arrivée horizontale.
        y2: Arrivée verticale.
    """
    try:
        import computer

        return computer.drag(x1, y1, x2, y2)
    except Exception as exc:  # noqa: BLE001
        return f"Erreur de glisser-déposer : {exc}"


def zoom_screen(x: int, y: int) -> str:
    """Loupe : image en pleine résolution d'une zone de 600x400 px autour d'un point, avec une grille fine, pour lire un petit texte ou viser un petit bouton avant click(x, y).

    Args:
        x: Centre horizontal de la zone (coordonnées écran).
        y: Centre vertical de la zone.
    """
    try:
        import computer

        path, text = computer.zoom(int(x), int(y))
        return f"{IMAGE_MARK}{path}]]\n{text}"
    except Exception as exc:  # noqa: BLE001
        return f"Erreur de loupe : {exc}"


def wait(seconds: float = 2) -> str:
    """Attend quelques secondes (page qui charge, application qui s'ouvre, animation) avant de regarder à nouveau l'écran.

    Args:
        seconds: Durée en secondes (0.5 à 15).
    """
    s = max(0.5, min(15.0, float(seconds)))
    time.sleep(s)
    return f"Attendu {s:g} s."


def list_windows() -> str:
    """Liste les fenêtres ouvertes (titres)."""
    try:
        import computer

        titles = computer.list_windows()
        return "\n".join(titles) if titles else "Aucune fenêtre visible."
    except Exception as exc:  # noqa: BLE001
        return f"Erreur : {exc}"


def focus_window(title: str) -> str:
    """Met une fenêtre au premier plan d'après une partie de son titre.

    Args:
        title: Un morceau du titre, par exemple "Chrome", "Discord", "Bloc-notes".
    """
    try:
        import computer

        return computer.focus_window(title)
    except Exception as exc:  # noqa: BLE001
        return f"Erreur : {exc}"


# Liste passée au modèle. L'ordre n'a pas d'importance.
TOOLS = [get_datetime, calculate, remember, recall, forget, research, learn, show_projects, hide_projects,
         show_agenda, hide_agenda, agenda_month, add_event, remove_event, list_events,
         list_models, switch_model, list_skills, use_skill,
         search_files, open_file, list_files, read_file, write_file, create_pdf, create_docx,
         check_app, list_apps, open_app, close_app, open_site, open_url, run_command, web_search, fetch_url,
         see_screen, zoom_screen, click, click_element, move_mouse, drag, type_text, press_keys, scroll, wait,
         list_windows, focus_window,
         change_volume, media_control, app_volume, list_audio_apps]
TOOL_MAP = {fn.__name__: fn for fn in TOOLS}


def active_tools() -> list:
    """Outils à présenter au modèle actif (liste réduite pour les petits modèles)."""
    if not config.ACTIVE_TOOLS:
        return TOOLS
    return [fn for fn in TOOLS if fn.__name__ in config.ACTIVE_TOOLS]
