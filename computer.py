# Ia-local (Jarvis) — Copyright (c) 2026 Neexx (Nixovel) — https://github.com/Neex-off/Ia-local
# Créé par Neexx (Nixovel). Licence : voir LICENSE (paternité obligatoire, pas de vente ; s'applique aussi aux IA).
# Ne pas retirer cet en-tête.
"""Contrôle de l'écran, de la souris et du clavier pour l'agent (Windows).

- screenshot()   : capture d'un moniteur avec une grille de coordonnées, réduite pour le modèle.
- ui_elements()  : boutons, champs, liens… de la fenêtre active via l'accessibilité Windows (UIA),
                   avec leur position. Permet de cliquer par nom plutôt qu'aux pixels.
- click / type_text / press_keys / scroll / focus_window / list_windows.

Sécurité : pyautogui.FAILSAFE est actif : envoyer la souris dans le coin haut-gauche de l'écran
interrompt toute action en cours.
"""
from __future__ import annotations

import ctypes
import re
import sys

if sys.platform.startswith("win"):
    import ctypes.wintypes
import threading
import time
import unicodedata
from pathlib import Path

import config

SCREEN_MAX_W = 1280          # largeur max de l'image envoyée au modèle
GRID_STEP = 100              # pas de la grille (pixels écran)
SHOT_PATH = config.WORKSPACE / "ecran.png"

_last_elements: list[dict] = []

INTERESTING_TYPES = {"Button", "Edit", "Hyperlink", "CheckBox", "RadioButton", "ComboBox", "MenuItem",
                     "TabItem", "ListItem", "TreeItem", "SplitButton", "Slider", "Document", "Text"}


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s.lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", s).strip()


# ---------------------------------------------------------------------- écran

def screenshot(monitor: int = 1) -> tuple[Path, int, int]:
    """Capture le moniteur (1 = principal) avec une grille, écrit SHOT_PATH. Renvoie (chemin, largeur, hauteur) écran."""
    import mss
    from PIL import Image, ImageDraw

    with mss.MSS() as s:
        mons = s.monitors
        if monitor <= 0:  # auto : l'écran qui contient la fenêtre active
            monitor = _monitor_of_foreground(mons)
        monitor = max(1, min(monitor, len(mons) - 1))
        m = mons[monitor]
        shot = s.grab(m)
        img = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
    w, h = img.size
    scale = min(1.0, SCREEN_MAX_W / w)
    small = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)

    draw = ImageDraw.Draw(small)
    for x in range(0, w, GRID_STEP):
        sx = int(x * scale)
        draw.line([(sx, 0), (sx, small.height)], fill=(255, 0, 0), width=1)
        draw.text((sx + 2, 2), str(x + m["left"]), fill=(255, 40, 40))
    for y in range(0, h, GRID_STEP):
        sy = int(y * scale)
        draw.line([(0, sy), (small.width, sy)], fill=(255, 0, 0), width=1)
        draw.text((2, sy + 2), str(y + m["top"]), fill=(255, 40, 40))
    SHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
    small.save(SHOT_PATH)
    return SHOT_PATH, w, h


IS_WINDOWS = sys.platform.startswith("win")


def _monitor_of_foreground(mons: list[dict]) -> int:
    """Numéro du moniteur (1..n) contenant le centre de la fenêtre active, 1 par défaut."""
    if not IS_WINDOWS:
        return 1
    try:
        hwnd = ctypes.windll.user32.GetForegroundWindow()
        rect = ctypes.wintypes.RECT()
        ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect))
        cx, cy = (rect.left + rect.right) // 2, (rect.top + rect.bottom) // 2
        for i, m in enumerate(mons[1:], start=1):
            if m["left"] <= cx < m["left"] + m["width"] and m["top"] <= cy < m["top"] + m["height"]:
                return i
    except Exception:  # noqa: BLE001
        pass
    return 1


def _foreground_window():
    if not IS_WINDOWS:
        return None
    from pywinauto import Desktop

    hwnd = ctypes.windll.user32.GetForegroundWindow()
    if not hwnd:
        return None
    return Desktop(backend="uia").window(handle=hwnd)


