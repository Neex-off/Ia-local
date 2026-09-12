# Ia-local (Jarvis) — Copyright (c) 2026 Neexx (Nixovel) — https://github.com/Neex-off/Ia-local
# Créé par Neexx (Nixovel). Licence : voir LICENSE (paternité obligatoire, pas de vente ; s'applique aussi aux IA).
# Ne pas retirer cet en-tête.
"""Boîte à outils « noyau » : ce que l'assistant a fait, annuler, arrêt d'urgence, modules, mode privé,
configuration, mise à jour, statistiques, personnalités, création de nouveaux outils, accès à distance.

Chargée à la demande par tools.open_toolbox("noyau").
"""
from __future__ import annotations

import importlib
import json
import py_compile
import re
import shutil
import socket
import subprocess
import zipfile
from datetime import datetime
from pathlib import Path

import config
import noyau

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
PERSO = config.ROOT / "outils_perso.py"


def what_did_you_do(count: int = 15, hours: float = 0) -> str:
    """« Qu'est-ce que tu as fait ? » : lit le journal d'audit des actions (ok, refusée, bloquée, erreur).

    Args:
        count: Nombre d'actions à montrer, les plus récentes d'abord.
        hours: Ne garder que les N dernières heures (0 = sans limite).
    """
    lignes = noyau.lire_audit(n=max(1, int(count)), depuis_heures=float(hours))
    if not lignes:
        return "Le journal est vide : aucune action enregistrée."
    out = []
    for d in lignes:
        args = ", ".join(f"{k}={str(v)[:30]}" for k, v in (d.get("args") or {}).items())
        out.append(f"{d['t'][11:16]} {d['outil']}({args}) -> {d['statut']}"
                   + (f" : {d['detail'][:70]}" if d.get("detail") else ""))
    return "\n".join(out)


def undo_last() -> str:
    """Annule la dernière action réversible (fichier déplacé, renommé, mis à la corbeille, application fermée…)."""
    return noyau.undo_last()


def stop_all() -> str:
    """ARRÊT D'URGENCE : coupe la parole, les tâches de fond et bloque toute nouvelle action jusqu'à resume_all."""
    return noyau.arret_urgence()


def resume_all() -> str:
    """Lève l'arrêt d'urgence : les actions repassent."""
    return noyau.reprendre()


def private_mode(enabled: bool = True) -> str:
    """Mode privé : le micro se coupe et plus rien n'est retenu (ni conversation, ni journal) tant qu'il est actif.

    Args:
        enabled: True pour activer, False pour revenir au mode normal.
    """
    noyau.set_prive(bool(enabled))
    return ("Mode privé activé : je n'écoute plus et je ne retiens rien. Dis « mode normal » ou écris-le pour revenir."
            if enabled else "Mode privé désactivé : j'écoute et je retiens à nouveau.")


def toggle_module(name: str, enabled: bool = True) -> str:
    """Active ou désactive une boîte à outils (module). Un module désactivé ne s'ouvre plus.

    Args:
        name: Nom du module (systeme, fichiers, machine, dev, code, web, ia, vie, business, contenu, serveur, windows, securite, jeux…).
        enabled: True pour activer, False pour désactiver.
    """
    import tools

    if name not in tools.TOOLBOXES:
        return f"Module inconnu : « {name} ». Modules : {', '.join(tools.TOOLBOXES)}."
    noyau.set_module(name, bool(enabled))
    if not enabled and name in tools._OPENED:
        tools._OPENED.remove(name)
    return f"Module « {name} » {'activé' if enabled else 'désactivé'}."


def list_modules() -> str:
    """Liste les modules (boîtes à outils) avec leur état actif / désactivé et le nombre d'outils."""
    import tools

    out = []
    for nom in tools.TOOLBOXES:
        n = len(tools._TOOLBOX_TOOLS.get(nom, []))
        etat = "actif" if noyau.module_actif(nom) else "DÉSACTIVÉ"
        out.append(f"- {nom} : {n} outils, {etat}" + (" (ouvert)" if nom in tools._OPENED else ""))
    return "\n".join(out)


