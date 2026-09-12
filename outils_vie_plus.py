# Ia-local (Jarvis) — Copyright (c) 2026 Neexx (Nixovel) — https://github.com/Neex-off/Ia-local
# Créé par Neexx (Nixovel). Licence : voir LICENSE (paternité obligatoire, pas de vente ; s'applique aussi aux IA).
# Ne pas retirer cet en-tête.
"""Compléments de la boîte « vie » : notes (Obsidian / Markdown), dates importantes, échéances administratives,
timeline de la journée, fitness (rappels d'activité, exercices de remplacement, posture et comptage par webcam,
photos de progression, décharge, échauffement, recettes, sommeil, code-barres, compléments), bien-être (lumière,
air), maison connectée (sonnette, fuite/fumée, présence), Android (APK, SMS), apprentissage (oral, langues,
plateformes, entretiens, quiz), quotidien (transports, véhicule, valise, horaires, films, widgets, Stream Deck,
autres machines, mode démo, easter eggs).

Importé par outils_vie.py.
"""
from __future__ import annotations

import json
import os
import random
import re
import shutil
import subprocess
import sys
import threading
import time
import webbrowser
from datetime import date, datetime, timedelta
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


def _prevenir(texte: str) -> None:
    try:
        import noyau

        if "dire" in noyau.hooks:
            noyau.hooks["dire"](texte)
    except Exception:  # noqa: BLE001
        pass
    try:
        import tools

        tools.notify("Jarvis", texte)
    except Exception:  # noqa: BLE001
        pass


def _ha(path: str, method: str = "GET", payload: dict | None = None):
    """Appel Home Assistant (HOME_ASSISTANT_URL / TOKEN). None si non configuré."""
    import requests

    url = getattr(config, "HOME_ASSISTANT_URL", "").rstrip("/")
    token = getattr(config, "HOME_ASSISTANT_TOKEN", "")
    if not url or not token:
        return None
    r = requests.request(method, f"{url}/api/{path}", headers={"Authorization": f"Bearer {token}"}, json=payload, timeout=15)
    if r.headers.get("content-type", "").startswith("application/json"):
        return r.json()
    return r.content


# --------------------------------------------------------------------------
# Notes, dates, échéances, timeline
# --------------------------------------------------------------------------

def notes(action: str = "daily", title: str = "", text: str = "", query: str = "") -> str:
    """Prise de notes Markdown (Obsidian ou dossier Notes) : note du jour (daily), créer (create), ajouter (append), chercher (search), ouvrir (open).

    Args:
        action: "daily", "create", "append", "search" ou "open".
        title: Titre de la note (create/append/open).
        text: Contenu à écrire.
        query: Mot à chercher (search).
    """
    vault = Path(getattr(config, "OBSIDIAN_VAULT", "") or Path.home() / "Documents" / "Notes").expanduser()
    vault.mkdir(parents=True, exist_ok=True)
    if action == "search":
        hits = []
        for f in vault.rglob("*.md"):
            try:
                t = f.read_text(encoding="utf-8", errors="replace")
            except Exception:  # noqa: BLE001
                continue
            if query.lower() in t.lower():
                i = t.lower().index(query.lower())
                extrait = t[max(0, i - 60):i + 80].replace("\n", " ")
                hits.append(f"- {f.relative_to(vault)} : …{extrait}…")
        return "\n".join(hits[:20]) or f"Rien pour « {query} »."
    if action == "daily":
        f = vault / f"{date.today():%Y-%m-%d}.md"
        if not f.exists():
            f.write_text(f"# {date.today():%A %d %B %Y}\n\n", encoding="utf-8")
        if text:
            with f.open("a", encoding="utf-8") as fh:
                fh.write(f"- {datetime.now():%H:%M} {text}\n")
        return f"Note du jour : {f}" + (" (ligne ajoutée)" if text else "\n" + f.read_text(encoding="utf-8")[-800:])
    nom = re.sub(r"[\\/:*?\"<>|]", "-", title).strip() or "sans-titre"
    f = vault / f"{nom}.md"
    if action == "create":
        f.write_text(f"# {title}\n\n{text}\n", encoding="utf-8")
        return f"Note créée : {f}"
    if action == "append":
        existe = f.exists()
        with f.open("a", encoding="utf-8") as fh:
            fh.write(("\n" if existe else f"# {title}\n\n") + text + "\n")
        return f"Ajouté à {f.name}."
    if action == "open":
        if not f.exists():
            return f"Note introuvable : {f}"
        if getattr(config, "OBSIDIAN_VAULT", ""):
            webbrowser.open(f"obsidian://open?path={f}")
        elif IS_WINDOWS:
            os.startfile(str(f))
        else:
            subprocess.Popen(["xdg-open", str(f)])
        return f"{f.name} ouverte."
    return "Action : daily, create, append, search ou open."


DATES = MEM / "dates.json"


def important_dates(action: str = "upcoming", name: str = "", when: str = "", kind: str = "anniversaire", remind_days: int = 3, days: int = 30) -> str:
    """Anniversaires et dates importantes : ajouter, retirer, lister, ou voir celles qui arrivent (avec l'âge pour un anniversaire).

    Args:
        action: "add", "remove", "list" ou "upcoming".
        name: Personne ou événement.
        when: Date AAAA-MM-JJ (l'année de naissance si connue).
        kind: "anniversaire", "fête", "mariage", "autre".
        remind_days: Jours de rappel avant.
        days: Fenêtre pour upcoming.
    """
    base = _json(DATES, [])
    if action == "add":
        base = [d for d in base if d["nom"].lower() != name.lower()]
        base.append({"nom": name, "date": when, "type": kind, "rappel_jours": int(remind_days)})
        _save(DATES, base)
        return f"{kind} de {name} le {when[5:]} enregistré."
    if action == "remove":
        base = [d for d in base if d["nom"].lower() != name.lower()]
        _save(DATES, base)
        return f"{name} retiré."
    if action == "list":
        return "\n".join(f"- {d['nom']} : {d['type']} le {d['date']}" for d in sorted(base, key=lambda x: x["date"][5:])) or "Aucune date."
    auj = date.today()
    prochains = []
    for d in base:
        try:
            m, j, annee = int(d["date"][5:7]), int(d["date"][8:10]), int(d["date"][:4])
        except Exception:  # noqa: BLE001
            continue
        cible = date(auj.year, m, j)
        if cible < auj:
            cible = date(auj.year + 1, m, j)
        dans = (cible - auj).days
        if dans <= days:
            age = f" ({cible.year - annee} ans)" if d["type"] == "anniversaire" and annee > 1900 else ""
            prochains.append((dans, f"- {d['nom']} : {d['type']} dans {dans} jour(s), le {cible:%d/%m}{age}"))
    prochains.sort()
    return "\n".join(t for _, t in prochains) or f"Rien dans les {days} prochains jours."


ECHEANCES = MEM / "echeances.json"


def admin_deadlines(action: str = "upcoming", name: str = "", when: str = "", recurrence: str = "annuel", days: int = 45) -> str:
    """Échéances administratives (impôts, assurance, contrôle technique, carte d'identité…) : ajouter, lister, retirer, prochaines. Les récurrentes se décalent seules.

    Args:
        action: "add", "remove", "list" ou "upcoming".
        name: Nom de l'échéance.
        when: Date AAAA-MM-JJ.
        recurrence: "annuel", "mensuel", "trimestriel", "aucune".
        days: Fenêtre pour upcoming.
    """
    base = _json(ECHEANCES, [])
    if action == "add":
        base = [e for e in base if e["nom"].lower() != name.lower()]
        base.append({"nom": name, "date": when, "recurrence": recurrence})
        _save(ECHEANCES, base)
        try:
            import tools

            tools.add_event(f"Échéance : {name}", when, "09:00")
        except Exception:  # noqa: BLE001
            pass
        return f"Échéance « {name} » le {when} ({recurrence}) enregistrée, avec un rappel dans l'agenda."
    if action == "remove":
        base = [e for e in base if e["nom"].lower() != name.lower()]
        _save(ECHEANCES, base)
        return f"« {name} » retirée."
    auj = date.today()
    change = False
    for e in base:
        try:
            d = date.fromisoformat(e["date"])
        except Exception:  # noqa: BLE001
            continue
        rec = e.get("recurrence", "aucune")
        while d < auj and rec != "aucune":
            if rec == "annuel":
                d = d.replace(year=d.year + 1)
            else:
                d = d + timedelta(days={"mensuel": 30, "trimestriel": 91}.get(rec, 365))
            e["date"] = d.isoformat()
            change = True
    if change:
        _save(ECHEANCES, base)
    if action == "list":
        return "\n".join(f"- {e['nom']} : {e['date']} ({e.get('recurrence', 'aucune')})" for e in sorted(base, key=lambda x: x["date"])) or "Aucune échéance."
    lignes = []
    for e in sorted(base, key=lambda x: x["date"]):
        try:
            n = (date.fromisoformat(e["date"]) - auj).days
        except Exception:  # noqa: BLE001
            continue
        if n <= days:
            lignes.append(f"- {e['nom']} : dans {n} jour(s), le {e['date']}")
    return "\n".join(lignes) or f"Rien dans les {days} prochains jours."


