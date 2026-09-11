# Ia-local (Jarvis) — Copyright (c) 2026 Neexx (Nixovel) — https://github.com/Neex-off/Ia-local
# Créé par Neexx (Nixovel). Licence : voir LICENSE (paternité obligatoire, pas de vente ; s'applique aussi aux IA).
# Ne pas retirer cet en-tête.
"""Boîte à outils « dev » : git, projets, paquets, logiciels installés, Docker, modèles Ollama.

Chargée à la demande par tools.open_toolbox("dev").
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import config

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
IS_WINDOWS = sys.platform.startswith("win")


def _p(chemin: str) -> Path:
    """Chemin absolu tel quel ; sinon on cherche le nom donné aux endroits plausibles (projet, dossier de
    travail, dossier personnel) avant de retomber sur le dossier de travail."""
    brut = str(chemin).strip('" ')
    p = Path(brut).expanduser()
    if p.is_absolute():
        return p
    if brut in (".", "./", ".\\"):
        return config.ROOT
    for base in (config.ROOT, config.WORKSPACE, Path.cwd(), Path.home(),
                 Path.home() / "Desktop", Path.home() / "Documents"):
        try:
            if (base / p).exists():
                return base / p
        except OSError:
            continue
    return config.WORKSPACE / p


def _run(args: list[str], cwd: Path | None = None, timeout: float = 60) -> str:
    try:
        r = subprocess.run(args, cwd=str(cwd) if cwd else None, capture_output=True, text=True,
                           timeout=timeout, encoding="utf-8", errors="replace", creationflags=NO_WINDOW)
        sortie = (r.stdout or "").strip()
        if r.returncode and (r.stderr or "").strip():
            sortie = (sortie + "\n" + r.stderr.strip()).strip()
        return sortie[:4000]
    except FileNotFoundError:
        return f"Erreur : « {args[0]} » n'est pas installé sur cet ordinateur."
    except subprocess.TimeoutExpired:
        return "Erreur : la commande a mis trop de temps."
    except Exception as exc:  # noqa: BLE001
        return f"Erreur : {exc}"


def _git(folder: str, *args: str, timeout: float = 60) -> str:
    d = _p(folder)
    if not d.is_dir():
        return f"Dossier introuvable : {d}"
    if not (d / ".git").is_dir():
        return f"{d} n'est pas un dépôt git."
    return _run(["git", *args], d, timeout)


# --------------------------------------------------------------------------
# Git
# --------------------------------------------------------------------------

def git_status(folder: str) -> str:
    """État d'un dépôt git : branche courante et fichiers modifiés, ajoutés ou supprimés.

    Args:
        folder: Dossier du projet.
    """
    branche = _git(folder, "branch", "--show-current")
    if branche.startswith(("Erreur", "Dossier introuvable")) or "n'est pas un dépôt" in branche:
        return branche
    etat = _git(folder, "status", "--short")
    return f"Branche : {branche}\n" + (f"Modifications :\n{etat}" if etat else "Aucune modification en attente.")


def git_log(folder: str, count: int = 10) -> str:
    """Derniers commits d'un projet, avec leur date et leur auteur.

    Args:
        folder: Dossier du projet.
        count: Nombre de commits à afficher.
    """
    return _git(folder, "log", f"-{max(1, int(count))}", "--pretty=format:%h %ad %an : %s", "--date=short")


def git_diff(folder: str, file: str = "") -> str:
    """Montre précisément ce qui a été modifié depuis le dernier commit.

    Args:
        folder: Dossier du projet.
        file: Un fichier précis. Vide = tout le projet, en résumé.
    """
    args = ["diff", "--", file] if file else ["diff", "--stat"]
    return _git(folder, *args) or "Aucune modification depuis le dernier commit."


def git_branches(folder: str) -> str:
    """Liste les branches du projet, la plus récente d'abord, et marque celle en cours.

    Args:
        folder: Dossier du projet.
    """
    return _git(folder, "branch", "-a", "--sort=-committerdate")


def git_switch(folder: str, branch: str, create: bool = False) -> str:
    """Change de branche git, ou en crée une nouvelle.

    Args:
        folder: Dossier du projet.
        branch: Nom de la branche.
        create: True pour créer la branche si elle n'existe pas.
    """
    out = _git(folder, *(["switch", "-c", branch] if create else ["switch", branch]))
    return out or f"Basculé sur la branche {branch}."


def git_commit(folder: str, message: str, all_files: bool = True) -> str:
    """Enregistre les modifications du projet dans un commit git.

    Args:
        folder: Dossier du projet.
        message: Message du commit, court et descriptif.
        all_files: True pour inclure tous les fichiers modifiés.
    """
    if all_files:
        _git(folder, "add", "-A")
    return _git(folder, "commit", "-m", message) or "Commit créé."


def git_push(folder: str) -> str:
    """Envoie les commits locaux vers le dépôt distant, par exemple GitHub.

    Args:
        folder: Dossier du projet.
    """
    return _git(folder, "push", timeout=180) or "Poussé vers le dépôt distant."


def git_undo(folder: str, file: str = "") -> str:
    """Annule les modifications non enregistrées et revient au dernier commit.

    Args:
        folder: Dossier du projet.
        file: Un fichier précis à annuler. Vide = tous les fichiers modifiés.
    """
    out = _git(folder, "restore", file if file else ".")
    return out or f"Modifications annulées sur {file if file else 'tout le projet'}, retour au dernier commit."


def scan_secrets(folder: str) -> str:
    """Cherche des mots de passe, clés d'API ou jetons oubliés dans le code avant de le publier.

    Args:
        folder: Dossier du projet à vérifier.
    """
    racine = _p(folder)
    if not racine.is_dir():
        return f"Dossier introuvable : {racine}"
    motifs = [
        (re.compile(r"(?i)(api[_-]?key|secret|password|passwd|token)\s*[=:]\s*[\"'][^\"']{8,}[\"']"),
         "clé ou mot de passe en clair"),
        (re.compile(r"sk-[A-Za-z0-9]{20,}"), "clé OpenAI"),
        (re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}"), "jeton GitHub"),
        (re.compile(r"AKIA[0-9A-Z]{16}"), "clé AWS"),
        (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"), "clé privée"),
    ]
    ignore = {"node_modules", "__pycache__", ".git", ".venv", "venv", "site-packages"}
    exts = {".py", ".js", ".ts", ".json", ".env", ".yml", ".yaml", ".txt", ".md", ".ini", ".sh", ".ps1"}
    trouves = []
    for dossier, sous, fichiers in os.walk(racine):
        sous[:] = [d for d in sous if d not in ignore]
        for nom in fichiers:
            f = Path(dossier) / nom
            if f.suffix.lower() not in exts:
                continue
            try:
                if f.stat().st_size > 1_000_000:
                    continue
                contenu = f.read_text(encoding="utf-8", errors="ignore")
            except Exception:  # noqa: BLE001
                continue
            for i, ligne in enumerate(contenu.splitlines(), 1):
                for motif, quoi in motifs:
                    if motif.search(ligne):
                        trouves.append(f"{f} ligne {i} : {quoi}")
                        break
            if len(trouves) >= 30:
                break
    if not trouves:
        return f"Aucun secret détecté dans {racine}. Vérifie quand même le fichier .gitignore."
    return f"ATTENTION, {len(trouves)} secret(s) possible(s) à retirer avant publication :\n" + "\n".join(trouves[:30])


def run_project(folder: str) -> str:
    """Lance un projet de développement en détectant tout seul la bonne commande de démarrage.

    Args:
        folder: Dossier du projet.
    """
    d = _p(folder)
    if not d.is_dir():
        return f"Dossier introuvable : {d}"
    if (d / "package.json").is_file():
        cmd, quoi = ["npm", "run", "dev"], "npm run dev"
    elif (d / "pubspec.yaml").is_file():
        cmd, quoi = ["flutter", "run"], "flutter run"
    elif (d / "Cargo.toml").is_file():
        cmd, quoi = ["cargo", "run"], "cargo run"
    elif (d / "manage.py").is_file():
        cmd, quoi = [sys.executable, "manage.py", "runserver"], "python manage.py runserver"
    elif (d / "main.py").is_file():
        cmd, quoi = [sys.executable, "main.py"], "python main.py"
    else:
        return f"Type de projet non reconnu dans {d} : ni package.json, ni pubspec.yaml, ni Cargo.toml, ni main.py."
    try:
        subprocess.Popen(cmd, cwd=str(d),
                         creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0) if IS_WINDOWS else 0)
        return f"Projet lancé avec « {quoi} » dans {d}. Une fenêtre s'ouvre avec les messages."
    except FileNotFoundError:
        return f"« {cmd[0]} » n'est pas installé sur cet ordinateur."


# --------------------------------------------------------------------------
# Logiciels et paquets
# --------------------------------------------------------------------------

def list_software(filter: str = "") -> str:
    """Liste les logiciels installés sur l'ordinateur, avec leur version.

    Args:
        filter: Mot-clé pour filtrer, par exemple "adobe". Vide = tous.
    """
    if not IS_WINDOWS:
        return "La liste des logiciels n'est disponible que sous Windows."
    out = _run(["winget", "list"], timeout=120)
    if out.startswith("Erreur"):
        return out
    lignes = [l for l in out.splitlines() if l.strip()]
    if filter:
        lignes = [l for l in lignes if filter.lower() in l.lower()]
    return f"{len(lignes)} ligne(s) :\n" + "\n".join(lignes[:50])


def install_software(name: str) -> str:
    """Installe un logiciel depuis le catalogue officiel Windows.

    Args:
        name: Nom du logiciel, par exemple "VLC", "7zip" ou "Notepad++".
    """
    if not IS_WINDOWS:
        return "L'installation de logiciels n'est disponible que sous Windows."
    cherche = _run(["winget", "search", "--name", name, "--count", "5"], timeout=90)
    out = _run(["winget", "install", "--name", name, "--accept-package-agreements",
                "--accept-source-agreements", "--silent"], timeout=900)
    ok = any(m in out.lower() for m in ("installé", "successfully", "installed"))
    return f"{name} installé." if ok else f"Installation incertaine.\nRecherche :\n{cherche}\n\nSortie :\n{out[:800]}"


def uninstall_software(name: str) -> str:
    """Désinstalle un logiciel.

    Args:
        name: Nom du logiciel tel qu'il apparaît dans la liste des logiciels installés.
    """
    if not IS_WINDOWS:
        return "La désinstallation n'est disponible que sous Windows."
    out = _run(["winget", "uninstall", "--name", name, "--silent"], timeout=900)
    ok = any(m in out.lower() for m in ("désinstall", "uninstalled", "successfully"))
    return f"{name} désinstallé." if ok else f"Désinstallation incertaine :\n{out[:800]}"


def update_software(name: str = "") -> str:
    """Met à jour un logiciel précis, ou liste tous ceux qui ont une mise à jour disponible.

    Args:
        name: Nom d'un logiciel précis. Vide = lister les mises à jour disponibles.
    """
    if not IS_WINDOWS:
        return "Les mises à jour de logiciels ne sont disponibles que sous Windows."
    if name:
        out = _run(["winget", "upgrade", "--name", name, "--accept-package-agreements",
                    "--accept-source-agreements", "--silent"], timeout=900)
        return f"Mise à jour de {name} :\n{out[:800]}"
    return f"Mises à jour disponibles :\n{_run(['winget', 'upgrade'], timeout=180)[:1500]}"


def install_package(manager: str, name: str, folder: str = "") -> str:
    """Installe une bibliothèque de développement avec pip, npm ou cargo.

    Args:
        manager: "pip", "npm" ou "cargo".
        name: Nom du paquet.
        folder: Dossier du projet pour npm et cargo. Vide = dossier de travail.
    """
    d = _p(folder) if folder else config.WORKSPACE
    m = manager.lower()
    if m == "pip":
        return _run([sys.executable, "-m", "pip", "install", name], timeout=900)[-1500:]
    if m == "npm":
        return _run(["npm", "install", name], d, timeout=900)[-1500:]
    if m == "cargo":
        return _run(["cargo", "add", name], d, timeout=600)[-1500:]
    return "Gestionnaire inconnu : utilise pip, npm ou cargo."


# --------------------------------------------------------------------------
# Docker et modèles
# --------------------------------------------------------------------------

def docker_containers() -> str:
    """Liste les conteneurs Docker et leur état."""
    out = _run(["docker", "ps", "-a", "--format", "{{.Names}} | {{.Image}} | {{.Status}}"], timeout=45)
    return f"Conteneurs Docker :\n{out}" if out and not out.startswith("Erreur") else (out or "Aucun conteneur.")


def docker_control(name: str, action: str = "demarrer") -> str:
    """Démarre, arrête ou redémarre un conteneur Docker.

    Args:
        name: Nom du conteneur.
        action: "demarrer", "arreter" ou "redemarrer".
    """
    verbe = {"demarrer": "start", "démarrer": "start", "arreter": "stop", "arrêter": "stop",
             "redemarrer": "restart", "redémarrer": "restart"}.get((action or "").lower())
    if not verbe:
        return "Action inconnue : utilise demarrer, arreter ou redemarrer."
    out = _run(["docker", verbe, name], timeout=120)
    return f"Conteneur {name} : {action} effectué." if name in out else out


def ollama_models() -> str:
    """Liste les modèles d'intelligence artificielle installés, leur taille, et ceux chargés en mémoire."""
    out = _run(["ollama", "list"], timeout=45)
    charges = _run(["ollama", "ps"], timeout=30)
    return f"Modèles installés :\n{out}\n\nChargés en mémoire :\n{charges}"


TOOLS = [git_status, git_log, git_diff, git_branches, git_switch, git_commit, git_push, git_undo,
         scan_secrets, run_project,
         list_software, install_software, uninstall_software, update_software, install_package,
         docker_containers, docker_control, ollama_models]