def self_check() -> str:
    """Auto-diagnostic : quels modules se chargent, quels programmes externes sont présents, quelles clés sont configurées."""
    import tools

    out = []
    for nom, (module, _d) in tools.TOOLBOXES.items():
        try:
            importlib.import_module(module)
            out.append(f"OK  module {nom}")
        except Exception as exc:  # noqa: BLE001
            out.append(f"KO  module {nom} : {str(exc)[:60]}")
    for exe in ("ollama", "git", "ffmpeg", "adb", "winget", "code", "node", "docker", "ssh", "python"):
        out.append(f"{'OK ' if shutil.which(exe) else '-- '} programme {exe}")
    try:
        import sounddevice as sd

        out.append(f"OK  audio : {len(sd.query_devices())} périphériques")
    except Exception as exc:  # noqa: BLE001
        out.append(f"KO  audio : {str(exc)[:60]}")
    try:
        r = subprocess.run(["nvidia-smi", "--query-gpu=name,memory.used,memory.total", "--format=csv,noheader"],
                           capture_output=True, text=True, timeout=10, creationflags=NO_WINDOW)
        out.append(f"OK  GPU : {r.stdout.strip()}" if r.returncode == 0 else "--  GPU NVIDIA absent")
    except Exception:  # noqa: BLE001
        out.append("--  GPU NVIDIA absent")
    cles = ("GITHUB_TOKEN", "VIRUSTOTAL_KEY", "HIBP_KEY", "STRIPE_KEY", "YOUTUBE_KEY", "TELEGRAM_TOKEN",
            "DISCORD_TOKEN", "DISCORD_APP_ID", "FIGMA_TOKEN", "HOME_ASSISTANT_TOKEN", "TMDB_KEY")
    for c in cles:
        out.append(f"{'OK ' if getattr(config, c, '') else '-- '} clé {c}")
    try:
        import winsdk  # noqa: F401

        out.append("OK  OCR Windows")
    except Exception:  # noqa: BLE001
        out.append("--  OCR Windows (winsdk)")
    return "\n".join(out)


def usage_stats(days: int = 30) -> str:
    """Statistiques d'utilisation de l'assistant : actions, outils les plus utilisés, erreurs, messages.

    Args:
        days: Période en jours (365 pour le récapitulatif annuel).
    """
    s = noyau.statistiques(int(days))
    top = ", ".join(f"{n} ({c})" for n, c in s["par_outil"]) or "aucun"
    jours_actifs = len(s["par_jour"])
    meilleur = max(s["par_jour"], key=lambda x: x[1]) if s["par_jour"] else ("-", 0)
    return (f"Sur {days} jours : {s['actions']} actions, {s['messages_utilisateur']} messages de l'utilisateur au total, "
            f"{jours_actifs} jours actifs, journée record {meilleur[0]} ({meilleur[1]} actions).\n"
            f"Statuts : {s['statuts']}\nOutils les plus utilisés : {top}")


def year_recap() -> str:
    """Récapitulatif annuel d'utilisation : volume, habitudes, outils favoris, séances de sport et journal."""
    base = usage_stats(365)
    extra = []
    try:
        j = json.loads((config.ROOT / "memoire" / "journal.json").read_text(encoding="utf-8"))
        entrees = j if isinstance(j, list) else j.get("entrees", [])
        sport = sum(1 for e in entrees if str(e.get("type", "")).startswith("sport"))
        extra.append(f"Journal : {len(entrees)} entrées dont {sport} séances de sport.")
    except Exception:  # noqa: BLE001
        pass
    try:
        ag = json.loads((config.ROOT / "memoire" / "agenda.json").read_text(encoding="utf-8"))
        n = len(ag if isinstance(ag, list) else ag.get("events", []))
        extra.append(f"Agenda : {n} événements enregistrés.")
    except Exception:  # noqa: BLE001
        pass
    return base + ("\n" + "\n".join(extra) if extra else "")


def set_personality(name: str = "jarvis") -> str:
    """Change la personnalité de l'assistant : jarvis (défaut), serieux, sarcastique, coach, prof, ami.

    Args:
        name: Le nom de la personnalité.
    """
    n = name.strip().lower()
    if not noyau.set_personnalite(n):
        return f"Personnalité inconnue. Choix : {', '.join(noyau.PERSONNALITES)}."
    return f"Personnalité « {n} » activée à partir du prochain message."


