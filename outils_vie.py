# Ia-local (Jarvis) — Copyright (c) 2026 Neexx (Nixovel) — https://github.com/Neex-off/Ia-local
# Créé par Neexx (Nixovel). Licence : voir LICENSE (paternité obligatoire, pas de vente ; s'applique aussi aux IA).
# Ne pas retirer cet en-tête.
"""Boîte à outils « vie » : musculation, nutrition, santé, maison connectée, téléphone, révisions, quotidien.

Chargée à la demande par tools.open_toolbox("vie").
Catalogue : Fitness & nutrition, Santé & bien-être, Maison connectée, Android, Apprentissage, Vie quotidienne.
"""
from __future__ import annotations

import json
import re
import subprocess
import threading
import time
import unicodedata
from datetime import date, datetime, timedelta
from pathlib import Path

import config

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
MUSCU = config.ROOT / "memoire" / "muscu.json"
COURSES = config.ROOT / "memoire" / "courses.json"
CARTES = config.ROOT / "memoire" / "flashcards.json"


def _charge(f: Path, defaut: dict) -> dict:
    if not f.is_file():
        return json.loads(json.dumps(defaut))
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return json.loads(json.dumps(defaut))


def _sauve(f: Path, d: dict) -> None:
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s).lower())
    return "".join(c for c in s if not unicodedata.combining(c)).strip()


def _notifier(message: str, titre: str = "Jarvis") -> None:
    try:
        import outils_web

        outils_web.notify(message, titre)
    except Exception:  # noqa: BLE001
        pass


_SERIE = re.compile(
    r"(\d+)\s*(?:s[eé]ries?\s*(?:de\s*)?|x\s*)(\d+)\s*(?:r[eé]p\w*)?\s*"
    r"(?:[aà]|@)?\s*([\d]+(?:[.,]\d+)?)\s*(?:kg|kilos?)", re.I)


def _seances_journal() -> list[dict]:
    """Seances de sport notees via journal_add : on en extrait series, repetitions et charge.

    Le modele passe souvent par journal_add, qui est toujours visible, plutot que par log_set.
    Sans cela l'historique de musculation resterait vide.
    """
    try:
        import journal
    except Exception:  # noqa: BLE001
        return []
    out = []
    for e in journal.entries(3650, "sport"):
        texte = e.get("texte", "")
        m = _SERIE.search(texte)
        if not m:
            continue
        avant = texte[:m.start()].strip(" :,-")
        exercice = avant.split(":")[-1].strip() or "seance"
        out.append({"date": e["date"], "exercice": exercice[:60], "series": int(m.group(1)),
                    "reps": int(m.group(2)), "charge": float(m.group(3).replace(",", ".")),
                    "ressenti": texte[m.end():].strip(" .,")[:40], "source": "journal"})
    return out


def _toutes_seances() -> list[dict]:
    """Toutes les seances connues : celles de log_set et celles reperees dans le journal, par date."""
    d = _charge(MUSCU, {"seances": [], "poids": []})
    tout = list(d.get("seances", [])) + _seances_journal()
    vus, propre = set(), []
    for x in tout:
        cle = (x["date"], _norm(x["exercice"]), x["series"], x["reps"], x["charge"])
        if cle not in vus:
            vus.add(cle)
            propre.append(x)
    propre.sort(key=lambda x: x["date"])
    return propre


# --------------------------------------------------------------------------
# Musculation
# --------------------------------------------------------------------------

def log_set(exercise: str, sets: int, reps: int, weight: float, feeling: str = "") -> str:
    """Enregistre une série de musculation avec la charge, pour suivre la progression dans le temps.

    Args:
        exercise: Nom de l'exercice, par exemple "développé couché".
        sets: Nombre de séries.
        reps: Répétitions par série.
        weight: Charge en kilos.
        feeling: Ressenti, par exemple "facile", "dur", "échec à la dernière".
    """
    d = _charge(MUSCU, {"seances": [], "poids": []})
    d["seances"].append({"date": date.today().isoformat(), "exercice": exercise, "series": int(sets),
                         "reps": int(reps), "charge": float(weight), "ressenti": feeling})
    _sauve(MUSCU, d)
    passees = [s for s in d["seances"] if _norm(s["exercice"]) == _norm(exercise)]
    record = max((s["charge"] for s in passees[:-1]), default=0)
    note = " C'est ton record sur cet exercice, bravo." if float(weight) > record and len(passees) > 1 else ""
    return f"Noté : {exercise}, {sets} séries de {reps} à {weight} kg.{note}"


