# Ia-local (Jarvis) — Copyright (c) 2026 Neexx (Nixovel) — https://github.com/Neex-off/Ia-local
# Créé par Neexx (Nixovel). Licence : voir LICENSE (paternité obligatoire, pas de vente ; s'applique aussi aux IA).
# Ne pas retirer cet en-tête.
"""Boîte à outils « automation » : macros (enregistrer / rejouer), expansion de texte, souris et clavier, emojis,
remplacer en masse dans des fichiers, sessions de travail, bureaux virtuels, historique du presse-papiers,
enregistrement d'écran, mode présentation, filtre lumière bleue, rouvrir la dernière fenêtre fermée.

Chargée à la demande par tools.open_toolbox("automation").
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

import config

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
IS_WINDOWS = sys.platform.startswith("win")
MEM = config.ROOT / "memoire"
MACROS = MEM / "macros.json"
SESSIONS = MEM / "sessions.json"
PRESSE = MEM / "presse_papiers.json"
EXPANSIONS = MEM / "expansions.json"
FERMES = MEM / "fermes.json"


def _json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return default


def _save(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


# --------------------------------------------------------------------------
# Macros
# --------------------------------------------------------------------------
_REC: dict = {"events": [], "t0": 0.0, "souris": None, "clavier": None, "nom": ""}


def record_macro(action: str = "start", name: str = "") -> str:
    """Enregistre une macro souris + clavier (start), l'arrête et la sauvegarde (stop), ou liste les macros (list).

    Args:
        action: "start", "stop" ou "list".
        name: Nom de la macro (pour start).
    """
    if action == "list":
        m = _json(MACROS, {})
        return "Macros : " + (", ".join(f"{k} ({len(v)} actions)" for k, v in m.items()) or "aucune")
    try:
        from pynput import keyboard, mouse
    except Exception:  # noqa: BLE001
        return "Le paquet pynput manque."
    if action == "start":
        if _REC["souris"]:
            return "Un enregistrement est déjà en cours."
        _REC.update({"events": [], "t0": time.time(), "nom": name or f"macro-{datetime.now():%H%M}"})

        def on_click(x, y, button, pressed):
            if pressed:
                _REC["events"].append({"t": time.time() - _REC["t0"], "type": "click", "x": x, "y": y, "button": button.name})

        def on_scroll(x, y, dx, dy):
            _REC["events"].append({"t": time.time() - _REC["t0"], "type": "scroll", "x": x, "y": y, "dy": dy})

        def on_press(key):
            k = getattr(key, "char", None) or getattr(key, "name", str(key))
            _REC["events"].append({"t": time.time() - _REC["t0"], "type": "key", "key": k})

        _REC["souris"] = mouse.Listener(on_click=on_click, on_scroll=on_scroll)
        _REC["clavier"] = keyboard.Listener(on_press=on_press)
        _REC["souris"].start()
        _REC["clavier"].start()
        return f"Enregistrement « {_REC['nom']} » lancé : fais les gestes, puis dis « stop macro »."
    if action == "stop":
        if not _REC["souris"]:
            return "Aucun enregistrement en cours."
        _REC["souris"].stop()
        _REC["clavier"].stop()
        _REC["souris"] = _REC["clavier"] = None
        m = _json(MACROS, {})
        evts = [e for e in _REC["events"] if not (e["type"] == "key" and e["key"] in ("cmd", "alt_l", "alt_r"))]
        m[_REC["nom"]] = evts
        _save(MACROS, m)
        return f"Macro « {_REC['nom']} » enregistrée : {len(evts)} actions. play_macro(\"{_REC['nom']}\") pour la rejouer."
    return "Action : start, stop ou list."


def play_macro(name: str, times: int = 1, speed: float = 1.0) -> str:
    """Rejoue une macro enregistrée.

    Args:
        name: Nom de la macro.
        times: Nombre de répétitions.
        speed: Vitesse (2.0 = deux fois plus vite).
    """
    m = _json(MACROS, {})
    evts = m.get(name)
    if not evts:
        return f"Macro inconnue : {name}. Macros : {', '.join(m) or 'aucune'}."
    import pyautogui

    pyautogui.FAILSAFE = True
    touches = {"space": "space", "enter": "enter", "backspace": "backspace", "tab": "tab", "ctrl_l": "ctrl",
               "ctrl_r": "ctrl", "shift": "shift", "shift_r": "shift", "esc": "esc"}
    for _ in range(max(1, int(times))):
        t_prec = 0.0
        for e in evts:
            time.sleep(max(0.0, (e["t"] - t_prec) / max(0.1, speed)))
            t_prec = e["t"]
            if e["type"] == "click":
                pyautogui.click(e["x"], e["y"], button=e.get("button", "left"))
            elif e["type"] == "scroll":
                pyautogui.scroll(int(e["dy"] * 120), e["x"], e["y"])
            elif e["type"] == "key":
                k = e["key"]
                if len(k) == 1:
                    pyautogui.write(k)
                else:
                    pyautogui.press(touches.get(k, k))
    return f"Macro « {name} » rejouée {times} fois."


# --------------------------------------------------------------------------
# Expansion de texte
# --------------------------------------------------------------------------
_EXP: dict = {"listener": None, "tampon": ""}


def text_expansion(action: str = "list", shortcut: str = "", text: str = "") -> str:
    """Expansion de texte : un raccourci tapé (ex. ";sig") est remplacé par un texte long. add/remove/list, start/stop l'écoute clavier.

    Args:
        action: "add", "remove", "list", "start" ou "stop".
        shortcut: Le raccourci (commence par ";" de préférence).
        text: Le texte complet (pour add).
    """
    base = _json(EXPANSIONS, {})
    if action == "add" and shortcut:
        base[shortcut] = text
        _save(EXPANSIONS, base)
        etat = "active" if _EXP["listener"] else "inactive : text_expansion(\"start\")"
        return f"« {shortcut} » -> « {text[:40]} ». L'écoute est {etat}."
    if action == "remove":
        base.pop(shortcut, None)
        _save(EXPANSIONS, base)
        return f"« {shortcut} » retiré."
    if action == "list":
        return "Raccourcis : " + (", ".join(f"{k} -> {v[:30]}" for k, v in base.items()) or "aucun")
    if action == "stop":
        if _EXP["listener"]:
            _EXP["listener"].stop()
            _EXP["listener"] = None
        return "Expansion de texte arrêtée."
    if action == "start":
        if _EXP["listener"]:
            return "Déjà active."
        try:
            from pynput import keyboard
        except Exception:  # noqa: BLE001
            return "Le paquet pynput manque."
        import pyautogui
        import pyperclip

        def on_press(key):
            c = getattr(key, "char", None)
            if c is None:
                if getattr(key, "name", "") in ("space", "enter", "tab"):
                    _EXP["tampon"] = ""
                return
            _EXP["tampon"] = (_EXP["tampon"] + c)[-40:]
            for k, v in _json(EXPANSIONS, {}).items():
                if _EXP["tampon"].endswith(k):
                    _EXP["tampon"] = ""
                    time.sleep(0.05)
                    pyautogui.press("backspace", presses=len(k))
                    old = pyperclip.paste()
                    pyperclip.copy(v)
                    pyautogui.hotkey("ctrl", "v")
                    time.sleep(0.1)
                    pyperclip.copy(old)
                    break

        _EXP["listener"] = keyboard.Listener(on_press=on_press)
        _EXP["listener"].start()
        return f"Expansion active pour {len(base)} raccourci(s)."
    return "Action : add, remove, list, start ou stop."


# --------------------------------------------------------------------------
# Souris, clavier, emojis
# --------------------------------------------------------------------------

def mouse_settings(speed: int = 0, acceleration: str = "") -> str:
    """Vitesse du pointeur Windows (1 à 20) et accélération (« précision du pointeur ») on/off.

    Args:
        speed: 1 à 20 (0 = ne change pas).
        acceleration: "on", "off" ou vide.
    """
    if not IS_WINDOWS:
        return "Disponible seulement sous Windows."
    import ctypes

    out = []
    if speed:
        ctypes.windll.user32.SystemParametersInfoW(0x0071, 0, max(1, min(20, int(speed))), 2)
        out.append(f"vitesse {speed}/20")
    if acceleration:
        vals = (ctypes.c_int * 3)(*((6, 10, 1) if acceleration == "on" else (0, 0, 0)))
        ctypes.windll.user32.SystemParametersInfoW(0x0004, 0, vals, 2)
        out.append(f"accélération {acceleration}")
    return "Souris : " + ", ".join(out) if out else "Rien demandé. Le DPI se règle dans le logiciel de la souris."


def keyboard_layout(layout: str = "") -> str:
    """Bascule la disposition clavier (vide = suivante, sinon "fr", "en", "de", "es", "it", "uk", "fr-ca").

    Args:
        layout: Code de la disposition voulue, ou vide pour passer à la suivante.
    """
    if not IS_WINDOWS:
        return "Disponible seulement sous Windows."
    import pyautogui

    if not layout:
        pyautogui.hotkey("win", "space")
        return "Disposition suivante."
    codes = {"fr": "0000040C", "en": "00000409", "en-us": "00000409", "uk": "00000809", "de": "00000407",
             "es": "0000040A", "it": "00000410", "fr-ca": "00001009"}
    code = codes.get(layout.lower())
    if not code:
        return f"Disposition inconnue. Choix : {', '.join(codes)}."
    import ctypes

    hkl = ctypes.windll.user32.LoadKeyboardLayoutW(code, 1)
    hwnd = ctypes.windll.user32.GetForegroundWindow()
    ctypes.windll.user32.PostMessageW(hwnd, 0x0050, 0, hkl)
    return f"Disposition « {layout} » activée pour la fenêtre active."


EMOJIS = {"sourire": "😊", "rire": "😂", "clin": "😉", "coeur": "❤️", "pouce": "👍", "feu": "🔥", "fusee": "🚀", "fete": "🎉",
          "triste": "😢", "colere": "😠", "surpris": "😮", "penser": "🤔", "ok": "👌", "applaudir": "👏", "priere": "🙏",
          "etoile": "⭐", "check": "✅", "croix": "❌", "attention": "⚠️", "idee": "💡", "cafe": "☕", "pizza": "🍕",
          "muscle": "💪", "jeu": "🎮", "musique": "🎵", "soleil": "☀️", "lune": "🌙", "eclair": "⚡", "argent": "💰",
          "flemme": "😴", "cool": "😎", "bisou": "😘", "hurler": "😱", "cent": "💯", "oeil": "👀", "fleche": "➡️",
          "copyright": "©", "marque": "™", "degre": "°", "euro": "€", "tiret": "—", "puce": "•", "infini": "∞"}


def type_emoji(name: str) -> str:
    """Tape un emoji ou un caractère spécial à la voix (« sourire », « feu », « coeur », « degré », « euro »…).

    Args:
        name: Nom de l'emoji ou du caractère.
    """
    import unicodedata

    n = "".join(c for c in unicodedata.normalize("NFD", name.strip().lower()) if unicodedata.category(c) != "Mn")
    e = EMOJIS.get(n) or next((v for k, v in EMOJIS.items() if k in n), None)
    if not e:
        return f"Emoji inconnu. Choix : {', '.join(EMOJIS)}."
    import pyautogui
    import pyperclip

    old = pyperclip.paste()
    pyperclip.copy(e)
    pyautogui.hotkey("ctrl", "v")
    time.sleep(0.1)
    pyperclip.copy(old)
    return f"{e} tapé."


def replace_in_files(folder: str, old: str, new: str, extensions: str = "", dry_run: bool = True, regex: bool = False) -> str:
    """Remplace un mot ou un motif dans tous les fichiers d'un dossier (copies .bak et annulation possible).

    Args:
        folder: Dossier.
        old: Texte (ou regex) à remplacer.
        new: Texte de remplacement.
        extensions: Extensions à traiter, ex. ".py,.md" (vide = fichiers texte courants).
        dry_run: True = seulement compter, False = remplacer vraiment.
        regex: Interpréter old comme une expression régulière.
    """
    p = Path(folder).expanduser()
    if not p.is_dir():
        return f"Dossier introuvable : {p}"
    exts = ({e.strip().lower() for e in extensions.split(",") if e.strip()}
            or {".txt", ".md", ".py", ".js", ".ts", ".html", ".css", ".json", ".csv", ".yaml", ".yml", ".toml", ".ini", ".cfg"})
    motif = re.compile(old if regex else re.escape(old))
    touches, total, sauvegardes = [], 0, []
    for f in p.rglob("*"):
        if f.suffix.lower() not in exts or any(part in (".git", "node_modules", ".venv") for part in f.parts):
            continue
        try:
            txt = f.read_text(encoding="utf-8")
        except Exception:  # noqa: BLE001
            continue
        n = len(motif.findall(txt))
        if not n:
            continue
        total += n
        touches.append(f"{f.relative_to(p)} ({n})")
        if not dry_run:
            bak = f.with_suffix(f.suffix + ".bak")
            shutil.copy(f, bak)
            sauvegardes.append((f, bak))
            f.write_text(motif.sub(new, txt), encoding="utf-8")
    if dry_run:
        return (f"{total} occurrence(s) dans {len(touches)} fichier(s) :\n" + "\n".join(touches[:30])
                + "\nRappelle avec dry_run=False pour remplacer.")
    if sauvegardes:
        import noyau

        def annuler():
            for f, bak in sauvegardes:
                shutil.move(bak, f)
            return f"{len(sauvegardes)} fichiers restaurés"

        noyau.register_undo(f"remplacement « {old} » -> « {new} » dans {p.name}", annuler)
    return f"{total} remplacement(s) dans {len(touches)} fichier(s) (copies .bak conservées, undo_last possible)."


# --------------------------------------------------------------------------
# Sessions, bureaux virtuels, presse-papiers, écran
# --------------------------------------------------------------------------

def save_session(name: str = "travail") -> str:
    """Sauvegarde la session de travail actuelle (applications qui ont une fenêtre visible) pour la rouvrir plus tard.

    Args:
        name: Nom de la session.
    """
    import psutil

    exes: dict[str, str] = {}
    for p in psutil.process_iter(["name", "exe"]):
        try:
            exe = p.info.get("exe") or ""
            nom = (p.info.get("name") or "").lower()
            if exe and "\\windows\\" not in exe.lower() and nom not in ("explorer.exe", "python.exe", "ollama.exe", "conhost.exe"):
                exes.setdefault(nom, exe)
        except Exception:  # noqa: BLE001
            continue
    visibles: dict[str, dict] = {}
    try:
        import pywinauto

        for w in pywinauto.Desktop(backend="uia").windows():
            try:
                nom = psutil.Process(w.process_id()).name().lower()
                if nom in exes and w.window_text().strip():
                    visibles[nom] = {"exe": exes[nom], "titre": w.window_text()[:80]}
            except Exception:  # noqa: BLE001
                continue
    except Exception:  # noqa: BLE001
        visibles = {n: {"exe": e, "titre": ""} for n, e in exes.items()}
    base = _json(SESSIONS, {})
    base[name] = list(visibles.values())
    _save(SESSIONS, base)
    return f"Session « {name} » enregistrée : {', '.join(Path(v['exe']).stem for v in visibles.values()) or 'rien'}."


def restore_session(name: str = "travail") -> str:
    """Rouvre une session de travail sauvegardée (relance les applications).

    Args:
        name: Nom de la session.
    """
    base = _json(SESSIONS, {})
    apps = base.get(name)
    if not apps:
        return f"Session inconnue : {name}. Sessions : {', '.join(base) or 'aucune'}."
    lances = []
    for a in apps:
        exe = a.get("exe", "")
        if exe and Path(exe).exists():
            try:
                subprocess.Popen([exe])
                lances.append(Path(exe).stem)
            except Exception:  # noqa: BLE001
                pass
    return f"Session « {name} » rouverte : {', '.join(lances) or 'rien à lancer'}."


def virtual_desktop(action: str = "next") -> str:
    """Bureaux virtuels Windows : nouveau (new), suivant (next), précédent (prev), fermer le courant (close), vue d'ensemble (overview).

    Args:
        action: new, next, prev, close ou overview.
    """
    if not IS_WINDOWS:
        return "Disponible seulement sous Windows."
    import pyautogui

    combos = {"new": ("win", "ctrl", "d"), "next": ("win", "ctrl", "right"), "prev": ("win", "ctrl", "left"),
              "close": ("win", "ctrl", "f4"), "overview": ("win", "tab")}
    c = combos.get(action)
    if not c:
        return "Action : new, next, prev, close ou overview."
    pyautogui.hotkey(*c)
    return {"new": "Nouveau bureau créé.", "next": "Bureau suivant.", "prev": "Bureau précédent.",
            "close": "Bureau fermé.", "overview": "Vue des bureaux ouverte."}[action]


_CLIP = {"thread": None, "stop": threading.Event()}


def clipboard_history(action: str = "list", index: int = 0) -> str:
    """Historique du presse-papiers tenu par Jarvis : start (surveille), list (les 20 derniers), get (remet le n-ième dans le presse-papiers), clear.

    Args:
        action: start, stop, list, get ou clear.
        index: Pour get : 1 = le plus récent.
    """
    if action == "start":
        if _CLIP["thread"] and _CLIP["thread"].is_alive():
            return "Déjà active."
        _CLIP["stop"].clear()

        def boucle():
            import pyperclip

            dernier = ""
            while not _CLIP["stop"].is_set():
                try:
                    t = pyperclip.paste()
                    if t and t != dernier and len(t) < 20000:
                        dernier = t
                        h = _json(PRESSE, [])
                        h.insert(0, {"t": datetime.now().isoformat(timespec="minutes"), "texte": t})
                        _save(PRESSE, h[:50])
                except Exception:  # noqa: BLE001
                    pass
                _CLIP["stop"].wait(1.0)

        _CLIP["thread"] = threading.Thread(target=boucle, daemon=True)
        _CLIP["thread"].start()
        return "Historique du presse-papiers actif (50 derniers textes). Win+V ouvre aussi celui de Windows."
    if action == "stop":
        _CLIP["stop"].set()
        return "Historique arrêté."
    h = _json(PRESSE, [])
    if action == "clear":
        _save(PRESSE, [])
        return "Historique vidé."
    if action == "get":
        if not h or index < 1 or index > len(h):
            return "Index hors limites."
        import pyperclip

        pyperclip.copy(h[index - 1]["texte"])
        return f"Élément {index} remis dans le presse-papiers : « {h[index - 1]['texte'][:60]} »."
    if not h:
        return "Historique vide (clipboard_history(\"start\") pour le remplir)."
    return "\n".join(f"{i}. [{e['t'][11:16]}] {e['texte'][:70].replace(chr(10), ' ')}" for i, e in enumerate(h[:20], start=1))


_REC_ECRAN: dict = {"proc": None, "fichier": None}


def screen_record(action: str = "start", monitor: int = 1, with_audio: bool = False) -> str:
    """Enregistrement de l'écran en vidéo : start / stop (ffmpeg si présent, sinon la Game Bar Win+Alt+R).

    Args:
        action: "start" ou "stop".
        monitor: Écran à enregistrer (ffmpeg).
        with_audio: Inclure le son du micro (ffmpeg).
    """
    ffmpeg = shutil.which("ffmpeg")
    if action == "stop":
        if _REC_ECRAN["proc"]:
            try:
                _REC_ECRAN["proc"].communicate(input=b"q", timeout=15)
            except Exception:  # noqa: BLE001
                _REC_ECRAN["proc"].kill()
            f = _REC_ECRAN["fichier"]
            _REC_ECRAN["proc"] = None
            return f"Enregistrement terminé : {f}"
        if IS_WINDOWS:
            import pyautogui

            pyautogui.hotkey("win", "alt", "r")
            return "Game Bar : enregistrement arrêté (vidéo dans Vidéos\\Captures)."
        return "Aucun enregistrement en cours."
    if _REC_ECRAN["proc"]:
        return "Un enregistrement est déjà en cours."
    if ffmpeg and IS_WINDOWS:
        import mss

        with mss.MSS() as s:
            m = s.monitors[max(1, min(int(monitor), len(s.monitors) - 1))]
        out = config.WORKSPACE / f"ecran-{datetime.now():%Y%m%d-%H%M%S}.mp4"
        out.parent.mkdir(parents=True, exist_ok=True)
        args = [ffmpeg, "-y", "-f", "gdigrab", "-framerate", "30", "-offset_x", str(m["left"]), "-offset_y", str(m["top"]),
                "-video_size", f"{m['width']}x{m['height']}", "-i", "desktop"]
        if with_audio:
            args += ["-f", "dshow", "-i", "audio=Microphone"]
        args += ["-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p", str(out)]
        _REC_ECRAN["proc"] = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                                              stderr=subprocess.DEVNULL, creationflags=NO_WINDOW)
        _REC_ECRAN["fichier"] = out
        return f"Enregistrement de l'écran {monitor} lancé ({out.name}). screen_record(\"stop\") pour finir."
    if IS_WINDOWS:
        import pyautogui

        pyautogui.hotkey("win", "alt", "r")
        return "Game Bar : enregistrement lancé (fenêtre active seulement). screen_record(\"stop\") pour finir."
    return "ffmpeg est nécessaire pour enregistrer l'écran."


def presentation_mode(enable: bool = True) -> str:
    """Mode présentation : masque les notifications, empêche la veille et l'écran de verrouillage (et l'inverse).

    Args:
        enable: True pour activer, False pour désactiver.
    """
    if not IS_WINDOWS:
        return "Disponible seulement sous Windows."
    exe = Path(r"C:\Windows\System32\PresentationSettings.exe")
    if exe.exists():
        subprocess.Popen([str(exe), "/start" if enable else "/stop"], creationflags=NO_WINDOW)
    try:
        import tools

        tools.do_not_disturb(bool(enable))
    except Exception:  # noqa: BLE001
        pass
    return "Mode présentation activé : plus de notifications ni de veille." if enable else "Mode présentation désactivé."


def night_light(enable: bool = True) -> str:
    """Filtre lumière bleue (Éclairage nocturne de Windows) : active ou désactive en cliquant dans les réglages.

    Args:
        enable: True pour activer, False pour désactiver.
    """
    if not IS_WINDOWS:
        return "Disponible seulement sous Windows."
    os.startfile("ms-settings:nightlight")
    time.sleep(1.5)
    try:
        import computer

        computer.ui_elements()
        for nom in (("Activer maintenant", "Turn on now") if enable else ("Désactiver maintenant", "Turn off now")):
            e = computer.find_element(nom)
            if e:
                computer.click(e["x"], e["y"])
                return f"Éclairage nocturne {'activé' if enable else 'désactivé'}."
        return f"Page Éclairage nocturne ouverte : clique sur « {'Activer' if enable else 'Désactiver'} maintenant » (je peux le faire avec see_screen)."
    except Exception as exc:  # noqa: BLE001
        return f"Page ouverte, mais je n'ai pas pu cliquer : {exc}"


def reopen_last_closed() -> str:
    """Rouvre la dernière application fermée par Jarvis (close_app)."""
    fermes = _json(FERMES, [])
    if not fermes:
        return "Je n'ai fermé aucune application récemment."
    d = fermes[-1]
    _save(FERMES, fermes[:-1])
    exe = d.get("exe", "")
    if exe and Path(exe).exists():
        subprocess.Popen([exe])
        return f"« {d.get('nom', Path(exe).stem)} » rouvert."
    import tools

    return tools.open_app(d.get("nom", ""))


TOOLS = [record_macro, play_macro, text_expansion, mouse_settings, keyboard_layout, type_emoji, replace_in_files,
         save_session, restore_session, virtual_desktop, clipboard_history, screen_record, presentation_mode,
         night_light, reopen_last_closed]

try:
    from outils_vision import TOOLS as _PLUS

    TOOLS += _PLUS
except Exception as _exc:  # noqa: BLE001
    print(f"[outils] vision indisponible : {_exc}")