def set_permission(tool: str, level: str = "vert") -> str:
    """Change le niveau de permission d'un outil : vert (direct), orange (confirmation), rouge (interdit).

    Args:
        tool: Nom exact de l'outil.
        level: vert, orange ou rouge.
    """
    import tools

    if tool not in tools.TOOL_MAP:
        return f"Outil inconnu : {tool}."
    if level not in ("vert", "orange", "rouge"):
        return "Niveau : vert, orange ou rouge."
    noyau.set_niveau(tool, level)
    return f"« {tool} » est maintenant {level}."


def export_config(path: str = "") -> str:
    """Exporte toute la configuration et la mémoire (sans les clés secrètes) dans un zip.

    Args:
        path: Chemin du zip à créer (vide = workspace/jarvis-config-DATE.zip).
    """
    dest = Path(path) if path else config.WORKSPACE / f"jarvis-config-{datetime.now():%Y%m%d-%H%M}.zip"
    dest.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as z:
        cfg = (config.ROOT / "config.py").read_text(encoding="utf-8")
        cfg = re.sub(r'^(\w*(?:TOKEN|KEY|SECRET|PASSWORD)\w*\s*=\s*)["\'].*?["\']', r'\1""', cfg, flags=re.M)
        z.writestr("config.py", cfg)
        n += 1
        for motif in ("*.json", "*.jsonl"):
            for f in (config.ROOT / "memoire").glob(motif):
                z.write(f, f"memoire/{f.name}")
                n += 1
        skills = config.ROOT / "skills"
        if skills.exists():
            for f in skills.rglob("*.md"):
                z.write(f, f"skills/{f.relative_to(skills)}")
                n += 1
    return f"Configuration exportée : {dest} ({n} fichiers, clés secrètes retirées)."


def import_config(path: str, memory: bool = True, settings: bool = False) -> str:
    """Réimporte une configuration exportée par export_config.

    Args:
        path: Chemin du zip.
        memory: Restaurer la mémoire (agenda, journal, faits…).
        settings: Remplacer aussi config.py (les clés secrètes devront être ressaisies).
    """
    p = Path(path)
    if not p.exists():
        return f"Introuvable : {p}"
    n = 0
    with zipfile.ZipFile(p) as z:
        for name in z.namelist():
            if name.startswith("memoire/") and memory:
                (config.ROOT / name).parent.mkdir(parents=True, exist_ok=True)
                (config.ROOT / name).write_bytes(z.read(name))
                n += 1
            elif name == "config.py" and settings:
                shutil.copy(config.ROOT / "config.py", config.ROOT / "config.py.bak")
                (config.ROOT / "config.py").write_bytes(z.read(name))
                n += 1
            elif name.startswith("skills/"):
                (config.ROOT / name).parent.mkdir(parents=True, exist_ok=True)
                (config.ROOT / name).write_bytes(z.read(name))
                n += 1
    return f"{n} fichiers restaurés. Redémarre Jarvis pour tout prendre en compte."