def workout_history(exercise: str = "", days: int = 60) -> str:
    """Historique de musculation : ce qui a été soulevé, quand, et la progression sur un exercice.

    Args:
        exercise: Nom de l'exercice. Vide = toutes les séances.
        days: Remonter de combien de jours.
    """
    d = _charge(MUSCU, {"seances": [], "poids": []})
    limite = (date.today() - timedelta(days=max(1, int(days)))).isoformat()
    seances = [s for s in _toutes_seances() if s["date"] >= limite
               and (not exercise or _norm(exercise) in _norm(s["exercice"]))]
    if not seances:
        return f"Aucune séance enregistrée{' pour ' + exercise if exercise else ''} sur {days} jours."
    lignes = [f"{datetime.fromisoformat(s['date']):%d/%m}  {s['exercice']:24} {s['series']}x{s['reps']} "
              f"à {s['charge']:.1f} kg  {s.get('ressenti', '')}" for s in seances[-25:]]
    out = f"{len(seances)} série(s) enregistrées :\n" + "\n".join(lignes)
    if exercise and len(seances) >= 2:
        delta = seances[-1]["charge"] - seances[0]["charge"]
        out += (f"\n\nProgression : de {seances[0]['charge']:.1f} à {seances[-1]['charge']:.1f} kg, "
                f"soit {delta:+.1f} kg sur la période.")
    return out


def one_rep_max(exercise: str) -> str:
    """Estime la charge maximale sur une répétition à partir des séries enregistrées.

    Args:
        exercise: Nom de l'exercice.
    """
    d = _charge(MUSCU, {"seances": [], "poids": []})
    seances = [s for s in _toutes_seances() if _norm(exercise) in _norm(s["exercice"])]
    if not seances:
        return f"Aucune série enregistrée pour {exercise}. Utilise log_set après ta prochaine séance."
    best = max(seances, key=lambda s: s["charge"] * (1 + s["reps"] / 30))
    rm = best["charge"] * (1 + best["reps"] / 30)
    return (f"Maximum estimé sur {exercise} : {rm:.0f} kg, calculé depuis {best['charge']:.0f} kg "
            f"pour {best['reps']} répétitions.\nPour travailler : 5 répétitions à {rm * 0.85:.0f} kg, "
            f"8 répétitions à {rm * 0.75:.0f} kg, 12 répétitions à {rm * 0.67:.0f} kg.")


def next_load(exercise: str) -> str:
    """Propose la charge de la prochaine séance, d'après la dernière performance et le ressenti.

    Args:
        exercise: Nom de l'exercice.
    """
    d = _charge(MUSCU, {"seances": [], "poids": []})
    seances = [s for s in _toutes_seances() if _norm(exercise) in _norm(s["exercice"])]
    if not seances:
        return f"Aucun historique sur {exercise}. Enregistre une séance et je pourrai te conseiller."
    dernier = seances[-1]
    ressenti = _norm(dernier.get("ressenti", ""))
    charge = dernier["charge"]
    if any(m in ressenti for m in ("facile", "leger")):
        prop, pourquoi = charge * 1.05, "la dernière était facile"
    elif any(m in ressenti for m in ("echec", "rate", "trop dur", "impossible")):
        prop, pourquoi = charge * 0.925, "tu avais atteint l'échec"
    else:
        prop, pourquoi = charge + 2.5, "progression normale"
    prop = round(prop * 2) / 2
    return (f"Dernière séance : {dernier['series']}x{dernier['reps']} à {charge:.1f} kg le {dernier['date']}. "
            f"Mets {prop:.1f} kg cette fois, {pourquoi}.")