def ui_elements(max_items: int = 60, timeout: float = 6.0) -> list[dict]:
    """Éléments interactifs visibles de la fenêtre active : [{name, type, x, y}]. Partiel si trop lent."""
    global _last_elements
    result: list[dict] = []

    def work():
        try:
            win = _foreground_window()
            if win is None:
                return
            seen = set()
            for el in win.descendants():
                try:
                    info = el.element_info
                    ctype = info.control_type
                    if ctype not in INTERESTING_TYPES:
                        continue
                    name = (info.name or "").strip()
                    if not name or len(name) > 80:
                        continue
                    if ctype == "Text" and len(name) < 3:
                        continue
                    r = info.rectangle
                    if r.width() <= 0 or r.height() <= 0 or r.width() > 1900:
                        continue
                    x, y = (r.left + r.right) // 2, (r.top + r.bottom) // 2
                    key = (name, ctype, x // 8, y // 8)
                    if key in seen:
                        continue
                    seen.add(key)
                    result.append({"name": name, "type": ctype, "x": x, "y": y})
                    if len(result) >= max_items * 3:
                        break
                except Exception:  # noqa: BLE001
                    continue
        except Exception:  # noqa: BLE001
            return

    t = threading.Thread(target=work, daemon=True)
    t.start()
    t.join(timeout)
    snapshot = list(result)
    snapshot.sort(key=lambda e: (e["type"] == "Text", e["y"], e["x"]))  # actionnables d'abord
    _last_elements = snapshot[:max_items]
    return _last_elements


def describe_screen(monitor: int = 0) -> tuple[Path, str]:
    """Capture + liste des éléments, prêt à envoyer au modèle. monitor 0 = écran de la fenêtre active."""
    path, w, h = screenshot(monitor)
    try:
        win = _foreground_window()
        title = win.window_text() if win else "?"
    except Exception:  # noqa: BLE001
        title = "?"
    els = ui_elements()
    lines = [f"Capture de l'écran où se trouve la fenêtre active ({w}x{h} pixels). Grille rouge = coordonnées écran (x, y). Fenêtre active : « {title} »."]
    if els:
        lines.append("Éléments de la fenêtre active (nom [type] -> x,y), utilisables avec click_element :")
        for e in els:
            lines.append(f"  - {e['name']} [{e['type']}] -> {e['x']},{e['y']}")
    else:
        lines.append("Aucun élément listé par l'accessibilité : utilise les coordonnées de la grille avec click(x, y).")
    return path, "\n".join(lines)


# ------------------------------------------------------------- souris/clavier

def _pag():
    import pyautogui

    pyautogui.FAILSAFE = True
    pyautogui.PAUSE = 0.05
    return pyautogui


def click(x: int, y: int, button: str = "left", double: bool = False) -> str:
    pag = _pag()
    x, y = int(x), int(y)
    pag.moveTo(x, y, duration=0.15)
    if double:
        pag.doubleClick(x, y, button=button)
    else:
        pag.click(x, y, button=button)
    return f"{'Double-clic' if double else 'Clic'} {button} en ({x}, {y})"


def move(x: int, y: int) -> str:
    pag = _pag()
    pag.moveTo(int(x), int(y), duration=0.2)
    return f"Souris en ({int(x)}, {int(y)})"


def drag(x1: int, y1: int, x2: int, y2: int, duration: float = 0.6) -> str:
    pag = _pag()
    pag.moveTo(int(x1), int(y1), duration=0.15)
    pag.mouseDown()
    pag.moveTo(int(x2), int(y2), duration=max(0.2, float(duration)))
    pag.mouseUp()
    return f"Glissé de ({int(x1)}, {int(y1)}) à ({int(x2)}, {int(y2)})"


ZOOM_PATH = config.WORKSPACE / "zoom.png"


def zoom(x: int, y: int, width: int = 600, height: int = 400) -> tuple[Path, str]:
    """Capture en pleine résolution d'une zone centrée sur (x, y), avec une grille fine, pour viser précisément."""
    import mss
    from PIL import Image, ImageDraw

    with mss.MSS() as s:
        mons = s.monitors
        mon = mons[_monitor_of_foreground(mons)] if len(mons) > 1 else mons[0]
        left = max(mon["left"], int(x) - width // 2)
        top = max(mon["top"], int(y) - height // 2)
        left = min(left, mon["left"] + mon["width"] - width)
        top = min(top, mon["top"] + mon["height"] - height)
        shot = s.grab({"left": left, "top": top, "width": width, "height": height})
        img = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
    draw = ImageDraw.Draw(img)
    step = 50
    for gx in range((step - (left % step)) % step, width, step):
        draw.line([(gx, 0), (gx, height)], fill=(255, 0, 0), width=1)
        draw.text((gx + 2, 2), str(left + gx), fill=(255, 40, 40))
    for gy in range((step - (top % step)) % step, height, step):
        draw.line([(0, gy), (width, gy)], fill=(255, 0, 0), width=1)
        draw.text((2, gy + 2), str(top + gy), fill=(255, 40, 40))
    img.save(ZOOM_PATH)
    return ZOOM_PATH, f"Loupe : zone écran de ({left}, {top}) à ({left + width}, {top + height}), grille rouge tous les 50 px en coordonnées écran réelles."


def find_element(name: str) -> dict | None:
    want = _norm(name)
    if not want:
        return None
    best, best_score = None, 0.0
    for e in _last_elements:
        n = _norm(e["name"])
        if n == want:
            return e
        if want in n or n in want:
            score = min(len(want), len(n)) / max(len(want), len(n))
        else:
            ww, nw = set(want.split()), set(n.split())
            score = len(ww & nw) / max(len(ww), 1) * 0.8
        if score > best_score:
            best, best_score = e, score
    return best if best_score >= 0.5 else None


def click_element(name: str, double: bool = False) -> str:
    e = find_element(name)
    if e is None:
        return f"Aucun élément nommé « {name} » dans la dernière capture. Refais see_screen ou utilise click(x, y)."
    msg = click(e["x"], e["y"], double=double)
    return f"{msg} sur « {e['name']} » [{e['type']}]"


def focused_is_password() -> bool:
    """Vrai si l'élément qui a le focus clavier est un champ de mot de passe (propriété UIA IsPassword, Windows)."""
    if not IS_WINDOWS:
        return False
    try:
        from pywinauto.uia_defines import IUIA

        el = IUIA().iuia.GetFocusedElement()
        return bool(el.CurrentIsPassword)
    except Exception:  # noqa: BLE001
        return False


def type_text(text: str, press_enter: bool = False) -> str:
    """Tape du texte (accents compris) via le presse-papiers + Ctrl+V.

    Si le champ actif est un champ de mot de passe, la réponse commence par « [[secret]] » pour que
    l'appelant masque le texte dans l'historique.
    """
    import pyperclip

    pag = _pag()
    secret = focused_is_password()
    old = None
    try:
        old = pyperclip.paste()
    except Exception:  # noqa: BLE001
        pass
    pyperclip.copy(text)
    time.sleep(0.05)
    pag.hotkey("ctrl", "v")
    time.sleep(0.15)
    if press_enter:
        pag.press("enter")
    try:
        pyperclip.copy(old if (old is not None and not secret) else "")  # jamais un mot de passe dans le presse-papiers
    except Exception:  # noqa: BLE001
        pass
    kind = "Mot de passe tapé (masqué)" if secret else f"Texte tapé ({len(text)} caractères)"
    return f"{'[[secret]]' if secret else ''}{kind}{' + Entrée' if press_enter else ''}"


_KEY_ALIASES = {
    "entree": "enter", "entrée": "enter", "retour": "enter", "echap": "esc", "échap": "esc", "escape": "esc",
    "espace": "space", "tabulation": "tab", "suppr": "delete", "supprimer": "delete", "effacer": "backspace",
    "control": "ctrl", "maj": "shift", "windows": "win", "haut": "up", "bas": "down", "gauche": "left",
    "droite": "right", "debut": "home", "début": "home", "fin": "end",
}


def press_keys(keys: str) -> str:
    """Appuie sur une touche ou un raccourci : "enter", "ctrl+s", "alt+tab", "win+d", "ctrl+shift+t"."""
    pag = _pag()
    parts = [p.strip().lower() for p in re.split(r"[+\s]+", keys) if p.strip()]
    parts = [_KEY_ALIASES.get(p, p) for p in parts]
    if not parts:
        return "Aucune touche indiquée."
    if len(parts) == 1:
        pag.press(parts[0])
    else:
        pag.hotkey(*parts)
    return f"Touches : {' + '.join(parts)}"


def scroll(amount: int, x: int | None = None, y: int | None = None) -> str:
    pag = _pag()
    if x is not None and y is not None:
        pag.moveTo(int(x), int(y), duration=0.1)
    pag.scroll(int(amount) * 120)
    return f"Défilement de {amount} crans ({'vers le haut' if amount > 0 else 'vers le bas'})"


def list_windows() -> list[str]:
    if not IS_WINDOWS:
        try:
            import pygetwindow  # type: ignore

            return [t for t in pygetwindow.getAllTitles() if t.strip()]
        except Exception:  # noqa: BLE001
            return []
    from pywinauto import Desktop

    titles = []
    for w in Desktop(backend="win32").windows():
        try:
            t = w.window_text().strip()
            if t and w.is_visible():
                titles.append(t)
        except Exception:  # noqa: BLE001
            continue
    return titles


def _force_foreground(hwnd: int) -> None:
    """Windows refuse souvent SetForegroundWindow : on simule une touche ALT puis on restaure la fenêtre."""
    u = ctypes.windll.user32
    u.keybd_event(0x12, 0, 0, 0)       # ALT enfoncé
    u.keybd_event(0x12, 0, 2, 0)       # ALT relâché
    u.ShowWindow(hwnd, 9)              # SW_RESTORE (si minimisée)
    u.SetForegroundWindow(hwnd)
    u.BringWindowToTop(hwnd)


def is_elevated(pid: int) -> bool | None:
    """Vrai si le processus tourne en administrateur (Windows). None si indéterminable."""
    if not IS_WINDOWS:
        return False
    try:
        import ctypes.wintypes as wt

        k, a = ctypes.windll.kernel32, ctypes.windll.advapi32
        h = k.OpenProcess(0x1000, False, int(pid))
        if not h:
            return None
        tok = wt.HANDLE()
        if not a.OpenProcessToken(h, 0x0008, ctypes.byref(tok)):
            return None
        elev, ret = wt.DWORD(), wt.DWORD()
        a.GetTokenInformation(tok, 20, ctypes.byref(elev), ctypes.sizeof(elev), ctypes.byref(ret))
        return bool(elev.value)
    except Exception:  # noqa: BLE001
        return None


def i_am_elevated() -> bool:
    if not IS_WINDOWS:
        return True
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:  # noqa: BLE001
        return False


ELEVATED_MSG = ("cette application tourne en ADMINISTRATEUR et Jarvis non : Windows bloque mes clics, mes touches et mes "
                "ordres de fermeture vers elle. Pour la piloter, relance Jarvis avec jarvis-admin.bat, ou lance l'application sans droits administrateur.")


def window_elevated_note(title: str) -> str:
    """Message à renvoyer au modèle si la fenêtre visée est élevée alors que Jarvis ne l'est pas ; sinon chaîne vide."""
    if i_am_elevated():
        return ""
    for w in windows_matching(title):
        try:
            if is_elevated(w.process_id()):
                return f"« {w.window_text()} » : {ELEVATED_MSG}"
        except Exception:  # noqa: BLE001
            continue
    return ""


def foreground_title() -> str:
    """Titre de la fenêtre actuellement au premier plan (Windows)."""
    if not IS_WINDOWS:
        return ""
    try:
        hwnd = ctypes.windll.user32.GetForegroundWindow()
        length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
        buf = ctypes.create_unicode_buffer(length + 1)
        ctypes.windll.user32.GetWindowTextW(hwnd, buf, length + 1)
        return buf.value
    except Exception:  # noqa: BLE001
        return ""


_GENERIC_WORDS = {"studio", "app", "launcher", "client", "desktop", "player", "gx", "browser", "pro", "free", "the", "le", "la"}


def _name_words(name: str) -> list[str]:
    """Mots significatifs d'un nom d'application : « OBS Studio » -> ["obs"] (+ "studio" en secours)."""
    words = [w for w in re.split(r"[^a-z0-9]+", _norm(name)) if len(w) >= 2]
    strong = [w for w in words if w not in _GENERIC_WORDS and len(w) >= 3]
    return strong or words


def processes_matching(name: str) -> list[tuple[int, str]]:
    """Processus dont l'exécutable ressemble au nom : « Opera GX » -> opera.exe, « OBS Studio » -> obs64.exe."""
    try:
        import psutil
    except ImportError:
        return []
    keys = _name_words(name)
    out = []
    for p in psutil.process_iter(["pid", "name"]):
        exe = (p.info.get("name") or "").lower()
        if exe and any(k in exe for k in keys):
            out.append((p.info["pid"], exe))
    return out


def windows_matching(title: str) -> list:
    """Fenêtres visibles correspondant à un nom d'application (objets pywinauto, Windows).

    Trois passes : le titre contient le nom tel quel (« Discord ») ; puis tous les mots du nom dans n'importe quel
    ordre (« Opera GX » -> « GX Corner – Opera ») ; puis les fenêtres du processus dont l'exécutable porte le nom
    (« OBS Studio » -> obs64.exe, dont la fenêtre s'appelle « OBS 32.0.2 - Profil… »)."""
    if not IS_WINDOWS:
        return []
    from pywinauto import Desktop

    want = _norm(title)
    if not want:
        return []
    wins = []
    for w in Desktop(backend="win32").windows():
        try:
            t = w.window_text()
            if t and w.is_visible():
                wins.append((w, _norm(t)))
        except Exception:  # noqa: BLE001
            continue
    out = [w for w, t in wins if want in t]
    if out:
        return out
    words = [w for w in re.split(r"[^a-z0-9]+", want) if len(w) >= 2]
    if len(words) > 1:
        out = [w for w, t in wins if all(re.search(r"\b" + re.escape(x) + r"\b", t) for x in words)]
        if out:
            return out
    pids = {pid for pid, _exe in processes_matching(title)}
    if pids:
        scored = []
        for w, t in wins:
            try:
                if w.process_id() in pids and t != "program manager":
                    # la vraie fenêtre d'abord : celle qui partage le plus de mots avec le nom, les overlays en dernier
                    score = sum(x in t for x in words) - (2 if "overlay" in t else 0)
                    scored.append((score, w))
            except Exception:  # noqa: BLE001
                continue
        out = [w for _s, w in sorted(scored, key=lambda x: -x[0])]
    return out


def close_window(title: str) -> tuple[list[str], list[int]]:
    """Ferme proprement (WM_CLOSE, comme la croix) toutes les fenêtres dont le titre contient `title`.
    Renvoie (titres fermés, pids concernés)."""
    closed, pids = [], []
    for w in windows_matching(title):
        try:
            pids.append(w.process_id())
            closed.append(w.window_text())
            w.close()
        except Exception:  # noqa: BLE001
            continue
    return closed, sorted(set(pids))


def focus_window(title: str) -> str:
    if not IS_WINDOWS:
        try:
            import pygetwindow  # type: ignore

            for w in pygetwindow.getWindowsWithTitle(title):
                w.activate()
                return f"Fenêtre au premier plan : « {w.title} »"
        except Exception:  # noqa: BLE001
            pass
        return f"Aucune fenêtre dont le titre contient « {title} » (ou fonction indisponible sur ce système)."
    from pywinauto import Desktop

    for w in windows_matching(title):
        try:
            t = w.window_text()
            hwnd = w.handle
            if w.is_minimized():
                w.restore()
            try:
                w.set_focus()
            except Exception:  # noqa: BLE001
                pass
            time.sleep(0.3)
            if ctypes.windll.user32.GetForegroundWindow() != hwnd:
                _force_foreground(hwnd)
                time.sleep(0.4)
            ok = ctypes.windll.user32.GetForegroundWindow() == hwnd
            return f"Fenêtre au premier plan : « {t} »" if ok else f"Fenêtre « {t} » trouvée mais Windows refuse de la mettre devant ; essaie press_keys(\"alt+tab\") ou clique dessus dans la barre des tâches."
        except Exception:  # noqa: BLE001
            continue
    return f"Aucune fenêtre ouverte dont le titre contient « {title} »."