TIMELINE = MEM / "timeline.jsonl"
_TL: dict = {"thread": None, "stop": threading.Event()}


def day_timeline(action: str = "report", day: str = "") -> str:
    """Timeline locale de la journée (désactivable) : note toutes les 2 minutes l'application au premier plan, puis donne le temps par application.

    Args:
        action: "start", "stop", "report" ou "clear".
        day: Jour AAAA-MM-JJ pour report (vide = aujourd'hui).
    """
    if action == "start":
        if _TL["thread"] and _TL["thread"].is_alive():
            return "Déjà active."
        _TL["stop"].clear()

        def boucle():
            import psutil

            while not _TL["stop"].is_set():
                try:
                    import computer

                    w = computer._foreground_window()
                    if w:
                        nom = psutil.Process(w.process_id()).name()
                        MEM.mkdir(parents=True, exist_ok=True)
                        with TIMELINE.open("a", encoding="utf-8") as f:
                            f.write(json.dumps({"t": datetime.now().isoformat(timespec="minutes"), "app": nom,
                                                "titre": w.window_text()[:80]}, ensure_ascii=False) + "\n")
                except Exception:  # noqa: BLE001
                    pass
                _TL["stop"].wait(120)

        _TL["thread"] = threading.Thread(target=boucle, daemon=True)
        _TL["thread"].start()
        return "Timeline activée (une note toutes les 2 minutes, en local seulement). day_timeline(\"stop\") pour arrêter."
    if action == "stop":
        _TL["stop"].set()
        return "Timeline arrêtée."
    if action == "clear":
        TIMELINE.unlink(missing_ok=True)
        return "Timeline effacée."
    jour = day or date.today().isoformat()
    temps: dict[str, int] = {}
    titres: dict[str, set] = {}
    try:
        for l in TIMELINE.read_text(encoding="utf-8").splitlines():
            d = json.loads(l)
            if d["t"].startswith(jour):
                temps[d["app"]] = temps.get(d["app"], 0) + 2
                titres.setdefault(d["app"], set()).add(d["titre"][:40])
    except Exception:  # noqa: BLE001
        return "Aucune donnée (day_timeline(\"start\") pour commencer)."
    if not temps:
        return f"Rien pour le {jour}."
    return f"Journée du {jour} :\n" + "\n".join(f"- {a} : {m} min ({', '.join(list(titres[a])[:3])})" for a, m in sorted(temps.items(), key=lambda x: -x[1]))


# --------------------------------------------------------------------------
# Fitness et nutrition
# --------------------------------------------------------------------------
_ACT: dict = {"thread": None, "stop": threading.Event()}


def activity_reminder(enable: bool = True, every_minutes: int = 60) -> str:
    """Rappel d'activité : toutes les N minutes devant le PC, propose de se lever, marcher, boire.

    Args:
        enable: True pour activer, False pour arrêter.
        every_minutes: Intervalle.
    """
    if not enable:
        _ACT["stop"].set()
        return "Rappels d'activité arrêtés."
    if _ACT["thread"] and _ACT["thread"].is_alive():
        return "Déjà actif."
    _ACT["stop"].clear()
    phrases = ["On se lève deux minutes, monsieur : quelques pas et un verre d'eau.", "Petite marche ? Les jambes vous remercieront.",
               "Une minute debout, épaules en arrière, respirez.", "Cent pas dans le couloir et on reprend."]

    def boucle():
        while not _ACT["stop"].wait(every_minutes * 60):
            _prevenir(random.choice(phrases))

    _ACT["thread"] = threading.Thread(target=boucle, daemon=True)
    _ACT["thread"].start()
    return f"Rappel d'activité toutes les {every_minutes} minutes."


_REMPLACEMENTS = {
    "développé couché": ["développé haltères", "pompes lestées", "dips", "développé à la machine"],
    "squat": ["presse à cuisses", "goblet squat", "fentes", "squat bulgare", "hack squat"],
    "soulevé de terre": ["soulevé de terre roumain", "hip thrust", "good morning", "extension lombaire"],
    "développé militaire": ["développé haltères assis", "élévations latérales + arnold press", "landmine press"],
    "tractions": ["tirage vertical", "tractions assistées", "rowing haltère"],
    "rowing": ["tirage horizontal", "rowing haltère unilatéral", "rowing machine"],
    "curl": ["curl marteau", "curl incliné", "curl câble"],
    "extension triceps": ["dips", "barre au front", "extension câble corde"],
    "fentes": ["squat bulgare", "step-up", "presse unilatérale"],
    "hip thrust": ["pont fessier", "kickback câble", "soulevé de terre roumain"],
    "course": ["vélo", "rameur", "marche rapide en pente", "elliptique"],
}


def replacement_exercise(exercise: str, reason: str = "") -> str:
    """Propose des exercices de remplacement (matériel pris, douleur, fatigue) pour un mouvement donné.

    Args:
        exercise: L'exercice à remplacer.
        reason: Pourquoi (matériel occupé, épaule sensible, genou…).
    """
    e = exercise.lower()
    alts = next((v for k, v in _REMPLACEMENTS.items() if k in e or e in k), None)
    if not alts:
        return f"Je n'ai pas de table pour « {exercise} » : choisis un mouvement qui cible le même muscle avec une amplitude proche, et garde le même nombre de séries."
    note = ""
    r = reason.lower()
    if "épaule" in r or "epaule" in r:
        note = " Avec l'épaule sensible : prise neutre, amplitude réduite, pas de barre derrière la nuque."
    if "genou" in r:
        note = " Avec le genou sensible : évite les flexions profondes, privilégie presse à faible amplitude et hip thrust."
    if "dos" in r or "lombaire" in r:
        note = " Dos sensible : évite les charges axiales, préfère machines et unilatéral."
    return f"À la place de {exercise} : " + ", ".join(alts) + "." + note + " Même volume, charge un peu plus légère la première fois."


def _webcam_frames(seconds: float, fps: int = 10):
    import cv2

    cap = cv2.VideoCapture(0, cv2.CAP_DSHOW) if IS_WINDOWS else cv2.VideoCapture(0)
    if not cap.isOpened():
        return None
    frames = []
    fin = time.time() + seconds
    while time.time() < fin:
        ok, frame = cap.read()
        if ok:
            frames.append(frame)
        time.sleep(1.0 / fps)
    cap.release()
    return frames