def rest_timer(seconds: int = 90) -> str:
    """Lance le minuteur de repos entre deux séries et prévient quand c'est fini.

    Args:
        seconds: Durée du repos en secondes.
    """
    s = max(10, min(600, int(seconds)))

    def attendre():
        time.sleep(s)
        _notifier("Repos terminé, série suivante.", "Musculation")

    threading.Thread(target=attendre, daemon=True).start()
    return f"Repos de {s} secondes lancé, je te préviens à la fin."


def log_weight(kg: float) -> str:
    """Enregistre le poids du jour pour suivre la tendance.

    Args:
        kg: Le poids en kilos.
    """
    d = _charge(MUSCU, {"seances": [], "poids": []})
    d["poids"] = [p for p in d.get("poids", []) if p["date"] != date.today().isoformat()]
    d["poids"].append({"date": date.today().isoformat(), "kg": float(kg)})
    d["poids"].sort(key=lambda p: p["date"])
    _sauve(MUSCU, d)
    return f"Poids du jour noté : {kg} kg."


def weight_trend(days: int = 30) -> str:
    """Montre l'évolution du poids sur la période, avec la tendance par semaine.

    Args:
        days: Nombre de jours à couvrir.
    """
    d = _charge(MUSCU, {"seances": [], "poids": []})
    limite = (date.today() - timedelta(days=max(2, int(days)))).isoformat()
    pesees = [p for p in d.get("poids", []) if p["date"] >= limite]
    if len(pesees) < 2:
        return "Pas assez de pesées enregistrées. Dis-moi ton poids régulièrement avec log_weight."
    debut, fin = pesees[0], pesees[-1]
    jours = (date.fromisoformat(fin["date"]) - date.fromisoformat(debut["date"])).days or 1
    delta = fin["kg"] - debut["kg"]
    lignes = [f"{datetime.fromisoformat(p['date']):%d/%m} : {p['kg']:.1f} kg" for p in pesees[-12:]]
    return (f"{len(pesees)} pesées sur {jours} jours :\n" + "\n".join(lignes)
            + f"\n\nTendance : {delta:+.1f} kg, soit {delta / jours * 7:+.2f} kg par semaine.")


def macros(weight_kg: float, goal: str = "seche") -> str:
    """Calcule les calories et les protéines conseillées selon le poids et l'objectif.

    Args:
        weight_kg: Poids du corps en kilos.
        goal: "seche" pour perdre du gras, "prise" pour prendre du muscle, "maintien" pour stabiliser.
    """
    p = float(weight_kg)
    g = _norm(goal)
    base = p * 31
    if g.startswith("sech") or "perdre" in g or "perte" in g:
        cal, prot, quoi = base - 450, p * 2.2, "sèche"
    elif g.startswith("pris") or "masse" in g or "gagner" in g:
        cal, prot, quoi = base + 350, p * 2.0, "prise de masse"
    else:
        cal, prot, quoi = base, p * 1.8, "maintien"
    lip = p * 0.9
    glu = max(0, (cal - prot * 4 - lip * 9) / 4)
    return (f"Pour {p:.0f} kg en {quoi} : environ {cal:.0f} calories par jour.\n"
            f"Protéines {prot:.0f} g, lipides {lip:.0f} g, glucides {glu:.0f} g.\n"
            f"Cela fait à peu près {prot / 25:.0f} portions de 25 g de protéines dans la journée.")


def add_shopping(item: str, quantity: str = "") -> str:
    """Ajoute un article à la liste de courses.

    Args:
        item: L'article à acheter.
        quantity: La quantité, par exemple "1 kg" ou "x2".
    """
    d = _charge(COURSES, {"liste": []})
    d["liste"].append({"article": item, "quantite": quantity, "fait": False})
    _sauve(COURSES, d)
    return f"Ajouté à la liste de courses : {item} {quantity}".strip()


def list_shopping() -> str:
    """Montre la liste de courses en cours."""
    d = _charge(COURSES, {"liste": []})
    restants = [a for a in d["liste"] if not a.get("fait")]
    if not restants:
        return "La liste de courses est vide."
    return f"{len(restants)} article(s) à acheter :\n" + "\n".join(
        f"- {a['article']} {a.get('quantite', '')}".rstrip() for a in restants)