def install_module(path: str, name: str = "", description: str = "") -> str:
    """Installe un module tiers (fichier .py qui expose une liste TOOLS) comme nouvelle boîte à outils, après tests.

    Args:
        path: Chemin du fichier .py à installer.
        name: Nom de la boîte (vide = déduit du nom de fichier).
        description: Ce que fait la boîte, pour le menu open_toolbox.
    """
    import tools

    src = Path(path)
    if not src.exists() or src.suffix != ".py":
        return f"Fichier .py introuvable : {src}"
    nom = (name or src.stem.replace("outils_", "")).strip().lower()
    module = f"outils_{nom}"
    dest = config.ROOT / f"{module}.py"
    try:
        py_compile.compile(str(src), doraise=True)
    except Exception as exc:  # noqa: BLE001
        return f"Refusé : le module ne compile pas ({exc})."
    code = src.read_text(encoding="utf-8", errors="replace")
    if "TOOLS" not in code:
        return "Refusé : le module n'expose pas de liste TOOLS."
    if noyau._ROUGE.search(code):
        return "Refusé : le module contient une opération interdite."
    shutil.copy(src, dest)
    try:
        m = importlib.import_module(module)
        importlib.reload(m)
        fns = list(m.TOOLS)
        for fn in fns:
            if not callable(fn) or not (fn.__doc__ or "").strip():
                raise ValueError(f"{getattr(fn, '__name__', fn)} sans docstring")
    except Exception as exc:  # noqa: BLE001
        dest.unlink(missing_ok=True)
        return f"Refusé, test d'import échoué : {exc}"
    tools.TOOLBOXES[nom] = (module, description or f"module tiers {nom}")
    tools._TOOLBOX_TOOLS[nom] = fns
    tools.TOOL_MAP.update({fn.__name__: fn for fn in fns})
    noyau.add_module_tiers(nom, module, description or f"module tiers {nom}")
    return f"Module « {nom} » installé : {len(fns)} outils ({', '.join(fn.__name__ for fn in fns)}). open_toolbox(\"{nom}\") pour l'ouvrir."


def create_tool(name: str, code: str, test: str = "") -> str:
    """Crée un nouvel outil Python que tu écris toi-même, avec test obligatoire, dans la boîte « perso ».

    Args:
        name: Nom de la fonction (snake_case), unique.
        code: Code complet de la fonction `def name(...) -> str:` avec sa docstring (Args: …). Imports à l'intérieur.
        test: Expression Python qui doit s'exécuter sans erreur, ex. 'name("exemple")'. Vide = simple import.
    """
    import tools

    nom = name.strip()
    if not nom.isidentifier() or nom in tools.TOOL_MAP:
        return f"Nom invalide ou déjà pris : {nom}."
    if f"def {nom}(" not in code or '"""' not in code:
        return "Le code doit définir la fonction avec ce nom et une docstring."
    if noyau._ROUGE.search(code):
        return "Refusé : le code contient une opération interdite."
    entete = ('"""Boîte « perso » : outils créés par l\'assistant lui-même (create_tool).\n"""\n'
              "from __future__ import annotations\n\nTOOLS = []\n\n")
    if not PERSO.exists():
        PERSO.write_text(entete, encoding="utf-8")
    ancien = PERSO.read_text(encoding="utf-8")
    nouveau = ancien.rstrip() + "\n\n\n" + code.strip() + f"\n\n\nTOOLS.append({nom})\n"
    PERSO.write_text(nouveau, encoding="utf-8")
    try:
        py_compile.compile(str(PERSO), doraise=True)
        m = importlib.import_module("outils_perso")
        importlib.reload(m)
        fn = getattr(m, nom)
        if test.strip():
            eval(test, {nom: fn, "__builtins__": __builtins__})  # noqa: S307  (test écrit par l'assistant)
    except Exception as exc:  # noqa: BLE001
        PERSO.write_text(ancien, encoding="utf-8")
        return f"Refusé, le test a échoué : {exc}. Corrige le code et réessaie."
    tools.TOOLBOXES.setdefault("perso", ("outils_perso", "outils créés par l'assistant"))
    tools._TOOLBOX_TOOLS["perso"] = list(m.TOOLS)
    tools.TOOL_MAP[nom] = fn
    return f"Outil « {nom} » créé et testé, disponible dans open_toolbox(\"perso\")."


