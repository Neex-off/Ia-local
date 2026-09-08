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

    want = _norm(title)
    for w in Desktop(backend="win32").windows():
        try:
            t = w.window_text()
            if t and want in _norm(t) and w.is_visible():
                if w.is_minimized():
                    w.restore()
                w.set_focus()
                return f"Fenêtre au premier plan : « {t} »"
        except Exception:  # noqa: BLE001
            continue
    return f"Aucune fenêtre dont le titre contient « {title} »."