def clear_shopping(item: str = "") -> str:
    """Retire un article de la liste de courses, ou vide toute la liste.

    Args:
        item: L'article à retirer. Vide = tout effacer.
    """
    d = _charge(COURSES, {"liste": []})
    if not item:
        n = len(d["liste"])
        d["liste"] = []
        _sauve(COURSES, d)
        return f"Liste de courses vidée, {n} article(s) retirés."
    avant = len(d["liste"])
    d["liste"] = [a for a in d["liste"] if _norm(item) not in _norm(a["article"])]
    _sauve(COURSES, d)
    return f"{avant - len(d['liste'])} article(s) retirés de la liste."


# --------------------------------------------------------------------------
# Santé
# --------------------------------------------------------------------------

def health_reminder(kind: str = "hydratation", every_minutes: int = 60, hours: int = 4) -> str:
    """Met en place un rappel régulier : boire, se lever, reposer les yeux, ou aller se coucher.

    Args:
        kind: "hydratation", "posture", "yeux" ou "coucher".
        every_minutes: Intervalle entre deux rappels, en minutes.
        hours: Pendant combien d'heures continuer.
    """
    textes = {
        "hydratation": "Pense à boire un verre d'eau.",
        "posture": "Redresse-toi et lève-toi une minute.",
        "yeux": "Regarde au loin vingt secondes, repose tes yeux.",
        "coucher": "Il est l'heure d'aller dormir.",
    }
    k = _norm(kind)
    message = next((v for cle, v in textes.items() if cle.startswith(k[:4])), textes["hydratation"])
    inter = max(5, int(every_minutes)) * 60
    fin = time.time() + max(1, int(hours)) * 3600

    def boucle():
        while time.time() < fin:
            time.sleep(inter)
            _notifier(message, "Jarvis")

    threading.Thread(target=boucle, daemon=True).start()
    return f"Rappel « {message} » toutes les {every_minutes} minutes pendant {hours} heures."


# --------------------------------------------------------------------------
# Maison connectée
# --------------------------------------------------------------------------

def _home_call(chemin: str, methode: str = "GET", data: dict | None = None):
    import requests

    url = getattr(config, "HOME_ASSISTANT_URL", "").rstrip("/")
    jeton = getattr(config, "HOME_ASSISTANT_TOKEN", "")
    if not (url and jeton):
        raise RuntimeError("maison non configurée")
    r = requests.request(methode, f"{url}/api/{chemin}", timeout=20,
                         headers={"Authorization": f"Bearer {jeton}", "Content-Type": "application/json"}, json=data)
    r.raise_for_status()
    return r.json()


def home_devices(filter: str = "") -> str:
    """Liste les appareils de la maison connectée et leur état : lumières, prises, capteurs, thermostat.

    Args:
        filter: Mot-clé pour filtrer, par exemple "lumiere" ou "salon". Vide = tout.
    """
    try:
        etats = _home_call("states")
    except RuntimeError:
        return ("La maison connectée n'est pas configurée. Ajoute HOME_ASSISTANT_URL et HOME_ASSISTANT_TOKEN "
                "dans config.py, avec l'adresse de ton Home Assistant et un jeton d'accès longue durée.")
    except Exception as exc:  # noqa: BLE001
        return f"Maison injoignable : {exc}"
    familles = ("light", "switch", "climate", "sensor", "binary_sensor", "lock", "vacuum", "media_player")
    lignes = []
    for e in etats:
        eid, etat = e.get("entity_id", ""), e.get("state", "")
        nom = e.get("attributes", {}).get("friendly_name", eid)
        if filter and _norm(filter) not in _norm(eid + " " + nom):
            continue
        if eid.split(".")[0] in familles:
            lignes.append(f"{etat:12} {nom} ({eid})")
    if not lignes:
        return f"Aucun appareil ne correspond à « {filter} »."
    return f"{len(lignes)} appareil(s) :\n" + "\n".join(sorted(lignes)[:40])