def self_update(apply: bool = False) -> str:
    """Vérifie si une nouvelle version du programme est disponible sur GitHub, et l'applique si apply=True (sauvegarde avant).

    Args:
        apply: False = seulement vérifier, True = remplacer les fichiers du programme par la nouvelle version.
    """
    import io
    import urllib.request

    depot = getattr(config, "UPDATE_REPO", "Neex-off/Ia-local")
    url = f"https://github.com/{depot}/archive/refs/heads/main.zip"
    try:
        data = urllib.request.urlopen(url, timeout=60).read()
    except Exception as exc:  # noqa: BLE001
        return f"Impossible de joindre GitHub : {exc}"
    z = zipfile.ZipFile(io.BytesIO(data))
    racine = z.namelist()[0].split("/")[0]
    diffs = []
    for name in z.namelist():
        if name.endswith("/"):
            continue
        rel = name[len(racine) + 1:]
        if not rel or rel == "config.py" or rel.startswith(("memoire", "voix/", "index")):
            continue
        if not rel.endswith((".py", ".html", ".js", ".css", ".txt", ".md", ".bat", ".sh", ".ps1")):
            continue
        local = config.ROOT / rel
        contenu = z.read(name)
        if not local.exists() or local.read_bytes() != contenu:
            diffs.append((rel, contenu))
    if not diffs:
        return "Déjà à jour."
    if not apply:
        return f"{len(diffs)} fichier(s) différent(s) : {', '.join(r for r, _ in diffs[:15])}. Rappelle self_update(apply=True) pour appliquer."
    sauvegarde = config.WORKSPACE / f"avant-maj-{datetime.now():%Y%m%d-%H%M}"
    sauvegarde.mkdir(parents=True, exist_ok=True)
    for rel, contenu in diffs:
        local = config.ROOT / rel
        if local.exists():
            (sauvegarde / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(local, sauvegarde / rel)
        local.parent.mkdir(parents=True, exist_ok=True)
        local.write_bytes(contenu)
    return f"{len(diffs)} fichiers mis à jour (sauvegarde dans {sauvegarde}). Redémarre Jarvis."


def remote_access_info() -> str:
    """Donne l'adresse pour piloter l'assistant depuis un téléphone ou un autre PC du même réseau (interface web et bouton /action)."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
    except Exception:  # noqa: BLE001
        ip = "127.0.0.1"
    port = getattr(config, "UI_PORT", 8765)
    hote = getattr(config, "UI_HOST", "127.0.0.1")
    note = ("" if hote in ("0.0.0.0", "") else
            " ATTENTION : UI_HOST vaut 127.0.0.1 dans config.py, l'interface n'est visible que sur ce PC ; "
            "mets UI_HOST = \"0.0.0.0\" et redémarre pour l'ouvrir au réseau local.")
    token = getattr(config, "REMOTE_TOKEN", "")
    return (f"Interface : http://{ip}:{port}/ (ouvre-la sur le téléphone, même Wi-Fi). "
            f"Bouton ou Stream Deck : http://{ip}:{port}/action?text=ta+phrase"
            + (f"&token={token}" if token else "") + "." + note)


def voice_owner(action: str = "status") -> str:
    """Reconnaissance du propriétaire à la voix : enrôle ta voix (enroll) ou vérifie l'état (status). Voix inconnue = droits réduits.

    Args:
        action: "enroll" pour apprendre la voix depuis voix/ma_voix.wav, "status", ou "off" pour désactiver.
    """
    ref = config.ROOT / "voix" / "ma_voix.wav"
    emp = config.ROOT / "memoire" / "voix_proprietaire.json"
    if action == "off":
        emp.unlink(missing_ok=True)
        return "Reconnaissance du propriétaire désactivée."
    try:
        from resemblyzer import VoiceEncoder, preprocess_wav
    except Exception:  # noqa: BLE001
        return ("La reconnaissance de locuteur demande le paquet « resemblyzer » (pip install resemblyzer). "
                "Sans lui, tout le monde a les mêmes droits.")
    if action == "enroll":
        if not ref.exists():
            return f"Enregistre d'abord ta voix dans {ref} (10 secondes suffisent)."
        enc = VoiceEncoder()
        vec = enc.embed_utterance(preprocess_wav(ref))
        emp.write_text(json.dumps({"vecteur": [float(x) for x in vec]}), encoding="utf-8")
        return "Voix du propriétaire enregistrée : une voix trop différente n'aura que les outils verts."
    return "Reconnaissance active." if emp.exists() else "Aucune voix enrôlée : voice_owner(\"enroll\")."


TOOLS = [what_did_you_do, undo_last, stop_all, resume_all, private_mode, toggle_module, list_modules,
         self_check, usage_stats, year_recap, set_personality, set_permission, export_config, import_config,
         install_module, create_tool, self_update, remote_access_info, voice_owner]
