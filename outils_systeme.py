# Ia-local (Jarvis) — Copyright (c) 2026 Neexx (Nixovel) — https://github.com/Neex-off/Ia-local
# Créé par Neexx (Nixovel). Licence : voir LICENSE (paternité obligatoire, pas de vente ; s'applique aussi aux IA).
# Ne pas retirer cet en-tête.
"""Boîte à outils « système » : processus, fenêtres, presse-papiers, écran, énergie.

Chargée à la demande par tools.open_toolbox("systeme"). Windows d'abord, repli propre ailleurs.
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes
import subprocess
import sys
import time
from pathlib import Path

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
IS_WINDOWS = sys.platform.startswith("win")


def _ps(command: str, timeout: float = 30) -> str:
    """Exécute une commande PowerShell et renvoie sa sortie (Windows)."""
    r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", command],
                       capture_output=True, text=True, timeout=timeout, encoding="utf-8",
                       errors="replace", creationflags=NO_WINDOW)
    return (r.stdout or "").strip() or (r.stderr or "").strip()


def _win_only(nom: str) -> str:
    return f"{nom} n'est disponible que sous Windows."


# --------------------------------------------------------------------------
# Processus
# --------------------------------------------------------------------------

def list_processes(filter: str = "", top: int = 15) -> str:
    """Liste les programmes en cours d'exécution avec leur mémoire et leur numéro (pid), les plus gourmands d'abord.

    Args:
        filter: Mot-clé pour ne garder que certains programmes (ex. "chrome"). Vide = tous.
        top: Nombre de lignes à renvoyer.
    """
    try:
        import psutil

        procs = []
        for p in psutil.process_iter(["pid", "name", "memory_info"]):
            nom = p.info.get("name") or ""
            if filter and filter.lower() not in nom.lower():
                continue
            mo = (p.info["memory_info"].rss / 2**20) if p.info.get("memory_info") else 0
            procs.append((mo, p.info["pid"], nom))
        procs.sort(reverse=True)
        if not procs:
            return f"Aucun programme ne correspond à « {filter} »."
        lignes = [f"{nom} (pid {pid}) : {mo:.0f} Mo" for mo, pid, nom in procs[:max(1, int(top))]]
        return f"{len(procs)} programme(s) :\n" + "\n".join(lignes)
    except Exception as exc:  # noqa: BLE001
        return f"Erreur : {exc}"


def kill_process(name_or_pid: str) -> str:
    """Arrête de force un programme par son nom ou son numéro (pid). À utiliser quand il ne répond plus.

    Args:
        name_or_pid: Nom du programme (ex. "obs64.exe") ou son pid.
    """
    try:
        import psutil

        cible = str(name_or_pid).strip()
        tues = []
        for p in psutil.process_iter(["pid", "name"]):
            nom = p.info.get("name") or ""
            vise = (p.info["pid"] == int(cible)) if cible.isdigit() else (cible.lower() in nom.lower())
            if vise:
                try:
                    p.kill()
                    tues.append(f"{nom} (pid {p.info['pid']})")
                except Exception:  # noqa: BLE001
                    continue
        time.sleep(0.8)
        return "Arrêté : " + ", ".join(tues) if tues else f"Aucun programme « {name_or_pid} » trouvé."
    except Exception as exc:  # noqa: BLE001
        return f"Erreur : {exc}"


# --------------------------------------------------------------------------
# Fenêtres
# --------------------------------------------------------------------------

def _hwnd(title: str):
    import computer

    wins = computer.windows_matching(title)
    return (wins[0].handle, wins[0].window_text()) if wins else (None, "")


def move_window(title: str, position: str = "gauche") -> str:
    """Place ou redimensionne une fenêtre : moitié gauche, moitié droite, plein écran, centre, réduite.

    Args:
        title: Une partie du titre de la fenêtre, ou le nom de l'application.
        position: "gauche", "droite", "haut", "bas", "plein", "centre", "reduite" ou "restaurer".
    """
    if not IS_WINDOWS:
        return _win_only("Le placement des fenêtres")
    try:
        h, nom = _hwnd(title)
        if not h:
            return f"Aucune fenêtre « {title} »."
        u = ctypes.windll.user32
        pos = (position or "gauche").strip().lower()
        if pos in ("reduite", "réduite", "minimiser"):
            u.ShowWindow(h, 6)
            return f"Fenêtre « {nom} » réduite."
        if pos in ("plein", "maximiser", "plein ecran", "plein écran"):
            u.ShowWindow(h, 3)
            return f"Fenêtre « {nom} » en plein écran."
        if pos in ("restaurer", "normal"):
            u.ShowWindow(h, 9)
            return f"Fenêtre « {nom} » restaurée."
        rect = ctypes.wintypes.RECT()
        u.SystemParametersInfoW(0x0030, 0, ctypes.byref(rect), 0)  # SPI_GETWORKAREA
        w, hgt = rect.right - rect.left, rect.bottom - rect.top
        cibles = {
            "gauche": (rect.left, rect.top, w // 2, hgt),
            "droite": (rect.left + w // 2, rect.top, w // 2, hgt),
            "haut": (rect.left, rect.top, w, hgt // 2),
            "bas": (rect.left, rect.top + hgt // 2, w, hgt // 2),
            "centre": (rect.left + w // 6, rect.top + hgt // 8, int(w / 1.5), int(hgt / 1.3)),
        }
        if pos not in cibles:
            return f"Position inconnue : {position}. Utilise gauche, droite, haut, bas, plein, centre ou reduite."
        u.ShowWindow(h, 9)
        x, y, cx, cy = cibles[pos]
        u.SetWindowPos(h, 0, x, y, cx, cy, 0x0040)
        return f"Fenêtre « {nom} » placée à « {pos} »."
    except Exception as exc:  # noqa: BLE001
        return f"Erreur : {exc}"


def pin_window(title: str, on_top: bool = True) -> str:
    """Épingle une fenêtre au-dessus de toutes les autres, ou la désépingle.

    Args:
        title: Une partie du titre de la fenêtre.
        on_top: True pour épingler, False pour désépingler.
    """
    if not IS_WINDOWS:
        return _win_only("L'épinglage de fenêtre")
    try:
        h, nom = _hwnd(title)
        if not h:
            return f"Aucune fenêtre « {title} »."
        ctypes.windll.user32.SetWindowPos(h, -1 if on_top else -2, 0, 0, 0, 0, 0x0001 | 0x0002)
        return f"Fenêtre « {nom} » {'épinglée au premier plan' if on_top else 'désépinglée'}."
    except Exception as exc:  # noqa: BLE001
        return f"Erreur : {exc}"


# --------------------------------------------------------------------------
# Presse-papiers
# --------------------------------------------------------------------------

def clipboard_read() -> str:
    """Lit le contenu du presse-papiers, c'est-à-dire ce que l'utilisateur vient de copier."""
    try:
        import pyperclip

        t = pyperclip.paste()
        return f"Presse-papiers ({len(t)} caractères) :\n{t[:4000]}" if t else "Le presse-papiers est vide."
    except Exception as exc:  # noqa: BLE001
        return f"Erreur : {exc}"


def clipboard_write(text: str) -> str:
    """Met un texte dans le presse-papiers pour que l'utilisateur puisse le coller où il veut.

    Args:
        text: Le texte à copier.
    """
    try:
        import pyperclip

        pyperclip.copy(text)
        return f"Copié dans le presse-papiers ({len(text)} caractères). Tu peux coller avec Ctrl+V."
    except Exception as exc:  # noqa: BLE001
        return f"Erreur : {exc}"


# --------------------------------------------------------------------------
# Écran, thème, bureau
# --------------------------------------------------------------------------

def set_brightness(level: int) -> str:
    """Règle la luminosité de l'écran (ordinateur portable ou écran compatible).

    Args:
        level: Pourcentage de 0 à 100.
    """
    if not IS_WINDOWS:
        return _win_only("La luminosité")
    n = max(0, min(100, int(level)))
    out = _ps(f"(Get-WmiObject -Namespace root/WMI -Class WmiMonitorBrightnessMethods).WmiSetBrightness(1,{n})")
    return f"Luminosité réglée à {n} %." if "xception" not in out else f"Écran non compatible : {out[:120]}"


def set_theme(mode: str = "sombre") -> str:
    """Passe Windows en thème clair ou sombre.

    Args:
        mode: "clair" ou "sombre".
    """
    if not IS_WINDOWS:
        return _win_only("Le thème Windows")
    clair = 1 if str(mode).lower().startswith("clair") else 0
    cle = "HKCU:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Themes\\Personalize"
    _ps(f"Set-ItemProperty -Path '{cle}' -Name AppsUseLightTheme -Value {clair}; "
        f"Set-ItemProperty -Path '{cle}' -Name SystemUsesLightTheme -Value {clair}")
    return f"Thème Windows passé en {'clair' if clair else 'sombre'}."


def set_wallpaper(path: str) -> str:
    """Change le fond d'écran du bureau.

    Args:
        path: Chemin complet d'une image (jpg, png).
    """
    if not IS_WINDOWS:
        return _win_only("Le fond d'écran")
    p = Path(str(path).strip('" ')).expanduser()
    if not p.is_file():
        return f"Image introuvable : {p}"
    ctypes.windll.user32.SystemParametersInfoW(20, 0, str(p), 3)
    return f"Fond d'écran changé : {p.name}"


def taskbar(hide: bool = True) -> str:
    """Masque ou réaffiche la barre des tâches (mode présentation, plein écran).

    Args:
        hide: True pour masquer, False pour réafficher.
    """
    if not IS_WINDOWS:
        return _win_only("La barre des tâches")
    try:
        u = ctypes.windll.user32
        h = u.FindWindowW("Shell_TrayWnd", None)
        u.ShowWindow(h, 0 if hide else 5)
        return "Barre des tâches masquée." if hide else "Barre des tâches réaffichée."
    except Exception as exc:  # noqa: BLE001
        return f"Erreur : {exc}"


def do_not_disturb(on: bool = True) -> str:
    """Active ou coupe le mode Ne pas déranger : les notifications ne s'affichent plus.

    Args:
        on: True pour activer le silence, False pour recevoir les notifications.
    """
    if not IS_WINDOWS:
        return _win_only("Le mode Ne pas déranger")
    val = 0 if on else 1
    cle = "HKCU:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\PushNotifications"
    _ps(f"New-Item -Path '{cle}' -Force | Out-Null; Set-ItemProperty -Path '{cle}' -Name ToastEnabled -Value {val}")
    return "Ne pas déranger activé : notifications coupées." if on else "Notifications réactivées."


# --------------------------------------------------------------------------
# Énergie et session
# --------------------------------------------------------------------------

def lock_session() -> str:
    """Verrouille la session Windows et affiche l'écran de connexion, sans rien fermer."""
    if not IS_WINDOWS:
        return _win_only("Le verrouillage")
    ctypes.windll.user32.LockWorkStation()
    return "Session verrouillée."