def home_control(device: str, action: str = "allumer") -> str:
    """Allume, éteint ou règle un appareil de la maison connectée.

    Args:
        device: Identifiant ou nom de l'appareil, par exemple "light.salon".
        action: "allumer", "eteindre", "basculer", ou une température pour un thermostat.
    """
    try:
        etats = _home_call("states")
    except RuntimeError:
        return "La maison connectée n'est pas configurée : ajoute HOME_ASSISTANT_URL et HOME_ASSISTANT_TOKEN."
    except Exception as exc:  # noqa: BLE001
        return f"Maison injoignable : {exc}"
    cible = None
    for e in etats:
        eid = e.get("entity_id", "")
        nom = e.get("attributes", {}).get("friendly_name", "")
        if _norm(device) == _norm(eid) or (nom and _norm(device) in _norm(nom)):
            cible = eid
            break
    if not cible:
        return f"Aucun appareil « {device} ». Utilise home_devices pour voir les noms exacts."
    domaine = cible.split(".")[0]
    a = _norm(action)
    try:
        if re.fullmatch(r"\d+(\.\d+)?", a):
            _home_call("services/climate/set_temperature", "POST", {"entity_id": cible, "temperature": float(a)})
            return f"Température de {cible} réglée sur {a} degrés."
        service = ("turn_off" if a.startswith(("etein", "coup", "ferm"))
                   else "toggle" if a.startswith("bascul") else "turn_on")
        _home_call(f"services/{domaine}/{service}", "POST", {"entity_id": cible})
        return f"{cible} : {action} effectué."
    except Exception as exc:  # noqa: BLE001
        return f"Échec : {exc}"


# --------------------------------------------------------------------------
# Téléphone Android
# --------------------------------------------------------------------------

def _adb(*args: str, timeout: float = 60) -> str:
    try:
        r = subprocess.run(["adb", *args], capture_output=True, text=True, timeout=timeout,
                           encoding="utf-8", errors="replace", creationflags=NO_WINDOW)
        return ((r.stdout or "").strip() or (r.stderr or "").strip())[:3000]
    except FileNotFoundError:
        return ("ADB n'est pas installé. Installe les outils Android (platform-tools) et branche le téléphone "
                "avec le débogage USB activé.")
    except Exception as exc:  # noqa: BLE001
        return f"Erreur : {exc}"


def phone_status() -> str:
    """Vérifie si un téléphone Android est branché et prêt, et donne son modèle et sa batterie."""
    devices = _adb("devices")
    if "device" not in devices.replace("List of devices", ""):
        return f"Aucun téléphone détecté. Branche-le en USB avec le débogage activé.\n{devices}"
    modele = _adb("shell", "getprop", "ro.product.model")
    niveau = re.search(r"level:\s*(\d+)", _adb("shell", "dumpsys", "battery"))
    return f"Téléphone : {modele}, batterie {niveau.group(1) if niveau else '?'} %."


def phone_screenshot() -> str:
    """Prend une capture de l'écran du téléphone et me la montre."""
    cible = config.WORKSPACE / "telephone.png"
    _adb("shell", "screencap", "-p", "/sdcard/_jarvis.png")
    _adb("pull", "/sdcard/_jarvis.png", str(cible), timeout=120)
    _adb("shell", "rm", "/sdcard/_jarvis.png")
    if cible.is_file():
        import tools as _t

        return f"{_t.IMAGE_MARK}{cible}]]\nCapture de l'écran du téléphone."
    return "La capture a échoué. Vérifie la connexion avec phone_status."


def phone_notifications() -> str:
    """Lit les notifications en cours sur le téléphone Android."""
    out = _adb("shell", "dumpsys", "notification", "--noredact")
    if out.startswith(("ADB", "Erreur")):
        return out
    titres = re.findall(r"android\.title=String \(([^)]{2,80})\)", out)
    textes = re.findall(r"android\.text=String \(([^)]{2,120})\)", out)
    if not titres:
        return "Aucune notification lisible sur le téléphone."
    return f"{len(titres)} notification(s) :\n" + "\n".join(
        f"- {t} : {x}" for t, x in zip(titres[:15], textes[:15]))


def phone_transfer(source: str, destination: str, to_phone: bool = False) -> str:
    """Transfère un fichier entre l'ordinateur et le téléphone Android.

    Args:
        source: Chemin du fichier de départ.
        destination: Chemin d'arrivée. Sur le téléphone, par exemple "/sdcard/Download/".
        to_phone: True pour envoyer vers le téléphone, False pour récupérer depuis le téléphone.
    """
    return _adb("push" if to_phone else "pull", source, destination, timeout=300)


