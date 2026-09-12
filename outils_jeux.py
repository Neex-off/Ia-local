# Ia-local (Jarvis) — Copyright (c) 2026 Neexx (Nixovel) — https://github.com/Neex-off/Ia-local
# Créé par Neexx (Nixovel). Licence : voir LICENSE (paternité obligatoire, pas de vente ; s'applique aussi aux IA).
# Ne pas retirer cet en-tête.
"""Boîte à outils « jeux » : vérifier les fichiers d'un jeu, overlay FPS, profils souris par jeu, réglages
graphiques, temps de jeu, anti-tilt, analyse de parties, Discord (Rich Presence, modération), sessions entre amis,
installer un jeu, tester un logiciel dans le bac à sable Windows.

Chargée à la demande par tools.open_toolbox("jeux").
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
import webbrowser
from datetime import date, datetime
from pathlib import Path

import config

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
IS_WINDOWS = sys.platform.startswith("win")
JEUX = config.ROOT / "memoire" / "jeux.json"

STEAM_IDS = {"counter-strike": 730, "cs2": 730, "dota": 570, "apex": 1172470, "rust": 252490, "gta": 271590,
             "elden ring": 1245620, "baldur": 1086940, "rocket league": 252950, "terraria": 105600,
             "stardew": 413150, "helldivers": 553850, "palworld": 1623730, "valheim": 892970, "rainbow six": 359550}
JEUX_EXE = {"valorant.exe": "Valorant", "valorant-win64-shipping.exe": "Valorant", "cs2.exe": "Counter-Strike 2",
            "fortniteclient-win64-shipping.exe": "Fortnite", "r5apex.exe": "Apex Legends", "leagueclient.exe": "League of Legends",
            "league of legends.exe": "League of Legends", "rocketleague.exe": "Rocket League", "gta5.exe": "GTA V",
            "eldenring.exe": "Elden Ring", "minecraft.exe": "Minecraft", "javaw.exe": "Minecraft", "overwatch.exe": "Overwatch",
            "rainbowsix.exe": "Rainbow Six", "helldivers2.exe": "Helldivers 2", "palworld-win64-shipping.exe": "Palworld",
            "bg3.exe": "Baldur's Gate 3", "rust.exe": "Rust", "dota2.exe": "Dota 2", "dbd-win64-shipping.exe": "Dead by Daylight"}


def _json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return default


def _save(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _prevenir(texte: str) -> None:
    try:
        import noyau

        if "dire" in noyau.hooks:
            noyau.hooks["dire"](texte)
    except Exception:  # noqa: BLE001
        pass


def verify_game_files(game: str, platform: str = "steam") -> str:
    """Vérifie l'intégrité des fichiers d'un jeu (Steam : lance la vérification ; Epic/Riot : ouvre le lanceur au bon endroit).

    Args:
        game: Nom du jeu (ou son id Steam).
        platform: "steam", "epic" ou "riot".
    """
    g = game.strip().lower()
    if platform == "steam":
        appid = int(g) if g.isdigit() else next((v for k, v in STEAM_IDS.items() if k in g), 0)
        if not appid:
            webbrowser.open("steam://open/games")
            return (f"Je ne connais pas l'id Steam de « {game} » : bibliothèque Steam ouverte. Clic droit sur le jeu > "
                    "Propriétés > Fichiers installés > Vérifier l'intégrité, je peux le faire à l'écran si tu veux.")
        webbrowser.open(f"steam://validate/{appid}")
        return f"Vérification Steam lancée pour « {game} » (id {appid}) : Steam affiche la progression."
    if platform == "epic":
        webbrowser.open("com.epicgames.launcher://apps")
        return "Bibliothèque Epic ouverte : sur le jeu, menu « … » > Gérer > Vérifier. Dis-moi et je clique."
    webbrowser.open("riotclient://")
    return "Client Riot ouvert : paramètres du jeu > Réparer."


def fps_overlay(enable: bool = True) -> str:
    """Overlay FPS et ping : ouvre le widget Performances de la Game Bar (Win+G) et active le compteur FPS de Steam.

    Args:
        enable: True pour afficher, False pour masquer.
    """
    if not IS_WINDOWS:
        return "Disponible seulement sous Windows."
    import pyautogui

    pyautogui.hotkey("win", "g")
    if enable:
        subprocess.run(["powershell", "-NoProfile", "-Command",
                        "Set-ItemProperty 'HKCU:\\Software\\Valve\\Steam' -Name 'InGameOverlayShowFPSCounter' -Value 1 -ErrorAction SilentlyContinue"],
                       capture_output=True, creationflags=NO_WINDOW)
        return ("Game Bar ouverte : épingle le widget « Performances » (icône punaise) pour garder FPS et ping à l'écran. "
                "Le compteur FPS de Steam est aussi activé (coin haut gauche dans les jeux Steam).")
    return "Game Bar masquée."


def game_profile(action: str = "list", game: str = "", dpi: int = 0, sensitivity: float = 0, mouse_speed: int = 0) -> str:
    """Profils souris/clavier par jeu : enregistre DPI, sensibilité et vitesse souris Windows par jeu, et applique la vitesse Windows.

    Args:
        action: "list", "save", "apply" ou "delete".
        game: Nom du jeu.
        dpi: DPI souris (pour mémoire : le DPI se règle dans le logiciel de la souris).
        sensitivity: Sensibilité en jeu (pour mémoire).
        mouse_speed: Vitesse du pointeur Windows 1 à 20 (appliquée).
    """
    base = _json(JEUX, {})
    profils = base.setdefault("profils", {})
    if action == "list":
        if not profils:
            return "Aucun profil. game_profile(\"save\", \"Valorant\", dpi=800, sensitivity=0.4, mouse_speed=10)."
        return "\n".join(f"- {g} : DPI {p.get('dpi', '?')}, sens {p.get('sens', '?')}, vitesse Windows {p.get('vitesse', '?')}"
                         for g, p in profils.items())
    if action == "save":
        profils[game] = {"dpi": dpi, "sens": sensitivity, "vitesse": mouse_speed}
        _save(JEUX, base)
        return f"Profil « {game} » enregistré."
    if action == "delete":
        profils.pop(game, None)
        _save(JEUX, base)
        return f"Profil « {game} » supprimé."
    p = profils.get(game)
    if not p:
        return f"Pas de profil pour « {game} »."
    msg = f"Profil « {game} » : DPI {p['dpi']} (à régler dans le logiciel souris), sensibilité {p['sens']}."
    if p.get("vitesse") and IS_WINDOWS:
        import ctypes

        ctypes.windll.user32.SystemParametersInfoW(0x0071, 0, int(p["vitesse"]), 0)
        msg += f" Vitesse Windows réglée sur {p['vitesse']}."
    return msg


def optimize_graphics(game: str) -> str:
    """Conseils de réglages graphiques pour un jeu sur cette machine (GPU détecté), complétés par une recherche web.

    Args:
        game: Nom du jeu.
    """
    gpu = "GPU inconnu"
    try:
        r = subprocess.run(["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"], capture_output=True, text=True,
                           timeout=10, creationflags=NO_WINDOW)
        gpu = r.stdout.strip() or gpu
    except Exception:  # noqa: BLE001
        pass
    base = (f"Sur {gpu} : vise la fréquence de l'écran (V-Sync off, limite FPS à 2× la fréquence pour un compétitif, "
            "ou NVIDIA Reflex + Low Latency), DLSS Qualité en 1440p et plus, ombres et occlusion ambiante en moyen "
            "(gros gain, peu visible), textures au max si la VRAM le permet, plein écran exclusif, HDR off si l'écran ne le gère pas bien.")
    try:
        import tools

        web = tools.web_search(f"{game} meilleurs paramètres graphiques {gpu} 2026")
        return base + "\n\nRecherche :\n" + web[:1500]
    except Exception:  # noqa: BLE001
        return base


_TEMPS = {"thread": None, "stop": threading.Event()}


def playtime(action: str = "report", days: int = 7) -> str:
    """Suivi du temps de jeu : lance le suivi en fond (start), l'arrête (stop) ou donne le bilan (report).

    Args:
        action: "start", "stop" ou "report".
        days: Période du bilan en jours.
    """
    if action == "stop":
        _TEMPS["stop"].set()
        return "Suivi du temps de jeu arrêté."
    if action == "start":
        if _TEMPS["thread"] and _TEMPS["thread"].is_alive():
            return "Le suivi tourne déjà."
        _TEMPS["stop"].clear()

        def boucle():
            import psutil

            while not _TEMPS["stop"].is_set():
                actifs = {p.info["name"].lower() for p in psutil.process_iter(["name"]) if p.info.get("name")}
                jeux = {JEUX_EXE[e] for e in actifs if e in JEUX_EXE}
                if jeux:
                    base = _json(JEUX, {})
                    jour = date.today().isoformat()
                    for j in jeux:
                        base.setdefault("temps", {}).setdefault(j, {})
                        base["temps"][j][jour] = base["temps"][j].get(jour, 0) + 60
                    _save(JEUX, base)
                _TEMPS["stop"].wait(60)

        _TEMPS["thread"] = threading.Thread(target=boucle, daemon=True)
        _TEMPS["thread"].start()
        return "Suivi du temps de jeu lancé (une minute de précision)."
    base = _json(JEUX, {}).get("temps", {})
    if not base:
        return "Aucun temps enregistré : playtime(\"start\") pour commencer."
    from datetime import timedelta

    limite = (date.today() - timedelta(days=int(days))).isoformat()
    lignes = []
    total = 0
    for jeu, jours in base.items():
        s = sum(v for d, v in jours.items() if d >= limite)
        if s:
            total += s
            lignes.append((s, f"- {jeu} : {s/3600:.1f} h"))
    lignes.sort(reverse=True)
    return f"Sur {days} jours : {total/3600:.1f} h de jeu.\n" + "\n".join(l for _, l in lignes)


_TILT = {"thread": None, "stop": threading.Event()}


def anti_tilt(minutes: int = 90, enable: bool = True) -> str:
    """Mode anti-tilt : après N minutes de jeu d'affilée, propose une pause à la voix (puis toutes les 30 min).

    Args:
        minutes: Durée avant la première suggestion de pause.
        enable: False pour arrêter.
    """
    if not enable:
        _TILT["stop"].set()
        return "Anti-tilt désactivé."
    if _TILT["thread"] and _TILT["thread"].is_alive():
        return "Déjà actif."
    _TILT["stop"].clear()

    def boucle():
        import psutil

        debut = None
        prochain = minutes * 60
        while not _TILT["stop"].is_set():
            actifs = {p.info["name"].lower() for p in psutil.process_iter(["name"]) if p.info.get("name")}
            if any(e in JEUX_EXE for e in actifs):
                debut = debut or time.time()
                if time.time() - debut >= prochain:
                    _prevenir("Ça fait un moment que tu joues, monsieur. Une pause de cinq minutes, de l'eau, et tu reviens plus frais.")
                    prochain += 30 * 60
            else:
                debut, prochain = None, minutes * 60
            _TILT["stop"].wait(60)

    _TILT["thread"] = threading.Thread(target=boucle, daemon=True)
    _TILT["thread"].start()
    return f"Anti-tilt actif : je te proposerai une pause après {minutes} minutes de jeu."


def analyze_gameplay(video_path: str, focus: str = "erreurs et moments clés") -> str:
    """Analyse une vidéo de partie : images clés, description de ce qui se passe, points à améliorer.

    Args:
        video_path: Chemin de la vidéo.
        focus: Ce que tu veux analyser (erreurs, positionnement, économie, timings…).
    """
    try:
        import tools

        return (tools.summarize_video(video_path)
                + f"\n\nAngle d'analyse demandé : {focus}. Regarde les images clés jointes et commente ce qui aurait pu être mieux joué.")
    except Exception as exc:  # noqa: BLE001
        return f"Impossible d'analyser la vidéo : {exc}"


_RPC = {"client": None}


def discord_presence(state: str = "", details: str = "", clear: bool = False) -> str:
    """Rich Presence Discord personnalisé (« Joue à … » avec ton texte). Demande DISCORD_APP_ID dans config.py.

    Args:
        state: Ligne d'état (ex. "En ranked").
        details: Détail (ex. "Valorant, 3 victoires").
        clear: True pour retirer la présence.
    """
    app_id = getattr(config, "DISCORD_APP_ID", "")
    if not app_id:
        return "Il manque DISCORD_APP_ID dans config.py : crée une application sur discord.com/developers/applications et copie son Application ID."
    try:
        from pypresence import Presence
    except Exception:  # noqa: BLE001
        return "Le paquet pypresence manque."
    try:
        if clear:
            if _RPC["client"]:
                _RPC["client"].clear()
                _RPC["client"].close()
                _RPC["client"] = None
            return "Présence Discord retirée."
        if _RPC["client"] is None:
            _RPC["client"] = Presence(str(app_id))
            _RPC["client"].connect()
        _RPC["client"].update(state=state or None, details=details or None, start=int(time.time()))
        return f"Présence Discord : « {details} — {state} »."
    except Exception as exc:  # noqa: BLE001
        return f"Discord ne répond pas (est-il ouvert ?) : {exc}"


def moderate_discord(action: str, guild_id: str = "", user_id: str = "", channel_id: str = "", message: str = "", reason: str = "") -> str:
    """Modération d'un serveur Discord via un bot (DISCORD_TOKEN) : envoyer un message, purger, expulser, bannir, mettre en sourdine, lister les membres.

    Args:
        action: "send", "purge", "kick", "ban", "timeout" ou "members".
        guild_id: Id du serveur.
        user_id: Id du membre (kick/ban/timeout).
        channel_id: Id du salon (send/purge).
        message: Texte à envoyer, nombre de messages à purger, ou minutes de timeout.
        reason: Motif.
    """
    token = getattr(config, "DISCORD_TOKEN", "")
    if not token:
        return "Il manque DISCORD_TOKEN dans config.py (token de bot, onglet Bot de ton application Discord, invité sur le serveur avec les droits de modération)."
    import requests

    h = {"Authorization": f"Bot {token}", "Content-Type": "application/json", "X-Audit-Log-Reason": reason or "Jarvis"}
    base = "https://discord.com/api/v10"
    try:
        if action == "send":
            r = requests.post(f"{base}/channels/{channel_id}/messages", headers=h, json={"content": message}, timeout=20)
        elif action == "purge":
            n = max(2, min(100, int(message or 10)))
            msgs = requests.get(f"{base}/channels/{channel_id}/messages", headers=h, params={"limit": n}, timeout=20).json()
            r = requests.post(f"{base}/channels/{channel_id}/messages/bulk-delete", headers=h, json={"messages": [m["id"] for m in msgs]}, timeout=20)
        elif action == "kick":
            r = requests.delete(f"{base}/guilds/{guild_id}/members/{user_id}", headers=h, timeout=20)
        elif action == "ban":
            r = requests.put(f"{base}/guilds/{guild_id}/bans/{user_id}", headers=h, json={"delete_message_seconds": 0}, timeout=20)
        elif action == "timeout":
            from datetime import timedelta, timezone

            fin = (datetime.now(timezone.utc) + timedelta(minutes=int(message or 10))).isoformat()
            r = requests.patch(f"{base}/guilds/{guild_id}/members/{user_id}", headers=h, json={"communication_disabled_until": fin}, timeout=20)
        elif action == "members":
            r = requests.get(f"{base}/guilds/{guild_id}/members", headers=h, params={"limit": 100}, timeout=20)
            if r.ok:
                return "\n".join(f"- {m['user']['username']} ({m['user']['id']})" for m in r.json()[:60])
        else:
            return "Action : send, purge, kick, ban, timeout ou members."
    except Exception as exc:  # noqa: BLE001
        return f"Erreur Discord : {exc}"
    return f"Discord : {action} {'fait' if r.ok else 'refusé (' + str(r.status_code) + ') ' + r.text[:120]}."


def plan_gaming_session(game: str, when: str, hour: str = "21:00", friends: str = "", send_to: str = "") -> str:
    """Planifie une session de jeu : événement dans l'agenda et message aux amis (Discord si un salon est donné).

    Args:
        game: Le jeu.
        when: Date AAAA-MM-JJ.
        hour: Heure HH:MM.
        friends: Noms des amis, séparés par des virgules.
        send_to: Id d'un salon Discord pour poster l'invitation (vide = pas de message).
    """
    import tools

    res = tools.add_event(f"Session {game}" + (f" avec {friends}" if friends else ""), when, hour)
    if send_to:
        res += " " + moderate_discord("send", channel_id=send_to,
                                      message=f"Session **{game}** le {when} à {hour}" + (f" — {friends}" if friends else "") + " : qui est chaud ?")
    return res


def install_game(game: str, platform: str = "steam", uninstall: bool = False) -> str:
    """Installe ou désinstalle un jeu via sa plateforme (Steam par id ou nom connu ; Epic ouvre la page du jeu).

    Args:
        game: Nom ou id du jeu.
        platform: "steam" ou "epic".
        uninstall: True pour désinstaller.
    """
    g = game.strip().lower()
    if platform == "steam":
        appid = int(g) if g.isdigit() else next((v for k, v in STEAM_IDS.items() if k in g), 0)
        if not appid:
            webbrowser.open("steam://open/games" if uninstall else f"steam://store/search/?term={game}")
            return "Page Steam ouverte : clique sur le jeu puis Installer (ou clic droit > Désinstaller). Je peux le faire à l'écran."
        webbrowser.open(f"steam://{'uninstall' if uninstall else 'install'}/{appid}")
        return f"Steam : {'désinstallation' if uninstall else 'installation'} de « {game} » demandée, confirme dans la fenêtre Steam."
    webbrowser.open("com.epicgames.launcher://apps" if uninstall else "com.epicgames.launcher://store/search?q=" + game)
    return "Epic ouvert : clique sur Obtenir / Installer (ou « … » > Désinstaller). Je peux cliquer à l'écran."


def sandbox_test(path: str, folder_readonly: str = "") -> str:
    """Teste un logiciel inconnu dans le bac à sable Windows (Windows Sandbox) : environnement jetable, rien ne touche ton PC.

    Args:
        path: Chemin de l'installeur ou du programme à tester.
        folder_readonly: Dossier supplémentaire à partager en lecture seule (vide = seulement le dossier du fichier).
    """
    if not IS_WINDOWS:
        return "Disponible seulement sous Windows."
    p = Path(path).expanduser()
    if not p.exists():
        return f"Introuvable : {p}"
    if not Path(r"C:\Windows\System32\WindowsSandbox.exe").exists():
        return ("Windows Sandbox n'est pas activé : windows_features(\"enable\", \"Containers-DisposableClientVM\") "
                "(boîte windows), puis redémarre.")
    dossiers = [p.parent] + ([Path(folder_readonly)] if folder_readonly else [])
    maps = "".join(f"<MappedFolder><HostFolder>{d}</HostFolder><SandboxFolder>C:\\test\\{i}</SandboxFolder><ReadOnly>true</ReadOnly></MappedFolder>"
                   for i, d in enumerate(dossiers))
    wsb = config.WORKSPACE / "test.wsb"
    wsb.parent.mkdir(parents=True, exist_ok=True)
    wsb.write_text(f"<Configuration><Networking>Disable</Networking><MappedFolders>{maps}</MappedFolders>"
                   f"<LogonCommand><Command>explorer.exe C:\\test\\0</Command></LogonCommand></Configuration>", encoding="utf-8")
    os.startfile(str(wsb))
    return (f"Bac à sable lancé sans réseau, avec {p.name} dans C:\\test\\0. Lance-le dedans, observe, puis ferme la fenêtre : "
            "tout est effacé. Je peux regarder l'écran et cliquer pour toi.")


TOOLS = [verify_game_files, fps_overlay, game_profile, optimize_graphics, playtime, anti_tilt, analyze_gameplay,
         discord_presence, moderate_discord, plan_gaming_session, install_game, sandbox_test]