def sleep_pc() -> str:
    """Met l'ordinateur en veille immédiatement."""
    if not IS_WINDOWS:
        return _win_only("La mise en veille")
    subprocess.Popen(["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"], creationflags=NO_WINDOW)
    return "Mise en veille de l'ordinateur."


def shutdown_pc(action: str = "arret", minutes: int = 1) -> str:
    """Éteint ou redémarre l'ordinateur après un délai, ou annule un arrêt déjà programmé.

    Args:
        action: "arret", "redemarrage" ou "annuler".
        minutes: Délai avant l'action, en minutes. 1 par défaut, pour laisser le temps de se raviser.
    """
    if not IS_WINDOWS:
        return _win_only("L'arrêt de l'ordinateur")
    a = (action or "arret").lower()
    secondes = max(0, int(minutes) * 60)
    if a.startswith("annul"):
        subprocess.run(["shutdown", "/a"], capture_output=True, creationflags=NO_WINDOW)
        return "Arrêt programmé annulé."
    if a.startswith("redem") or a.startswith("redém"):
        subprocess.run(["shutdown", "/r", "/t", str(secondes)], capture_output=True, creationflags=NO_WINDOW)
        return f"Redémarrage dans {minutes} minute(s). Dis « annule l'arrêt » pour l'empêcher."
    subprocess.run(["shutdown", "/s", "/t", str(secondes)], capture_output=True, creationflags=NO_WINDOW)
    return f"Extinction dans {minutes} minute(s). Dis « annule l'arrêt » pour l'empêcher."


TOOLS = [list_processes, kill_process, move_window, pin_window, clipboard_read, clipboard_write,
         set_brightness, set_theme, set_wallpaper, taskbar, do_not_disturb,
         lock_session, sleep_pc, shutdown_pc]