def phone_mirror() -> str:
    """Affiche l'écran du téléphone sur l'ordinateur pour le piloter à la souris."""
    try:
        subprocess.Popen(["scrcpy"], creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0))
        return "Écran du téléphone affiché. Ferme la fenêtre pour arrêter."
    except FileNotFoundError:
        return "scrcpy n'est pas installé. Je peux l'installer avec install_software si tu veux."


# --------------------------------------------------------------------------
# Révisions
# --------------------------------------------------------------------------

def add_flashcard(subject: str, question: str, answer: str) -> str:
    """Crée une carte de révision qui reviendra à intervalles croissants jusqu'à être sue.

    Args:
        subject: Matière ou sujet.
        question: La question.
        answer: La réponse.
    """
    d = _charge(CARTES, {"cartes": []})
    d["cartes"].append({"sujet": subject, "question": question, "reponse": answer,
                        "niveau": 0, "prochaine": date.today().isoformat()})
    _sauve(CARTES, d)
    return f"Carte ajoutée en {subject}. Total : {len(d['cartes'])} cartes."


def review_flashcards(subject: str = "", count: int = 5) -> str:
    """Donne les cartes de révision à revoir aujourd'hui.

    Args:
        subject: Matière à réviser. Vide = toutes.
        count: Nombre de cartes.
    """
    d = _charge(CARTES, {"cartes": []})
    aujourdhui = date.today().isoformat()
    dues = [c for c in d["cartes"] if c.get("prochaine", aujourdhui) <= aujourdhui
            and (not subject or _norm(subject) in _norm(c["sujet"]))]
    if not dues:
        return f"Rien à réviser aujourd'hui{' en ' + subject if subject else ''}. {len(d['cartes'])} carte(s) au total."
    choisies = dues[:max(1, int(count))]
    lignes = [f"{i}. [{c['sujet']}] {c['question']}" for i, c in enumerate(choisies, 1)]
    return (f"{len(dues)} carte(s) à revoir, en voici {len(choisies)} :\n" + "\n".join(lignes)
            + "\n\nPose-les une par une, puis note le résultat avec grade_flashcard.")


def grade_flashcard(question: str, correct: bool = True) -> str:
    """Note si une carte de révision a été réussie, pour espacer ou rapprocher sa prochaine apparition.

    Args:
        question: Le début de la question de la carte.
        correct: True si la réponse était juste.
    """
    d = _charge(CARTES, {"cartes": []})
    for c in d["cartes"]:
        if _norm(question)[:40] in _norm(c["question"]):
            c["niveau"] = min(6, c.get("niveau", 0) + 1) if correct else 0
            jours = [0, 1, 3, 7, 16, 35, 90][c["niveau"]]
            c["prochaine"] = (date.today() + timedelta(days=jours)).isoformat()
            _sauve(CARTES, d)
            return (f"Carte notée réussie, prochaine révision dans {jours} jour(s)." if correct
                    else "Carte à revoir aujourd'hui.")
    return "Je n'ai pas retrouvé cette carte."


# --------------------------------------------------------------------------
# Quotidien
# --------------------------------------------------------------------------

