# Ia-local (Jarvis) — Copyright (c) 2026 Neexx (Nixovel) — https://github.com/Neex-off/Ia-local
# Créé par Neexx (Nixovel). Licence : voir LICENSE (paternité obligatoire, pas de vente ; s'applique aussi aux IA).
# Ne pas retirer cet en-tête.
"""Compléments de la boîte « automation » : export/import de la liste des logiciels, détection de présence par webcam
(avec verrouillage quand tu t'éloignes), recherche d'une capture d'écran par son contenu, contrôle par gestes.

Importé par outils_automation.py.
"""
from __future__ import annotations

import json
import subprocess
import sys
import threading
import time
from pathlib import Path

import config

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
IS_WINDOWS = sys.platform.startswith("win")
MEM = config.ROOT / "memoire"


def _json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return default


def _save(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _camera():
    import cv2

    return cv2.VideoCapture(0, cv2.CAP_DSHOW) if IS_WINDOWS else cv2.VideoCapture(0)


def software_list_export(action: str = "export", path: str = "") -> str:
    """Exporte la liste des logiciels installés (winget) dans un fichier, ou la réimporte pour tout réinstaller sur un nouveau PC.

    Args:
        action: "export" ou "import".
        path: Fichier JSON (vide = workspace/logiciels.json).
    """
    p = Path(path).expanduser() if path else config.WORKSPACE / "logiciels.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    if action == "export":
        r = subprocess.run(["winget", "export", "-o", str(p), "--accept-source-agreements"], capture_output=True, text=True, timeout=300,
                           encoding="utf-8", errors="replace", creationflags=NO_WINDOW)
        if not p.exists():
            return f"Échec : {(r.stderr or r.stdout)[-300:]}"
        try:
            n = len(json.loads(p.read_text(encoding="utf-8")).get("Sources", [{}])[0].get("Packages", []))
        except Exception:  # noqa: BLE001
            n = 0
        return f"{n} logiciels exportés dans {p} (software_list_export(\"import\", chemin) sur l'autre PC)."
    if not p.exists():
        return f"Introuvable : {p}"
    subprocess.Popen(["winget", "import", "-i", str(p), "--accept-source-agreements", "--accept-package-agreements", "--ignore-unavailable"], creationflags=NO_WINDOW)
    return f"Réinstallation lancée depuis {p} (winget travaille en arrière-plan, ça peut prendre longtemps)."


_PRESENCE: dict = {"thread": None, "stop": threading.Event(), "present": None, "absent_depuis": 0.0}


def webcam_presence(action: str = "start", lock_after_minutes: int = 0, check_every: int = 20) -> str:
    """Détection de présence par la webcam : sait si tu es devant le PC et peut verrouiller la session quand tu t'éloignes.

    Args:
        action: "start", "stop" ou "status".
        lock_after_minutes: Verrouiller après N minutes d'absence (0 = seulement détecter).
        check_every: Secondes entre deux vérifications.
    """
    if action == "stop":
        _PRESENCE["stop"].set()
        return "Détection de présence arrêtée."
    if action == "status":
        p = _PRESENCE["present"]
        if p is None:
            return "Présence : inconnue (détection pas démarrée)."
        return "Présence : tu es là." if p else f"Présence : absent depuis {int((time.time() - _PRESENCE['absent_depuis']) / 60)} min."
    try:
        import cv2
    except Exception:  # noqa: BLE001
        return "OpenCV manque."
    if _PRESENCE["thread"] and _PRESENCE["thread"].is_alive():
        return "Déjà active."
    _PRESENCE["stop"].clear()
    casc = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")

    def boucle():
        verrouille = False
        while not _PRESENCE["stop"].is_set():
            cap = _camera()
            vu = False
            if cap.isOpened():
                for _ in range(3):
                    ok, fr = cap.read()
                    if ok and len(casc.detectMultiScale(cv2.cvtColor(fr, cv2.COLOR_BGR2GRAY), 1.2, 5, minSize=(60, 60))):
                        vu = True
                        break
                cap.release()
            if vu:
                _PRESENCE["present"] = True
                verrouille = False
            else:
                if _PRESENCE["present"] is not False:
                    _PRESENCE["absent_depuis"] = time.time()
                _PRESENCE["present"] = False
                if lock_after_minutes and not verrouille and time.time() - _PRESENCE["absent_depuis"] >= lock_after_minutes * 60:
                    try:
                        import tools

                        tools.lock_session()
                    except Exception:  # noqa: BLE001
                        pass
                    verrouille = True
            _PRESENCE["stop"].wait(check_every)

    _PRESENCE["thread"] = threading.Thread(target=boucle, daemon=True)
    _PRESENCE["thread"].start()
    return "Détection de présence lancée" + (f" : verrouillage après {lock_after_minutes} min d'absence." if lock_after_minutes else ".")


def find_screenshot(query: str, folder: str = "", max_results: int = 8) -> str:
    """Retrouve une capture d'écran par son contenu (texte lu par OCR) dans le dossier des captures.

    Args:
        query: Mot ou phrase qui était visible sur la capture.
        folder: Dossier des captures (vide = Images/Captures d'écran, Vidéos/Captures, Images, workspace).
        max_results: Nombre max de résultats.
    """
    from outils_fichiers_plus import _ocr_image

    if folder:
        dossiers = [Path(folder).expanduser()]
    else:
        maison = Path.home()
        dossiers = [maison / "Pictures" / "Screenshots", maison / "Images" / "Captures d'écran", maison / "Videos" / "Captures",
                    maison / "Pictures", config.WORKSPACE]
    index = MEM / "index_captures.json"
    base = _json(index, {})
    fichiers = []
    for d in dossiers:
        if d.is_dir():
            fichiers += [f for f in d.glob("*") if f.suffix.lower() in (".png", ".jpg", ".jpeg")]
    fichiers = sorted(set(fichiers), key=lambda f: -f.stat().st_mtime)[:400]
    q = query.lower()
    hits = []
    for f in fichiers:
        cle = f"{f}|{int(f.stat().st_mtime)}"
        if cle not in base:
            base[cle] = _ocr_image(f).lower()
        if q in base[cle]:
            i = base[cle].index(q)
            extrait = base[cle][max(0, i - 40):i + 60].replace("\n", " ")
            hits.append(f"- {f} : …{extrait}…")
        if len(hits) >= max_results:
            break
    _save(index, base)
    if not hits:
        return f"Aucune capture ne contient « {query} » ({len(fichiers)} images lues)."
    return f"{len(hits)} capture(s) :\n" + "\n".join(hits) + "\nopen_file(chemin) pour l'ouvrir."


_GESTES: dict = {"thread": None, "stop": threading.Event()}


def hand_gestures(action: str = "start") -> str:
    """Contrôle par gestes de la main devant la webcam (mediapipe) : paume ouverte = lecture/pause, pouce levé = volume +, pouce baissé = volume −, poing = stop.

    Args:
        action: "start" ou "stop".
    """
    if action == "stop":
        _GESTES["stop"].set()
        return "Contrôle par gestes arrêté."
    try:
        import cv2
        import mediapipe as mp
    except Exception:  # noqa: BLE001
        return "Le contrôle par gestes demande le paquet mediapipe (pip install mediapipe) et OpenCV. Sans lui, la webcam sert déjà à la présence, la posture et le comptage."
    if _GESTES["thread"] and _GESTES["thread"].is_alive():
        return "Déjà actif."
    _GESTES["stop"].clear()

    def boucle():
        import tools

        mains = mp.solutions.hands.Hands(max_num_hands=1, min_detection_confidence=0.7)
        cap = _camera()
        dernier = ("", 0.0)
        while not _GESTES["stop"].is_set() and cap.isOpened():
            ok, fr = cap.read()
            if not ok:
                continue
            res = mains.process(cv2.cvtColor(fr, cv2.COLOR_BGR2RGB))
            if res.multi_hand_landmarks:
                lm = res.multi_hand_landmarks[0].landmark
                doigts = [lm[8].y < lm[6].y, lm[12].y < lm[10].y, lm[16].y < lm[14].y, lm[20].y < lm[18].y]
                pouce_haut = lm[4].y < lm[3].y < lm[2].y and not any(doigts)
                pouce_bas = lm[4].y > lm[3].y > lm[2].y and not any(doigts)
                if all(doigts):
                    geste = "paume"
                elif pouce_haut:
                    geste = "pouce_haut"
                elif pouce_bas:
                    geste = "pouce_bas"
                elif not any(doigts):
                    geste = "poing"
                else:
                    geste = ""
                if geste and (geste != dernier[0] or time.time() - dernier[1] > 2.0):
                    dernier = (geste, time.time())
                    try:
                        if geste == "paume":
                            tools.media_control("play_pause")
                        elif geste == "pouce_haut":
                            tools.change_volume(10)
                        elif geste == "pouce_bas":
                            tools.change_volume(-10)
                        else:
                            tools.media_control("stop")
                    except Exception:  # noqa: BLE001
                        pass
            time.sleep(0.15)
        cap.release()

    _GESTES["thread"] = threading.Thread(target=boucle, daemon=True)
    _GESTES["thread"].start()
    return "Contrôle par gestes actif : paume = lecture/pause, pouce haut/bas = volume, poing = stop."


TOOLS = [software_list_export, webcam_presence, find_screenshot, hand_gestures]
