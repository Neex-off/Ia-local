# Ia-local (Jarvis) — Copyright (c) 2026 Neexx (Nixovel) — https://github.com/Neex-off/Ia-local
# Créé par Neexx (Nixovel). Licence : voir LICENSE (paternité obligatoire, pas de vente ; s'applique aussi aux IA).
# Ne pas retirer cet en-tête.
"""Journal de vie de l'utilisateur, tenu par Jarvis : séances de sport, journées, humeur (memoire/journal.json).

C'est la « conscience » de Jarvis : il sait ce qui s'est passé récemment, remarque ce qui manque (pas de séance
depuis longtemps, journée pas racontée) et pose la question de lui-même le soir.
"""
from __future__ import annotations

import json
import threading
from datetime import date, datetime, timedelta

import config

FILE = config.ROOT / "memoire" / "journal.json"
_lock = threading.Lock()
KINDS = ("sport", "journee", "humeur", "autre")


def _load() -> dict:
    if not FILE.is_file():
        return {"entrees": [], "bilan_pose": ""}
    try:
        data = json.loads(FILE.read_text(encoding="utf-8"))
        data.setdefault("entrees", [])
        data.setdefault("bilan_pose", "")
        return data
    except Exception:  # noqa: BLE001
        return {"entrees": [], "bilan_pose": ""}


def _save(data: dict) -> None:
    FILE.parent.mkdir(parents=True, exist_ok=True)
    FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def add(kind: str, text: str) -> dict:
    kind = (kind or "autre").strip().lower()
    if kind not in KINDS:
        kind = "autre"
    now = datetime.now()
    with _lock:
        data = _load()
        entry = {"id": max((e["id"] for e in data["entrees"]), default=0) + 1, "date": now.date().isoformat(),
                 "heure": now.strftime("%H:%M"), "type": kind, "texte": " ".join(text.split())}
        data["entrees"].append(entry)
        _save(data)
        return entry


def entries(days: int = 7, kind: str = "") -> list[dict]:
    since = (date.today() - timedelta(days=max(0, days - 1))).isoformat()
    with _lock:
        data = _load()
    return [e for e in data["entrees"] if e["date"] >= since and (not kind or e["type"] == kind)]


def fmt(e: dict) -> str:
    d = date.fromisoformat(e["date"])
    return f"{d.strftime('%d/%m')} {e['heure']} [{e['type']}] {e['texte']}"


def last_sport() -> dict | None:
    with _lock:
        data = _load()
    sport = [e for e in data["entrees"] if e["type"] == "sport"]
    return sport[-1] if sport else None


def days_since_sport() -> int | None:
    last = last_sport()
    if last is None:
        return None
    return (date.today() - date.fromisoformat(last["date"])).days


def today_has(kind: str) -> bool:
    today = date.today().isoformat()
    with _lock:
        data = _load()
    return any(e["date"] == today and e["type"] == kind for e in data["entrees"])


def context_line() -> str:
    """Une ligne glissée dans chaque message pour que Jarvis « ait conscience » de la vie de l'utilisateur."""
    parts = []
    n = days_since_sport()
    if n is None:
        parts.append("salle de sport : aucune séance notée pour l'instant")
    elif n == 0:
        parts.append("salle de sport : séance aujourd'hui")
    else:
        parts.append(f"salle de sport : dernière séance il y a {n} jour(s)")
    recent = entries(3)
    if recent:
        parts.append("journal récent : " + " ; ".join(fmt(e) for e in recent[-4:]))
    parts.append("journée d'aujourd'hui " + ("déjà racontée" if today_has("journee") else "pas encore racontée"))
    return "Conscience : " + ". ".join(parts) + "."


def checkin_question(now: datetime | None = None) -> str | None:
    """Le soir (config.CHECKIN_HOUR), une fois par jour, si la journée n'a pas été racontée : la question à poser.
    Marque la question comme posée."""
    now = now or datetime.now()
    if config.CHECKIN_HOUR is None or now.hour < config.CHECKIN_HOUR:
        return None
    today = now.date().isoformat()
    with _lock:
        data = _load()
        if data.get("bilan_pose") == today:
            return None
        if any(e["date"] == today and e["type"] == "journee" for e in data["entrees"]):
            return None
        data["bilan_pose"] = today
        _save(data)
    n = days_since_sport()
    sport = ""
    if n is None or n >= 2:
        sport = " Êtes-vous passé à la salle de sport ?"
    return f"{config.USER_TITLE.capitalize()}, comment s'est passée votre journée ?{sport}"