def weather(city: str = "Mulhouse", days: int = 2) -> str:
    """Donne la météo précise d'une ville, maintenant et les jours suivants.

    Args:
        city: Nom de la ville.
        days: Nombre de jours, de 1 à 7.
    """
    try:
        import requests

        g = requests.get("https://geocoding-api.open-meteo.com/v1/search", timeout=20,
                         params={"name": city, "count": 1, "language": "fr"}).json()
        if not g.get("results"):
            return f"Ville inconnue : {city}"
        lieu = g["results"][0]
        r = requests.get("https://api.open-meteo.com/v1/forecast", timeout=20, params={
            "latitude": lieu["latitude"], "longitude": lieu["longitude"], "timezone": "auto",
            "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max",
            "current": "temperature_2m,weather_code,wind_speed_10m", "forecast_days": max(1, min(7, int(days))),
        }).json()
        codes = {0: "ciel dégagé", 1: "peu nuageux", 2: "partiellement nuageux", 3: "couvert", 45: "brouillard",
                 48: "brouillard givrant", 51: "bruine légère", 53: "bruine", 55: "bruine forte",
                 61: "pluie légère", 63: "pluie", 65: "forte pluie", 71: "neige légère", 73: "neige",
                 75: "forte neige", 80: "averses", 81: "averses", 82: "fortes averses", 95: "orage",
                 96: "orage avec grêle", 99: "orage violent"}
        cur = r.get("current", {})
        out = [f"{lieu['name']} maintenant : {cur.get('temperature_2m')} degrés, "
               f"{codes.get(cur.get('weather_code'), '?')}, vent {cur.get('wind_speed_10m')} km/h."]
        d = r.get("daily", {})
        jours_fr = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
        for i, jour in enumerate(d.get("time", [])):
            dt = date.fromisoformat(jour)
            nom = "aujourd'hui" if i == 0 else ("demain" if i == 1 else jours_fr[dt.weekday()])
            out.append(f"{nom} : de {d['temperature_2m_min'][i]:.0f} à {d['temperature_2m_max'][i]:.0f} degrés, "
                       f"{codes.get(d['weather_code'][i], '?')}, {d['precipitation_probability_max'][i]} % de pluie.")
        return "\n".join(out)
    except Exception as exc:  # noqa: BLE001
        return f"Erreur météo : {exc}"


def itinerary(destination: str, departure: str = "", mode: str = "voiture") -> str:
    """Ouvre l'itinéraire vers une destination pour connaître la durée du trajet.

    Args:
        destination: Adresse ou lieu d'arrivée.
        departure: Point de départ. Vide = position actuelle.
        mode: "voiture", "pied", "velo" ou "transports".
    """
    import webbrowser
    from urllib.parse import quote

    modes = {"voiture": "driving", "pied": "walking", "velo": "bicycling", "transports": "transit"}
    m = modes.get(_norm(mode), "driving")
    url = (f"https://www.google.com/maps/dir/?api=1&destination={quote(destination)}&travelmode={m}"
           + (f"&origin={quote(departure)}" if departure else ""))
    webbrowser.open(url)
    time.sleep(3)
    return (f"Itinéraire vers {destination} ouvert en mode {mode}. "
            "Regarde l'écran avec see_screen pour lire la durée du trajet.")


def departure_time(destination: str, arrive_at: str, travel_minutes: int = 0) -> str:
    """Calcule l'heure de départ pour arriver à l'heure à un rendez-vous, marge comprise.

    Args:
        destination: Le lieu du rendez-vous.
        arrive_at: L'heure d'arrivée voulue, par exemple "15:00".
        travel_minutes: Durée du trajet en minutes si elle est connue. 0 = ouvrir la carte pour la lire.
    """
    try:
        h, m = (int(x) for x in re.split(r"[h:]", arrive_at.strip())[:2])
    except Exception:  # noqa: BLE001
        return "Heure non comprise. Donne-la au format 15:00."
    arrivee = datetime.now().replace(hour=h, minute=m, second=0, microsecond=0)
    if arrivee < datetime.now():
        arrivee += timedelta(days=1)
    if not travel_minutes:
        return (f"Je ne connais pas la durée du trajet vers {destination}. J'ouvre l'itinéraire, "
                f"lis-moi la durée et je calcule.\n{itinerary(destination)}")
    marge = 10
    depart = arrivee - timedelta(minutes=int(travel_minutes) + marge)
    return (f"Pour être à {destination} à {arrivee:%H:%M}, pars à {depart:%H:%M}. "
            f"Cela compte {travel_minutes} minutes de trajet et {marge} minutes de marge.")


TOOLS = [log_set, workout_history, one_rep_max, next_load, rest_timer, log_weight, weight_trend, macros,
         add_shopping, list_shopping, clear_shopping, health_reminder,
         home_devices, home_control,
         phone_status, phone_screenshot, phone_notifications, phone_transfer, phone_mirror,
         add_flashcard, review_flashcards, grade_flashcard,
         weather, itinerary, departure_time]