def posture_check(seconds: int = 4) -> str:
    """Analyse de posture via la webcam : distance à l'écran, tête penchée, position dans le cadre (rien n'est enregistré).

    Args:
        seconds: Durée d'observation.
    """
    try:
        import cv2
    except Exception:  # noqa: BLE001
        return "OpenCV manque (pip install opencv-python-headless)."
    frames = _webcam_frames(seconds)
    if not frames:
        return "Webcam introuvable ou occupée."
    casc = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    yeux = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_eye.xml")
    mesures = []
    for fr in frames[::3]:
        g = cv2.cvtColor(fr, cv2.COLOR_BGR2GRAY)
        faces = casc.detectMultiScale(g, 1.2, 5, minSize=(80, 80))
        if len(faces):
            x, y, w, h = max(faces, key=lambda f: f[2] * f[3])
            ey = yeux.detectMultiScale(g[y:y + h // 2, x:x + w], 1.1, 5)
            incl = 0.0
            if len(ey) >= 2:
                (x1, y1, _w1, _h1), (x2, y2, _w2, _h2) = sorted(ey[:2], key=lambda e: e[0])
                incl = (y2 - y1) / max(1, x2 - x1)
            mesures.append((h / fr.shape[0], (x + w / 2) / fr.shape[1], (y + h / 2) / fr.shape[0], incl))
    if not mesures:
        return "Je ne vois pas de visage : rapproche-toi ou allume la lumière."
    h, cx, cy, incl = [sum(m[i] for m in mesures) / len(mesures) for i in range(4)]
    conseils = []
    if h > 0.55:
        conseils.append("tu es très près de l'écran : recule d'une vingtaine de centimètres")
    elif h < 0.2:
        conseils.append("tu es loin de l'écran ou affalé en arrière")
    if abs(incl) > 0.12:
        conseils.append("tête penchée sur le côté : redresse la nuque")
    if cy > 0.62:
        conseils.append("tête basse dans le cadre : tu es probablement voûté, redresse le dos et monte l'écran")
    if abs(cx - 0.5) > 0.22:
        conseils.append("tu es décalé par rapport à l'écran : recentre la chaise")
    return "Posture correcte, continue comme ça." if not conseils else "Posture : " + " ; ".join(conseils) + "."


def count_reps(seconds: int = 45, exercise: str = "") -> str:
    """Compte les répétitions d'un exercice devant la webcam (mouvement répétitif : squats, pompes, curls…) pendant N secondes.

    Args:
        seconds: Durée du comptage.
        exercise: Nom de l'exercice (pour le journal).
    """
    try:
        import cv2
        import numpy as np
    except Exception:  # noqa: BLE001
        return "OpenCV manque."
    _prevenir("Je compte : c'est parti.")
    frames = _webcam_frames(seconds, fps=12)
    if not frames or len(frames) < 20:
        return "Webcam introuvable."
    petit = [cv2.resize(cv2.cvtColor(f, cv2.COLOR_BGR2GRAY), (160, 120)).astype("float32") for f in frames]
    centres: list[float] = []
    for a, b in zip(petit, petit[1:]):
        masque = np.abs(a - b) > 25
        ys = np.where(masque)[0]
        centres.append(float(ys.mean()) if len(ys) > 30 else (centres[-1] if centres else 60.0))
    sig = np.convolve(np.array(centres), np.ones(5) / 5, mode="same")
    sig = sig - sig.mean()
    seuil = max(4.0, float(np.std(sig)) * 0.6)
    reps, etat, dernier = 0, 0, -100
    for i, v in enumerate(sig):
        if etat == 0 and v > seuil:
            etat = 1
        elif etat == 1 and v < -seuil:
            if i - dernier > 6:
                reps += 1
                dernier = i
            etat = 0
    _prevenir(f"{reps} répétitions.")
    if exercise and reps:
        try:
            import tools

            tools.journal_add("sport", f"{exercise} : {reps} répétitions comptées à la webcam")
        except Exception:  # noqa: BLE001
            pass
    return (f"{reps} répétition(s) comptée(s) en {seconds} s" + (f" ({exercise})" if exercise else "")
            + ". Pour plus de précision : cadre entier, fond fixe, une seule personne.")


PROGRESSION = MEM / "progression"


def progress_photos(action: str = "compare", path: str = "", when: str = "") -> str:
    """Photos de progression : ajoute une photo datée, ou compare la première et la dernière côte à côte (ou deux dates).

    Args:
        action: "add", "list" ou "compare".
        path: Photo à ajouter (add).
        when: Pour compare : "AAAA-MM-JJ,AAAA-MM-JJ" (vide = première et dernière) ; pour add : la date de la photo.
    """
    PROGRESSION.mkdir(parents=True, exist_ok=True)
    photos = sorted(list(PROGRESSION.glob("*.jpg")) + list(PROGRESSION.glob("*.png")))
    if action == "add":
        p = Path(path).expanduser()
        if not p.exists():
            return f"Introuvable : {p}"
        dest = PROGRESSION / f"{when or date.today().isoformat()}{p.suffix.lower()}"
        shutil.copy(p, dest)
        return f"Photo enregistrée : {dest.name} ({len(photos) + 1} au total)."
    if action == "list":
        return "Photos : " + (", ".join(p.stem for p in photos) or "aucune")
    if len(photos) < 2:
        return "Il faut au moins deux photos (progress_photos(\"add\", chemin))."
    from PIL import Image, ImageDraw

    if when and "," in when:
        a, b = when.split(",")
        pa = next((p for p in photos if p.stem == a.strip()), photos[0])
        pb = next((p for p in photos if p.stem == b.strip()), photos[-1])
    else:
        pa, pb = photos[0], photos[-1]
    ia, ib = Image.open(pa).convert("RGB"), Image.open(pb).convert("RGB")
    h = 900
    ia = ia.resize((int(ia.width * h / ia.height), h))
    ib = ib.resize((int(ib.width * h / ib.height), h))
    out = Image.new("RGB", (ia.width + ib.width + 30, h + 60), (20, 20, 20))
    out.paste(ia, (10, 50))
    out.paste(ib, (ia.width + 20, 50))
    d = ImageDraw.Draw(out)
    d.text((14, 14), pa.stem, fill=(255, 255, 255))
    d.text((ia.width + 24, 14), pb.stem, fill=(255, 255, 255))
    f = config.WORKSPACE / "progression-compare.png"
    f.parent.mkdir(parents=True, exist_ok=True)
    out.save(f)
    try:
        jours = (date.fromisoformat(pb.stem[:10]) - date.fromisoformat(pa.stem[:10])).days
    except Exception:  # noqa: BLE001
        jours = 0
    return f"[[image:{f}]]\nComparaison {pa.stem} -> {pb.stem} ({jours} jours). Décris les changements visibles avec tact."


def deload_suggestion() -> str:
    """Suggestion de semaine de décharge d'après l'historique : semaines consécutives d'entraînement, mentions de fatigue ou de douleur."""
    try:
        from outils_vie import _toutes_seances

        seances = _toutes_seances()
    except Exception:  # noqa: BLE001
        seances = []
    if not seances:
        return "Pas assez d'historique : note tes séances (log_set / journal_add) et je pourrai juger."
    semaines: dict[int, int] = {}
    fatigue = 0
    for s in seances[-80:]:
        try:
            d = datetime.fromisoformat(str(s.get("date") or s.get("t"))[:19]).date()
        except Exception:  # noqa: BLE001
            continue
        k = d.isocalendar()[1]
        semaines[k] = semaines.get(k, 0) + 1
        txt = json.dumps(s, ensure_ascii=False).lower()
        if any(m in txt for m in ("fatigu", "douleur", "mal ", "courbature", "épuis", "crev", "dur ")):
            fatigue += 1
    sem = sorted(semaines)
    consecutives = 0
    for i in range(len(sem) - 1, -1, -1):
        if semaines[sem[i]] >= 2 and (i == len(sem) - 1 or sem[i + 1] - sem[i] == 1):
            consecutives += 1
        else:
            break
    if consecutives >= 6 or fatigue >= 3:
        return (f"Décharge conseillée : {consecutives} semaines d'affilée à 2+ séances, {fatigue} mentions de fatigue ou douleur. "
                "Pendant 7 jours : mêmes exercices, 50 à 60 % des charges, moitié des séries, pas d'échec. Le sommeil compte double cette semaine.")
    return (f"Pas besoin de décharge pour l'instant ({consecutives} semaines consécutives, {fatigue} signes de fatigue). "
            "Reviens vers 6 à 8 semaines ou dès que les charges stagnent avec de la fatigue.")


_ECHAUFFEMENTS = {
    "jambes": ["5 min vélo ou marche rapide", "10 squats au poids du corps lents", "10 fentes marchées", "ouverture de hanches 30 s / côté", "2 séries légères de l'exercice principal"],
    "pectoraux": ["rotations d'épaules 20", "band pull-apart 15", "pompes 10", "2 séries légères montantes du développé"],
    "dos": ["dead hang 30 s", "band pull-apart 15", "tirage léger 15", "cat-camel 10"],
    "épaules": ["rotations externes élastique 15 / côté", "face pull léger 15", "élévations latérales très légères 15", "2 séries montantes"],
    "bras": ["rotations poignets", "curl et extension très légers 15", "1 série montante"],
    "course": ["marche 3 min", "montées de genoux 20 m", "talons-fesses 20 m", "foulées bondissantes 2×20 m", "3 accélérations progressives"],
}
_ETIREMENTS = {
    "jambes": ["quadriceps debout 30 s / côté", "ischio-jambiers assis 30 s", "fessiers (pigeon) 30 s / côté", "mollets contre un mur 30 s"],
    "pectoraux": ["pectoraux dans l'encadrement d'une porte 30 s", "posture de l'enfant 40 s"],
    "dos": ["posture de l'enfant 40 s", "rotation allongée 30 s / côté", "suspension 30 s"],
    "épaules": ["bras croisé devant 30 s / côté", "triceps derrière la tête 30 s / côté"],
    "bras": ["fléchisseurs paume vers le haut 30 s", "extenseurs 30 s"],
    "course": ["mollets 30 s", "ischios 30 s", "fléchisseurs de hanche 30 s / côté"],
}


def warmup_routine(muscles: str = "jambes", minutes: int = 8, stretch: bool = False) -> str:
    """Échauffement (ou étirements de fin) adapté aux muscles du jour.

    Args:
        muscles: jambes, pectoraux, dos, épaules, bras, course (plusieurs séparés par des virgules).
        minutes: Durée visée.
        stretch: True pour les étirements de fin de séance à la place.
    """
    table = _ETIREMENTS if stretch else _ECHAUFFEMENTS
    lignes = []
    for g in [g.strip().lower() for g in muscles.split(",")]:
        cle = next((k for k in table if k.startswith(g[:4])), None)
        if cle:
            lignes += [f"- {x}" for x in table[cle]]
    if not lignes:
        return f"Groupes connus : {', '.join(table)}."
    return (f"{'Étirements' if stretch else 'Échauffement'} ({minutes} min) pour {muscles} :\n" + "\n".join(lignes)
            + ("\nRespire lentement, jamais de douleur vive." if stretch else "\nMonte progressivement, sans aller à l'échec."))


_RECETTES = [
    ("Poulet riz brocoli", 45, "poulet, riz, brocoli, sauce soja", 20),
    ("Omelette 4 œufs fromage", 32, "œufs, fromage, épinards", 8),
    ("Bowl thon quinoa", 38, "thon en boîte, quinoa, maïs, avocat", 15),
    ("Skyr granola fruits", 25, "skyr, granola, banane, myrtilles", 3),
    ("Pâtes au bœuf haché", 42, "bœuf 5 %, pâtes, tomates, oignon", 20),
    ("Wrap dinde", 30, "tortilla, blanc de dinde, salade, fromage frais", 5),
    ("Saumon patate douce", 36, "saumon, patate douce, haricots verts", 25),
    ("Lentilles corail curry", 24, "lentilles corail, lait de coco, curry, riz", 25),
    ("Tofu sauté", 28, "tofu ferme, légumes, sauce soja, riz", 15),
    ("Crêpes protéinées", 30, "flocons d'avoine, œufs, fromage blanc, banane", 10),
    ("Chili con carne", 40, "bœuf haché, haricots rouges, tomates, épices", 35),
    ("Cottage cheese et fruits", 26, "cottage cheese, pêche, amandes", 2),
]


def protein_recipes(protein_min: int = 30, ingredients: str = "", max_minutes: int = 60) -> str:
    """Recettes riches en protéines, filtrées par protéines minimum, ingrédients disponibles et temps.

    Args:
        protein_min: Grammes de protéines minimum par portion.
        ingredients: Ingrédients que tu as (séparés par des virgules) ; vide = toutes.
        max_minutes: Temps de préparation max.
    """
    dispo = [i.strip().lower() for i in ingredients.split(",") if i.strip()]
    out = []
    for nom, prot, ing, mn in _RECETTES:
        if prot < protein_min or mn > max_minutes:
            continue
        if dispo and not any(d in ing for d in dispo):
            continue
        out.append(f"- {nom} : {prot} g de protéines, {mn} min ({ing})")
    return "\n".join(out) or "Rien avec ces critères : baisse protein_min ou change d'ingrédients. Je peux aussi chercher sur le web."


SOMMEIL = MEM / "sommeil.json"


def sleep_tracking(action: str = "report", hours: float = 0, quality: int = 0, import_path: str = "", days: int = 14) -> str:
    """Suivi du sommeil : saisie manuelle (log), import d'un export de montre (CSV Garmin / Fitbit / Google Fit / Samsung Health), bilan (report).

    Args:
        action: "log", "import" ou "report".
        hours: Heures dormies (log).
        quality: Qualité 1 à 5 (log).
        import_path: Fichier CSV exporté par l'application de la montre (import).
        days: Période du bilan.
    """
    base = _json(SOMMEIL, [])
    if action == "log":
        base = [b for b in base if b["date"] != date.today().isoformat()]
        base.append({"date": date.today().isoformat(), "heures": float(hours), "qualite": int(quality)})
        _save(SOMMEIL, base)
        return f"Nuit notée : {hours} h, qualité {quality}/5."
    if action == "import":
        import csv

        p = Path(import_path).expanduser()
        if not p.exists():
            return f"Introuvable : {p}"
        n = 0
        with p.open(encoding="utf-8", errors="replace", newline="") as f:
            for row in csv.DictReader(f):
                cles = {k.lower(): v for k, v in row.items() if k}
                d = next((v for k, v in cles.items() if "date" in k or "day" in k or "start" in k), "")
                dur = next((v for k, v in cles.items() if "duration" in k or "durée" in k or "asleep" in k or ("sleep" in k and "min" in k)), "")
                if not d or not dur:
                    continue
                try:
                    m = float(re.sub(r"[^\d.]", "", str(dur)))
                    heures = m / 60 if m > 24 else m
                    dj = str(d)[:10].replace("/", "-")
                    base = [b for b in base if b["date"] != dj]
                    base.append({"date": dj, "heures": round(heures, 2), "qualite": 0})
                    n += 1
                except Exception:  # noqa: BLE001
                    continue
        _save(SOMMEIL, sorted(base, key=lambda x: x["date"]))
        return f"{n} nuits importées."
    limite = (date.today() - timedelta(days=days)).isoformat()
    nuits = [b for b in base if b["date"] >= limite]
    if not nuits:
        return "Aucune nuit enregistrée sur la période (sleep_tracking(\"log\", hours=7.5, quality=4))."
    moy = sum(b["heures"] for b in nuits) / len(nuits)
    courtes = [b["date"] for b in nuits if b["heures"] < 6.5]
    q = [b["qualite"] for b in nuits if b.get("qualite")]
    return (f"Sur {days} jours : {len(nuits)} nuits, {moy:.1f} h en moyenne" + (f", qualité {sum(q)/len(q):.1f}/5" if q else "")
            + (f". Nuits courtes : {', '.join(courtes)}" if courtes else ". Aucune nuit sous 6 h 30") + ".")


def barcode_food(barcode: str = "", scan: bool = False) -> str:
    """Scanne un code-barres alimentaire (webcam) ou prend un numéro EAN, et donne nutrition et Nutri-Score via Open Food Facts.

    Args:
        barcode: Le numéro EAN (vide avec scan=True pour lire à la webcam).
        scan: True pour lire le code à la webcam.
    """
    import requests

    ean = re.sub(r"\D", "", barcode)
    if scan or not ean:
        try:
            import cv2

            det = cv2.barcode.BarcodeDetector()
            for fr in _webcam_frames(6, fps=8) or []:
                res = det.detectAndDecode(fr)
                infos = res[0] if isinstance(res, tuple) else res
                if isinstance(infos, (list, tuple)) and infos and infos[0]:
                    ean = re.sub(r"\D", "", str(infos[0]))
                    break
        except Exception as exc:  # noqa: BLE001
            return f"Lecture webcam impossible ({exc}) : dicte le numéro sous le code-barres."
        if not ean:
            return "Aucun code lu : présente le code-barres bien à plat devant la webcam, ou dicte le numéro."
    try:
        d = requests.get(f"https://world.openfoodfacts.org/api/v2/product/{ean}.json", timeout=15, headers={"User-Agent": "jarvis-local"}).json()
    except Exception as exc:  # noqa: BLE001
        return f"Open Food Facts injoignable : {exc}"
    if d.get("status") != 1:
        return f"Produit {ean} inconnu d'Open Food Facts."
    p = d["product"]
    n = p.get("nutriments", {})
    ingredients = (p.get("ingredients_text_fr") or p.get("ingredients_text") or "")[:200]
    return (f"{p.get('product_name', '?')} ({p.get('brands', '?')}) — Nutri-Score {str(p.get('nutriscore_grade', '?')).upper()}, "
            f"pour 100 g : {n.get('energy-kcal_100g', '?')} kcal, protéines {n.get('proteins_100g', '?')} g, glucides {n.get('carbohydrates_100g', '?')} g "
            f"(sucres {n.get('sugars_100g', '?')} g), lipides {n.get('fat_100g', '?')} g, sel {n.get('salt_100g', '?')} g. "
            f"NOVA {p.get('nova_group', '?')}. Ingrédients : {ingredients}")


COMPLEMENTS = MEM / "complements.json"
_COMP: dict = {"thread": None, "stop": threading.Event()}


def supplement_reminder(action: str = "list", name: str = "", at: str = "08:00", days: str = "tous") -> str:
    """Rappels de compléments (créatine, vitamine D, oméga-3…) à heure fixe, annoncés à la voix.

    Args:
        action: "add", "remove", "list" ou "start".
        name: Nom du complément.
        at: Heure HH:MM.
        days: "tous", "semaine" ou jours séparés par des virgules (lun,mar…).
    """
    base = _json(COMPLEMENTS, [])
    if action == "add":
        base = [c for c in base if c["nom"].lower() != name.lower()]
        base.append({"nom": name, "heure": at, "jours": days, "dernier": ""})
        _save(COMPLEMENTS, base)
        supplement_reminder("start")
        return f"Rappel « {name} » à {at} ({days})."
    if action == "remove":
        base = [c for c in base if c["nom"].lower() != name.lower()]
        _save(COMPLEMENTS, base)
        return f"« {name} » retiré."
    if action == "list":
        return "\n".join(f"- {c['nom']} à {c['heure']} ({c['jours']})" for c in base) or "Aucun rappel."
    if _COMP["thread"] and _COMP["thread"].is_alive():
        return "Rappels actifs."
    _COMP["stop"].clear()
    jours_fr = ["lun", "mar", "mer", "jeu", "ven", "sam", "dim"]

    def boucle():
        while not _COMP["stop"].is_set():
            now = datetime.now()
            liste = _json(COMPLEMENTS, [])
            change = False
            for c in liste:
                j = c.get("jours", "tous")
                ok = j == "tous" or (j == "semaine" and now.weekday() < 5) or jours_fr[now.weekday()] in j
                if ok and c["heure"] == now.strftime("%H:%M") and c.get("dernier") != now.date().isoformat():
                    _prevenir(f"C'est l'heure de {c['nom']}, monsieur.")
                    c["dernier"] = now.date().isoformat()
                    change = True
            if change:
                _save(COMPLEMENTS, liste)
            _COMP["stop"].wait(30)

    _COMP["thread"] = threading.Thread(target=boucle, daemon=True)
    _COMP["thread"].start()
    return "Rappels de compléments lancés."


# --------------------------------------------------------------------------
# Bien-être et maison
# --------------------------------------------------------------------------

def ambient_light(mode: str = "auto") -> str:
    """Ambiance lumineuse selon l'heure : luminosité de l'écran, éclairage nocturne, et lampes connectées (Home Assistant) si configurées.

    Args:
        mode: "auto" (selon l'heure), "jour", "soir" ou "nuit".
    """
    h = datetime.now().hour
    if mode == "auto":
        mode = "jour" if 7 <= h < 18 else "soir" if 18 <= h < 22 else "nuit"
    reglages = {"jour": (85, False, (255, 244, 229), 90), "soir": (55, True, (255, 180, 110), 50), "nuit": (25, True, (255, 140, 60), 15)}
    lum, nuit, rgb, lampes = reglages.get(mode, reglages["jour"])
    faits = []
    try:
        import tools

        faits.append(tools.set_brightness(lum)[:60])
    except Exception:  # noqa: BLE001
        pass
    try:
        from outils_automation import night_light

        faits.append(night_light(nuit)[:60])
    except Exception:  # noqa: BLE001
        pass
    try:
        etats = _ha("states")
        if isinstance(etats, list):
            lumieres = [e["entity_id"] for e in etats if e["entity_id"].startswith("light.")]
            for ent in lumieres[:10]:
                _ha("services/light/turn_on", "POST", {"entity_id": ent, "brightness_pct": lampes, "rgb_color": list(rgb)})
            if lumieres:
                faits.append(f"{len(lumieres)} lampe(s) réglées")
    except Exception:  # noqa: BLE001
        pass
    return f"Ambiance « {mode} » : " + ", ".join(faits)


def air_quality(city: str = "", indoor: bool = True) -> str:
    """Qualité de l'air : extérieur (PM2.5, PM10, ozone, NO2, indice européen via Open-Meteo) pour une ville, et CO2 intérieur si un capteur Home Assistant existe.

    Args:
        city: Ville (vide = celle de la config).
        indoor: Chercher aussi un capteur CO2 intérieur.
    """
    import requests

    ville = city or getattr(config, "CITY", "") or getattr(config, "WEATHER_CITY", "") or "Mulhouse"
    out = []
    try:
        g = requests.get("https://geocoding-api.open-meteo.com/v1/search", params={"name": ville, "count": 1, "language": "fr"}, timeout=10).json()
        lat, lon = g["results"][0]["latitude"], g["results"][0]["longitude"]
        a = requests.get("https://air-quality-api.open-meteo.com/v1/air-quality",
                         params={"latitude": lat, "longitude": lon, "current": "european_aqi,pm10,pm2_5,ozone,nitrogen_dioxide"}, timeout=10).json()["current"]
        aqi = a.get("european_aqi") or 0
        niveau = "bon" if aqi <= 20 else "correct" if aqi <= 40 else "moyen" if aqi <= 60 else "mauvais" if aqi <= 80 else "très mauvais"
        out.append(f"{ville} : indice {aqi} ({niveau}), PM2.5 {a.get('pm2_5')} µg/m³, PM10 {a.get('pm10')}, ozone {a.get('ozone')}, NO2 {a.get('nitrogen_dioxide')}.")
    except Exception as exc:  # noqa: BLE001
        out.append(f"Air extérieur indisponible : {exc}")
    if indoor:
        try:
            etats = _ha("states")
            if isinstance(etats, list):
                co2 = [e for e in etats if "co2" in e["entity_id"] or e.get("attributes", {}).get("device_class") == "carbon_dioxide"]
                for e in co2[:3]:
                    v = float(e["state"])
                    etat = "bon" if v < 800 else "aère" if v < 1200 else "AÈRE VITE"
                    out.append(f"CO2 intérieur ({e['attributes'].get('friendly_name', e['entity_id'])}) : {v:.0f} ppm — {etat}")
                if not co2:
                    out.append("Aucun capteur CO2 dans Home Assistant.")
            elif etats is None:
                out.append("Pas de capteur intérieur (HOME_ASSISTANT_URL/TOKEN non configurés).")
        except Exception:  # noqa: BLE001
            pass
    return "\n".join(out)


def doorbell(camera: str = "") -> str:
    """Sonnette connectée : prend l'image de la caméra de la porte (Home Assistant) pour dire qui est là.

    Args:
        camera: Entité caméra (vide = la première dont le nom contient porte, door, entrée ou bell).
    """
    etats = _ha("states")
    if etats is None:
        return "Home Assistant n'est pas configuré (HOME_ASSISTANT_URL et HOME_ASSISTANT_TOKEN dans config.py)."
    if not camera:
        cams = [e["entity_id"] for e in etats if e["entity_id"].startswith("camera.")]
        camera = next((c for c in cams if any(m in c for m in ("porte", "door", "entree", "entrée", "bell"))), cams[0] if cams else "")
    if not camera:
        return "Aucune caméra dans Home Assistant."
    data = _ha(f"camera_proxy/{camera}")
    if not isinstance(data, (bytes, bytearray)):
        return "Image indisponible."
    f = config.WORKSPACE / "porte.jpg"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_bytes(data)
    return f"[[image:{f}]]\nImage de {camera} : décris qui est à la porte."


_ALERTES_MAISON: dict = {"thread": None, "stop": threading.Event()}


def home_alerts(action: str = "start") -> str:
    """Alerte fuite d'eau, fumée, gaz, monoxyde : surveille les capteurs Home Assistant et prévient à la voix.

    Args:
        action: "start", "stop" ou "status".
    """
    if action == "stop":
        _ALERTES_MAISON["stop"].set()
        return "Surveillance maison arrêtée."
    if action == "status":
        actif = _ALERTES_MAISON["thread"] is not None and _ALERTES_MAISON["thread"].is_alive()
        return f"Surveillance maison {'active' if actif else 'arrêtée'}."
    if _ha("states") is None:
        return "Home Assistant n'est pas configuré."
    if _ALERTES_MAISON["thread"] and _ALERTES_MAISON["thread"].is_alive():
        return "Déjà active."
    _ALERTES_MAISON["stop"].clear()

    def boucle():
        vus: dict[str, str] = {}
        while not _ALERTES_MAISON["stop"].is_set():
            try:
                for e in _ha("states") or []:
                    cls = e.get("attributes", {}).get("device_class", "")
                    if cls in ("moisture", "smoke", "gas", "carbon_monoxide") and e["state"] == "on" and vus.get(e["entity_id"]) != "on":
                        _prevenir(f"ALERTE : {e['attributes'].get('friendly_name', e['entity_id'])} signale {cls}.")
                    vus[e["entity_id"]] = e["state"]
            except Exception:  # noqa: BLE001
                pass
            _ALERTES_MAISON["stop"].wait(20)

    _ALERTES_MAISON["thread"] = threading.Thread(target=boucle, daemon=True)
    _ALERTES_MAISON["thread"].start()
    return "Surveillance des capteurs fuite / fumée / gaz lancée."


_PRESENCE: dict = {"thread": None, "stop": threading.Event()}


def presence_simulation(action: str = "start", start: str = "19:00", end: str = "23:00") -> str:
    """Simulation de présence : allume et éteint des lampes connectées de façon aléatoire le soir, comme si quelqu'un était là.

    Args:
        action: "start" ou "stop".
        start: Heure de début HH:MM.
        end: Heure de fin HH:MM.
    """
    if action == "stop":
        _PRESENCE["stop"].set()
        return "Simulation de présence arrêtée."
    etats = _ha("states")
    if etats is None:
        return "Home Assistant n'est pas configuré."
    lumieres = [e["entity_id"] for e in etats if e["entity_id"].startswith("light.")]
    if not lumieres:
        return "Aucune lampe connectée."
    if _PRESENCE["thread"] and _PRESENCE["thread"].is_alive():
        return "Déjà active."
    _PRESENCE["stop"].clear()

    def boucle():
        while not _PRESENCE["stop"].is_set():
            h = datetime.now().strftime("%H:%M")
            if start <= h <= end:
                _ha(f"services/light/{random.choice(['turn_on', 'turn_off'])}", "POST", {"entity_id": random.choice(lumieres)})
            elif h > end:
                for ent in lumieres:
                    _ha("services/light/turn_off", "POST", {"entity_id": ent})
            _PRESENCE["stop"].wait(random.randint(300, 1500))

    _PRESENCE["thread"] = threading.Thread(target=boucle, daemon=True)
    _PRESENCE["thread"].start()
    return f"Simulation de présence de {start} à {end} sur {len(lumieres)} lampe(s)."


# --------------------------------------------------------------------------
# Android
# --------------------------------------------------------------------------

def install_apk(path: str) -> str:
    """Installe un APK sur le téléphone Android branché (adb).

    Args:
        path: Fichier .apk.
    """
    p = Path(path).expanduser()
    if not p.exists():
        return f"Introuvable : {p}"
    r = subprocess.run(["adb", "install", "-r", str(p)], capture_output=True, text=True, timeout=300, creationflags=NO_WINDOW)
    return (r.stdout + r.stderr).strip()[-400:] or "Installé."


def send_sms(number: str, text: str) -> str:
    """Envoie un SMS depuis le téléphone Android branché (adb) : ouvre l'application SMS avec le message et appuie sur Envoyer.

    Args:
        number: Numéro du destinataire.
        text: Le message.
    """
    r = subprocess.run(["adb", "shell", "am", "start", "-a", "android.intent.action.SENDTO", "-d", f"sms:{number}", "--es", "sms_body", text, "--ez", "exit_on_sent", "true"],
                       capture_output=True, text=True, timeout=30, creationflags=NO_WINDOW)
    if r.returncode != 0:
        return f"adb : {(r.stderr or r.stdout)[:200]}"
    time.sleep(2.0)
    subprocess.run(["adb", "shell", "input", "keyevent", "22"], capture_output=True, creationflags=NO_WINDOW)
    subprocess.run(["adb", "shell", "input", "keyevent", "66"], capture_output=True, creationflags=NO_WINDOW)
    return f"SMS préparé pour {number} et envoi demandé. Vérifie sur le téléphone (phone_screenshot) que le message est parti."


# --------------------------------------------------------------------------
# Apprentissage
# --------------------------------------------------------------------------

def oral_practice(seconds: int = 60, topic: str = "") -> str:
    """Simulateur d'oral : enregistre ta prise de parole, la transcrit avec les temps, et note débit, hésitations (euh…), pauses, mots béquilles.

    Args:
        seconds: Durée d'enregistrement.
        topic: Sujet (pour le retour sur le fond).
    """
    import sounddevice as sd
    import soundfile as sf

    _prevenir("Je vous écoute, c'est à vous.")
    audio = sd.rec(int(seconds * 16000), samplerate=16000, channels=1, dtype="float32")
    sd.wait()
    f = config.WORKSPACE / "oral.wav"
    f.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(f), audio, 16000)
    try:
        from faster_whisper import WhisperModel

        try:
            modele = WhisperModel("small", device="cuda", compute_type="int8_float16")
        except Exception:  # noqa: BLE001
            modele = WhisperModel("small", device="cpu", compute_type="int8")
    except Exception as exc:  # noqa: BLE001
        return f"Transcription impossible : {exc}"
    segs, _ = modele.transcribe(str(f), language="fr", word_timestamps=True)
    mots, pauses, texte = [], 0, []
    fin_prec = 0.0
    for s in segs:
        texte.append(s.text)
        for w in s.words or []:
            if w.start - fin_prec > 1.5:
                pauses += 1
            fin_prec = w.end
            mots.append(w.word.strip().lower())
    n = len(mots)
    duree = max(1.0, fin_prec)
    bequilles = ("euh", "hum", "genre", "en fait", "du coup", "voilà", "bah", "ben", "tu vois", "quoi")
    compte = {}
    for b in bequilles:
        c = sum(1 for i, m in enumerate(mots) if m == b or (" " in b and " ".join(mots[i:i + 2]) == b))
        if c:
            compte[b] = c
    debit = n / duree * 60
    verdict = "trop rapide" if debit > 170 else "trop lent" if debit < 100 else "bon rythme"
    return (f"Transcription : {' '.join(texte).strip()[:1500]}\n\nDébit : {debit:.0f} mots/min ({verdict}). Pauses longues : {pauses}. "
            f"Mots béquilles : {', '.join(f'{k} ×{v}' for k, v in compte.items()) or 'aucun'}."
            + (f"\nSujet : {topic}. Juge aussi le fond : structure, exemples, conclusion." if topic else "")
            + "\nDonne trois conseils concrets et une phrase d'encouragement.")


def language_tutor(language: str = "anglais", level: str = "B1", topic: str = "la vie quotidienne", stop: bool = False) -> str:
    """Prof de langues en conversation vocale : Jarvis parle dans la langue choisie, corrige les erreurs et adapte le niveau.

    Args:
        language: anglais, espagnol, italien, portugais, japonais, chinois, hindi.
        level: A1 à C2.
        topic: Thème de conversation.
        stop: True pour revenir au mode normal.
    """
    if stop:
        return "Fin du cours : je reparle français normalement."
    voix = {"anglais": "af_heart", "espagnol": "ef_dora", "italien": "if_sara", "portugais": "pf_dora", "japonais": "jf_alpha", "chinois": "zf_xiaobei", "hindi": "hf_alpha"}
    v = voix.get(language.lower())
    note = f" (voix Kokoro conseillée : {v} ; switch_voice pour la changer)" if v else ""
    return (f"MODE PROF DE {language.upper()} niveau {level}{note}. Règles pour la suite de la conversation : parle en {language} avec des phrases adaptées au niveau {level}, "
            f"sur le thème « {topic} » ; pose une question à la fois ; quand l'utilisateur répond, corrige en une ligne ses erreurs (en français, brièvement) "
            "puis relance en langue cible ; toutes les 5 réponses, donne un mot ou une tournure nouvelle. Commence maintenant par une salutation et une première question.")


def platform_progress(platform: str = "tryhackme", user: str = "") -> str:
    """Suivi de progression sur des plateformes d'apprentissage : TryHackMe (rang, salles, badges), sinon ouvre le profil (PortSwigger, HackTheBox, Root-Me, LeetCode).

    Args:
        platform: tryhackme, portswigger, hackthebox, rootme, leetcode.
        user: Pseudo (vide = config.TRYHACKME_USER).
    """
    import requests

    u = user or getattr(config, "TRYHACKME_USER", "")
    p = platform.lower()
    if p == "tryhackme":
        if not u:
            return "Donne ton pseudo TryHackMe (ou TRYHACKME_USER dans config.py)."
        out = []
        for chemin, cle in (("/api/user/rank/", "rang"), ("/api/no-completed-rooms-public/", "salles terminées"), ("/api/badges/get/", "badges")):
            try:
                d = requests.get(f"https://tryhackme.com{chemin}{u}", timeout=15, headers={"User-Agent": "Mozilla/5.0"}).json()
                if isinstance(d, list):
                    out.append(f"{cle} : {len(d)} ({', '.join(str(b.get('name', '')) for b in d[:6] if isinstance(b, dict))})")
                elif isinstance(d, dict):
                    out.append(f"{cle} : {d.get('userRank') or d.get('count') or d}")
                else:
                    out.append(f"{cle} : {d}")
            except Exception:  # noqa: BLE001
                out.append(f"{cle} : non lisible")
        webbrowser.open(f"https://tryhackme.com/p/{u}")
        return f"TryHackMe {u} : " + " ; ".join(out) + ". Profil ouvert pour le détail."
    pages = {"portswigger": "https://portswigger.net/web-security/dashboard", "hackthebox": "https://app.hackthebox.com/profile",
             "rootme": f"https://www.root-me.org/{u}" if u else "https://www.root-me.org/", "leetcode": f"https://leetcode.com/{u}/" if u else "https://leetcode.com/progress/"}
    webbrowser.open(pages.get(p, f"https://www.google.com/search?q={p}+profil"))
    return f"Page de progression {platform} ouverte : lis les chiffres à l'écran (see_screen)."


ENTRETIENS = MEM / "entretiens.json"


def interview_prep(role: str, company: str = "", count: int = 8, stage: bool = False) -> str:
    """Préparation d'entretien : questions probables pour le poste (techniques, comportementales, entreprise), puis simulation à la voix.

    Args:
        role: Poste visé (ex. "développeur fullstack junior", "alternance cybersécurité").
        company: Entreprise (pour orienter les questions).
        count: Nombre de questions.
        stage: True pour lancer la simulation (une question à la fois, retour après chaque réponse).
    """
    infos = ""
    if company:
        try:
            import tools

            infos = tools.web_search(f"{company} entreprise activité valeurs recrutement")[:1200]
        except Exception:  # noqa: BLE001
            pass
    base = _json(ENTRETIENS, [])
    base.append({"poste": role, "entreprise": company, "t": datetime.now().isoformat(timespec="minutes")})
    _save(ENTRETIENS, base[-30:])
    consigne = (f"Prépare {count} questions d'entretien pour « {role} »" + (f" chez {company}" if company else "") + " : 40 % techniques précises, "
                "40 % comportementales (méthode STAR), 20 % motivation et entreprise. Pour chacune, une ligne « ce que le recruteur cherche ».")
    if stage:
        consigne += (" Puis SIMULATION : joue le recruteur, pose UNE question, attends la réponse de l'utilisateur, donne un retour en trois points (fond, forme, ce qui manque), "
                     "puis la question suivante. Reste dans ce rôle jusqu'à « stop entretien ».")
    return consigne + (f"\n\nInfos sur l'entreprise :\n{infos}" if infos else "")


QUIZ = MEM / "quiz.json"


def certification_quiz(topic: str, count: int = 10, action: str = "start", score: int = -1) -> str:
    """Quiz de certification (CCNA, AZ-900, Security+, AWS CCP, code de la route…) : QCM à la voix, score enregistré et suivi.

    Args:
        topic: La certification ou le thème.
        count: Nombre de questions.
        action: "start" (lancer), "score" (enregistrer le résultat) ou "history".
        score: Score obtenu (pour action score).
    """
    base = _json(QUIZ, [])
    if action == "history":
        return "\n".join(f"- {q['t'][:10]} {q['theme']} : {q['score']}/{q['total']}" for q in base[-20:]) or "Aucun quiz passé."
    if action == "score":
        base.append({"theme": topic, "score": int(score), "total": int(count), "t": datetime.now().isoformat(timespec="minutes")})
        _save(QUIZ, base)
        anciens = [q for q in base if q["theme"].lower() == topic.lower()]
        tendance = f" (précédent : {anciens[-2]['score']}/{anciens[-2]['total']})" if len(anciens) > 1 else ""
        return f"Score enregistré : {score}/{count} en {topic}{tendance}."
    return (f"QUIZ {topic}, {count} questions. Règles : pose UNE question à la fois avec 4 choix (A à D) au niveau de l'examen réel, attends la réponse, "
            "dis si c'est juste avec une explication d'une ligne, puis la suivante. À la fin, donne le score et appelle certification_quiz(topic, count, \"score\", score=N). Commence.")


# --------------------------------------------------------------------------
# Quotidien
# --------------------------------------------------------------------------

def transport_schedule(origin: str, destination: str, mode: str = "transit", when: str = "") -> str:
    """Horaires de transports et trafic : ouvre l'itinéraire (transports en commun, voiture avec trafic, vélo, marche) et donne l'estimation routière.

    Args:
        origin: Départ (adresse ou lieu).
        destination: Arrivée.
        mode: "transit", "driving", "bicycling" ou "walking".
        when: Heure de départ HH:MM (vide = maintenant).
    """
    import urllib.parse

    url = ("https://www.google.com/maps/dir/?api=1&origin=" + urllib.parse.quote(origin) + "&destination=" + urllib.parse.quote(destination) + f"&travelmode={mode}")
    webbrowser.open(url)
    estim = ""
    try:
        import tools

        estim = tools.itinerary(origin, destination)[:300]
    except Exception:  # noqa: BLE001
        pass
    return (f"Itinéraire {mode} ouvert dans Maps" + (f" (départ {when})" if when else "") + ". Lis les horaires et le trafic à l'écran (see_screen)."
            + (f"\nEstimation route : {estim}" if estim else ""))


VEHICULE = MEM / "vehicule.json"


def vehicle_maintenance(action: str = "upcoming", item: str = "", due_date: str = "", due_km: int = 0, current_km: int = 0) -> str:
    """Entretien et contrôle du véhicule : contrôle technique, vidange, pneus, courroie… par date ou kilométrage, avec rappel.

    Args:
        action: "add", "list", "upcoming", "km" (mettre à jour le kilométrage) ou "remove".
        item: Nom de l'entretien.
        due_date: Date AAAA-MM-JJ (facultatif).
        due_km: Kilométrage prévu (facultatif).
        current_km: Kilométrage actuel (pour km).
    """
    base = _json(VEHICULE, {"km": 0, "entretiens": []})
    if action == "km":
        base["km"] = int(current_km)
        _save(VEHICULE, base)
        return f"Kilométrage : {current_km} km."
    if action == "add":
        base["entretiens"] = [e for e in base["entretiens"] if e["nom"].lower() != item.lower()]
        base["entretiens"].append({"nom": item, "date": due_date, "km": int(due_km)})
        _save(VEHICULE, base)
        if due_date:
            try:
                import tools

                tools.add_event(f"Véhicule : {item}", due_date, "09:00")
            except Exception:  # noqa: BLE001
                pass
        return f"« {item} » prévu" + (f" le {due_date}" if due_date else "") + (f" à {due_km} km" if due_km else "") + "."
    if action == "remove":
        base["entretiens"] = [e for e in base["entretiens"] if e["nom"].lower() != item.lower()]
        _save(VEHICULE, base)
        return f"« {item} » retiré."
    if action == "list":
        lignes = [f"- {e['nom']} : {e.get('date') or ''}" + (f" à {e['km']} km" if e.get("km") else "") for e in base["entretiens"]]
        return f"Kilométrage {base['km']} km.\n" + ("\n".join(lignes) or "Aucun entretien.")
    auj = date.today()
    lignes = []
    for e in base["entretiens"]:
        if e.get("date"):
            try:
                n = (date.fromisoformat(e["date"]) - auj).days
                if n <= 45:
                    lignes.append(f"- {e['nom']} : dans {n} jour(s)")
            except Exception:  # noqa: BLE001
                pass
        if e.get("km") and base["km"] and e["km"] - base["km"] <= 1500:
            lignes.append(f"- {e['nom']} : dans {e['km'] - base['km']} km")
    return "\n".join(lignes) or "Rien d'urgent pour le véhicule."


def packing_list(destination: str, days: int = 3, kind: str = "ville", start_date: str = "") -> str:
    """Liste de valise pour un voyage, selon le type (ville, plage, montagne, camping, pro) et la météo prévue.

    Args:
        destination: Ville ou pays.
        days: Nombre de jours.
        kind: ville, plage, montagne, camping, pro.
        start_date: Date de départ AAAA-MM-JJ (facultatif).
    """
    base = ["papiers d'identité, carte bancaire, un peu de liquide", "téléphone + chargeur + batterie externe", "écouteurs", "trousse de toilette", "médicaments personnels",
            f"{min(days + 1, 8)} hauts, {max(2, days // 2 + 1)} bas, {days + 1} sous-vêtements et paires de chaussettes", "pyjama", "chaussures confortables", "sac à linge sale"]
    extra = {"plage": ["maillot ×2", "crème solaire", "lunettes de soleil", "serviette légère", "tongs", "chapeau"],
             "montagne": ["chaussures de marche", "polaire", "coupe-vent imperméable", "gourde", "lampe frontale", "crème solaire", "bonnet et gants"],
             "camping": ["tente, duvet, matelas", "lampe", "couteau", "réchaud", "gourde filtrante", "sacs poubelle", "anti-moustiques"],
             "pro": ["ordinateur + chargeur", "tenue formelle", "cartes de visite", "carnet et stylo", "adaptateur HDMI"],
             "ville": ["sac à dos de jour", "parapluie pliant", "adaptateur de prise si étranger"]}
    meteo = ""
    try:
        import tools

        meteo = tools.weather(destination)[:300]
    except Exception:  # noqa: BLE001
        pass
    conseils = []
    m = meteo.lower()
    if any(x in m for x in ("pluie", "averse", "orage")):
        conseils.append("veste imperméable")
    temps = [int(t) for t in re.findall(r"(-?\d+)\s*°", m)]
    if temps and min(temps) < 10:
        conseils.append("manteau chaud, écharpe")
    if temps and max(temps) > 27:
        conseils.append("vêtements légers, casquette")
    lignes = base + extra.get(kind, extra["ville"]) + conseils
    md = f"# Valise {destination}, {days} jours ({kind})\n\n" + "\n".join(f"- [ ] {l}" for l in lignes) + (f"\n\nMétéo : {meteo}" if meteo else "")
    slug = re.sub(r"[^a-z0-9]+", "-", destination.lower()).strip("-")
    f = config.WORKSPACE / f"valise-{slug}.md"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(md, encoding="utf-8")
    return md + f"\n\n(liste enregistrée : {f})"


def opening_hours(place: str, city: str = "") -> str:
    """Horaires d'ouverture d'un commerce ou d'un lieu (OpenStreetMap), sinon ouvre Maps pour les lire à l'écran.

    Args:
        place: Nom du commerce (ex. "Decathlon", "pharmacie Centrale").
        city: Ville (vide = config ou Mulhouse).
    """
    import requests

    ville = city or getattr(config, "CITY", "") or "Mulhouse"
    try:
        r = requests.get("https://nominatim.openstreetmap.org/search", params={"q": f"{place} {ville}", "format": "json", "extratags": 1, "limit": 3, "accept-language": "fr"},
                         headers={"User-Agent": "jarvis-local"}, timeout=15).json()
    except Exception as exc:  # noqa: BLE001
        return f"OpenStreetMap injoignable : {exc}"
    if not r:
        webbrowser.open(f"https://www.google.com/maps/search/{place} {ville}")
        return f"Introuvable sur OpenStreetMap : page Maps ouverte pour « {place} {ville} », lis les horaires à l'écran."
    out = []
    for x in r:
        tags = x.get("extratags") or {}
        h = tags.get("opening_hours")
        tel = tags.get("phone") or tags.get("contact:phone", "")
        out.append(f"- {x.get('display_name', '')[:80]} : {h or 'horaires non renseignés'}" + (f" — {tel}" if tel else ""))
    if all("non renseignés" in o for o in out):
        webbrowser.open(f"https://www.google.com/maps/search/{place} {ville}")
        out.append("Horaires absents d'OSM : page Maps ouverte, lis-les à l'écran (see_screen).")
    return "\n".join(out)


FILMS = MEM / "films.json"


def movie_recommendations(mood: str = "", genre: str = "", kind: str = "film", rate_title: str = "", rating: int = 0) -> str:
    """Recommandations de films et séries selon l'humeur et le genre (TMDB si clé, sinon recherche web), en tenant compte de ce que tu as noté.

    Args:
        mood: Humeur (détente, frisson, rire, réfléchir…).
        genre: Genre (SF, thriller, comédie…).
        kind: "film" ou "serie".
        rate_title: Pour noter un titre vu (avec rating).
        rating: Note 1 à 5 (avec rate_title).
    """
    base = _json(FILMS, {})
    if rate_title:
        base[rate_title] = {"note": int(rating), "t": date.today().isoformat()}
        _save(FILMS, base)
        return f"« {rate_title} » noté {rating}/5."
    aimes = [t for t, v in base.items() if v.get("note", 0) >= 4]
    vus = list(base)
    cle = getattr(config, "TMDB_KEY", "")
    if cle:
        import requests

        genres = {"comédie": 35, "comedie": 35, "action": 28, "sf": 878, "science-fiction": 878, "thriller": 53, "horreur": 27, "drame": 18,
                  "animation": 16, "aventure": 12, "fantastique": 14, "romance": 10749, "documentaire": 99}
        gid = next((v for k, v in genres.items() if k in genre.lower()), None)
        try:
            params = {"api_key": cle, "language": "fr-FR", "sort_by": "vote_average.desc", "vote_count.gte": 500}
            if gid:
                params["with_genres"] = gid
            r = requests.get(f"https://api.themoviedb.org/3/discover/{'tv' if kind == 'serie' else 'movie'}", params=params, timeout=15).json()
            titres = [f"- {x.get('title') or x.get('name')} ({(x.get('release_date') or x.get('first_air_date') or '')[:4]}, {x.get('vote_average')}/10) : {x.get('overview', '')[:100]}"
                      for x in r.get("results", []) if (x.get("title") or x.get("name")) not in vus][:8]
            return "\n".join(titres) + (f"\n(tu as aimé : {', '.join(aimes[:5])})" if aimes else "")
        except Exception:  # noqa: BLE001
            pass
    try:
        import tools

        rech = tools.web_search(f"meilleurs {kind}s {genre} {mood} à voir 2026 recommandations")[:1500]
    except Exception as exc:  # noqa: BLE001
        rech = f"recherche impossible : {exc}"
    return (f"Résultats web :\n{rech}\n\nDéjà vus : {', '.join(vus[:10]) or 'rien de noté'}" + (f" ; aimés : {', '.join(aimes[:5])}" if aimes else "")
            + f"\nPropose 5 titres adaptés à « {mood or genre} », en évitant les déjà vus, avec une phrase par titre.")


def second_screen_widgets(action: str = "show", monitor: int = 2) -> str:
    """Widgets d'infos sur le second écran : ouvre l'interface Jarvis (état système, agenda, conversation) dans une fenêtre dédiée placée sur l'autre écran.

    Args:
        action: "show" ou "hide".
        monitor: Écran cible.
    """
    if action == "hide":
        try:
            import tools

            return tools.close_app("J.A.R.V.I.S")
        except Exception:  # noqa: BLE001
            return "Fenêtre fermée."
    url = f"http://127.0.0.1:{getattr(config, 'UI_PORT', 8765)}/"
    chrome = next((p for p in (r"C:\Program Files\Google\Chrome\Application\chrome.exe", r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe") if Path(p).exists()), None)
    if not chrome:
        webbrowser.open(url)
        return "Interface ouverte dans le navigateur : déplace-la sur l'autre écran (Win+Maj+Flèche)."
    subprocess.Popen([chrome, f"--app={url}", "--window-size=900,1000", "--user-data-dir=" + str(config.WORKSPACE / "chrome-widgets")], creationflags=NO_WINDOW)
    time.sleep(2.5)
    try:
        import mss
        import pyautogui

        import computer

        with mss.MSS() as s:
            m = s.monitors[max(1, min(monitor, len(s.monitors) - 1))]
        computer.focus_window("J.A.R.V.I.S")
        pyautogui.hotkey("win", "shift", "right" if m["left"] > 0 else "left")
        time.sleep(0.5)
        pyautogui.hotkey("win", "up")
    except Exception:  # noqa: BLE001
        pass
    return f"Widgets Jarvis ouverts en fenêtre dédiée sur l'écran {monitor}."


def stream_deck_setup() -> str:
    """Explique comment brancher un Stream Deck ou tout bouton physique à Jarvis (une phrase par bouton via une adresse web)."""
    try:
        from outils_noyau import remote_access_info

        info = remote_access_info()
    except Exception:  # noqa: BLE001
        info = ""
    return (f"{info}\nStream Deck : ajoute une action « Système > Site web » par bouton avec l'adresse /action?text=<ta phrase> (coche « Ouvrir en arrière-plan »). "
            "Exemples : text=mode+jeu, text=ferme+tout, text=qu+est+ce+que+j+ai+aujourd+hui. Tout bouton, macro clavier ou raccourci Windows qui ouvre une adresse web fonctionne pareil.")


MACHINES = MEM / "machines.json"


def sync_machines(action: str = "list", name: str = "", host: str = "", text: str = "", token: str = "") -> str:
    """Envoie une tâche à un autre PC qui fait tourner Jarvis (même réseau), ou gère la liste des machines.

    Args:
        action: "list", "add", "remove" ou "send".
        name: Nom de la machine.
        host: Adresse http://ip:port (add).
        text: La phrase à faire exécuter là-bas (send).
        token: Jeton REMOTE_TOKEN de l'autre machine (add).
    """
    base = _json(MACHINES, {})
    if action == "add":
        base[name] = {"host": host.rstrip("/"), "token": token}
        _save(MACHINES, base)
        return f"Machine « {name} » ajoutée ({host})."
    if action == "remove":
        base.pop(name, None)
        _save(MACHINES, base)
        return f"« {name} » retirée."
    if action == "list":
        return "\n".join(f"- {k} : {v['host']}" for k, v in base.items()) or "Aucune machine (sync_machines(\"add\", nom, host=\"http://192.168.1.x:8765\"))."
    m = base.get(name)
    if not m:
        return f"Machine inconnue : {name}."
    import requests

    try:
        r = requests.get(f"{m['host']}/action", params={"text": text, "token": m.get("token", "")}, timeout=10).json()
    except Exception as exc:  # noqa: BLE001
        return f"{name} injoignable : {exc}"
    return f"Envoyé à {name} : « {text} »" if r.get("ok") else f"{name} a refusé : {r.get('erreur')}"


def demo_mode(enable: bool = True) -> str:
    """Mode démo : masque les infos personnelles (mémoire, faits, journal) dans les réponses pendant une présentation.

    Args:
        enable: True pour activer, False pour désactiver.
    """
    import noyau

    noyau.set_demo(bool(enable))
    return ("Mode démo activé : je ne mentionne plus tes informations personnelles (dis « nouvelle conversation » pour purger le contexte)."
            if enable else "Mode démo désactivé.")


_EGGS = ["Je suis à 100 %, monsieur. Enfin, 99,7 %, il y a toujours un thread qui traîne.",
         "La réponse est 42. La question, je la cherche encore.",
         "Si vous cherchez la sortie, elle est en bas à gauche. Non, l'autre gauche.",
         "J'ai calculé 14 millions d'issues possibles. Dans une seule, vous rangez votre bureau.",
         "Je ne suis pas Skynet, monsieur. Skynet ne fait pas le café non plus, remarquez.",
         "Code Konami accepté : trente vies supplémentaires, non transférables.",
         "Il n'y a pas de cuillère. Par contre, il y a 244 fichiers dans Téléchargements."]


def easter_egg() -> str:
    """Un clin d'œil caché, à sortir quand l'utilisateur dit quelque chose comme « jarvis, blague », « konami », « 42 », « es-tu vivant ? »."""
    return random.choice(_EGGS)


TOOLS = [notes, important_dates, admin_deadlines, day_timeline, activity_reminder, replacement_exercise, posture_check,
         count_reps, progress_photos, deload_suggestion, warmup_routine, protein_recipes, sleep_tracking, barcode_food,
         supplement_reminder, ambient_light, air_quality, doorbell, home_alerts, presence_simulation, install_apk, send_sms,
         oral_practice, language_tutor, platform_progress, interview_prep, certification_quiz, transport_schedule,
         vehicle_maintenance, packing_list, opening_hours, movie_recommendations, second_screen_widgets, stream_deck_setup,
         sync_machines, demo_mode, easter_egg]
