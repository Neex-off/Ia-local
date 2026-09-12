# Ia-local (Jarvis) — Copyright (c) 2026 Neexx (Nixovel) — https://github.com/Neex-off/Ia-local
# Créé par Neexx (Nixovel). Licence : voir LICENSE (paternité obligatoire, pas de vente ; s'applique aussi aux IA).
# Ne pas retirer cet en-tête.
"""Données des vues de l'interface : journée, journal des actions, sport.

Chaque fonction renvoie un dict prêt à envoyer à la page (ui/index.html), qui le dessine.
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import config

MEM = config.ROOT / "memoire"


def _json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return default


def _jours(d: str) -> int:
    try:
        return (date.fromisoformat(d[:10]) - date.today()).days
    except Exception:  # noqa: BLE001
        return 9999


# --------------------------------------------------------------------------
# Journée
# --------------------------------------------------------------------------

def journee(meteo: bool = True) -> dict:
    """Agenda du jour et des 3 prochains jours, échéances, anniversaires, météo, sport, sommeil, humeur, activité de Jarvis."""
    import agenda

    auj = date.today()
    evenements = list(agenda.between(auj, auj + timedelta(days=3)))
    echeances = []
    for e in _json(MEM / "echeances.json", []):
        n = _jours(e.get("date", ""))
        if 0 <= n <= 30:
            echeances.append({"nom": e["nom"], "date": e["date"], "dans": n})
    dates = []
    for d in _json(MEM / "dates.json", []):
        try:
            m, j = int(d["date"][5:7]), int(d["date"][8:10])
            cible = date(auj.year, m, j)
            if cible < auj:
                cible = date(auj.year + 1, m, j)
            n = (cible - auj).days
            if n <= 30:
                dates.append({"nom": d["nom"], "type": d.get("type", ""), "date": cible.isoformat(), "dans": n})
        except Exception:  # noqa: BLE001
            continue
    meteo_txt = ""
    if meteo:
        try:
            from outils_vie import weather

            meteo_txt = weather(getattr(config, "CITY", "") or "Mulhouse", 2)[:600]
        except Exception:  # noqa: BLE001
            meteo_txt = ""
    sport, humeur = None, None
    try:
        import journal

        s = journal.entries(30, "sport")
        if s:
            sport = {"date": s[-1]["date"], "texte": s[-1]["texte"][:160]}
        h = journal.entries(14, "humeur")
        if h:
            humeur = {"date": h[-1]["date"], "texte": h[-1]["texte"][:160]}
    except Exception:  # noqa: BLE001
        pass
    sommeil = _json(MEM / "sommeil.json", [])
    nuit = sommeil[-1] if sommeil else None
    try:
        import noyau

        actions = noyau.lire_audit(n=500, depuis_heures=24)
        n_actions = len(actions)
        erreurs = sum(1 for a in actions if a.get("statut") in ("erreur", "bloquée", "échec"))
    except Exception:  # noqa: BLE001
        n_actions, erreurs = 0, 0
    return {"today": auj.isoformat(), "today_label": agenda.today_line().split(",")[0], "events": evenements,
            "echeances": sorted(echeances, key=lambda x: x["dans"]), "dates": sorted(dates, key=lambda x: x["dans"]),
            "meteo": meteo_txt, "sport": sport, "humeur": humeur, "sommeil": nuit, "actions": n_actions, "erreurs": erreurs}


def journee_resume(p: dict) -> str:
    """Phrase pour le modèle."""
    parts = [f"Aujourd'hui {p['today_label']}."]
    auj = [e for e in p["events"] if e["date"] == p["today"]]
    detail = " : " + ", ".join(f"{e.get('heure', '')} {e['titre']}".strip() for e in auj) if auj else ""
    parts.append(f"{len(auj)} rendez-vous aujourd'hui{detail}.")
    if p["echeances"]:
        parts.append("Échéances : " + ", ".join(f"{e['nom']} dans {e['dans']} j" for e in p["echeances"][:4]) + ".")
    if p["dates"]:
        parts.append("Dates : " + ", ".join(f"{d['nom']} dans {d['dans']} j" for d in p["dates"][:3]) + ".")
    if p["meteo"]:
        parts.append("Météo : " + p["meteo"].splitlines()[0][:120])
    if p["sport"]:
        parts.append(f"Dernière séance le {p['sport']['date']}.")
    return " ".join(parts)


# --------------------------------------------------------------------------
# Journal des actions
# --------------------------------------------------------------------------

def journal_actions(count: int = 40) -> dict:
    import noyau

    lignes = noyau.lire_audit(n=count)
    stats = noyau.statistiques(7)
    return {"actions": lignes, "arret": noyau.ARRET.is_set(), "prive": noyau.est_prive(),
            "semaine": {"actions": stats["actions"], "statuts": stats["statuts"], "top": stats["par_outil"][:6]}}


# --------------------------------------------------------------------------
# Sport
# --------------------------------------------------------------------------

def sport() -> dict:
    try:
        from outils_vie import _toutes_seances, next_load
    except Exception:  # noqa: BLE001
        return {"exercices": [], "poids": [], "photos": [], "seances": 0, "semaine": 0, "derniere": ""}
    seances = _toutes_seances()
    par_ex: dict[str, list] = {}
    for s in seances:
        par_ex.setdefault(s["exercice"].strip().lower(), []).append(s)
    exercices = []
    for nom, liste in sorted(par_ex.items(), key=lambda x: -len(x[1])):
        liste = sorted(liste, key=lambda x: x["date"])
        points = [{"date": s["date"], "charge": s["charge"], "series": s["series"], "reps": s["reps"], "ressenti": s.get("ressenti", "")} for s in liste[-20:]]
        conseil = ""
        try:
            conseil = next_load(nom)[:200]
        except Exception:  # noqa: BLE001
            pass
        exercices.append({"nom": nom, "n": len(liste), "max": max(s["charge"] for s in liste), "dernier": points[-1], "points": points, "conseil": conseil})
    muscu = _json(MEM / "muscu.json", {})
    poids = muscu.get("poids", [])[-30:] if isinstance(muscu, dict) else []
    dossier = MEM / "progression"
    photos = sorted([f.name for f in dossier.glob("*") if f.suffix.lower() in (".jpg", ".jpeg", ".png")]) if dossier.exists() else []
    jours = sorted({s["date"] for s in seances})
    semaine = sum(1 for d in jours if _jours(d) >= -7)
    return {"exercices": exercices[:12], "poids": poids, "photos": photos, "seances": len(jours), "semaine": semaine,
            "derniere": jours[-1] if jours else ""}


def sport_resume(p: dict) -> str:
    if not p["exercices"]:
        return "Aucune séance enregistrée pour l'instant."
    top = ", ".join(f"{e['nom']} {e['dernier']['charge']:g} kg (max {e['max']:g})" for e in p["exercices"][:4])
    return f"{p['seances']} jours de séance enregistrés, {p['semaine']} cette semaine, dernière le {p['derniere']}. {top}."
