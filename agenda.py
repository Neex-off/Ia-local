# Ia-local (Jarvis) — Copyright (c) 2026 Neexx (Nixovel) — https://github.com/Neex-off/Ia-local
# Créé par Neexx (Nixovel). Licence : voir LICENSE (paternité obligatoire, pas de vente ; s'applique aussi aux IA).
# Ne pas retirer cet en-tête.
"""Agenda local de Jarvis : rendez-vous et rappels dans memoire/agenda.json.

Un événement = {id, titre, date "AAAA-MM-JJ", heure "HH:MM" ou "", note, cree}.
"""
from __future__ import annotations

import json
import re
import threading
import unicodedata
from datetime import date, datetime, timedelta

import config

FILE = config.ROOT / "memoire" / "agenda.json"
_lock = threading.Lock()
JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre", "décembre"]


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s.lower())
    return "".join(c for c in s if not unicodedata.combining(c))


def _load() -> list[dict]:
    if not FILE.is_file():
        return []
    try:
        return json.loads(FILE.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return []


def _save(events: list[dict]) -> None:
    FILE.parent.mkdir(parents=True, exist_ok=True)
    events.sort(key=lambda e: (e["date"], e.get("heure") or "99:99"))
    FILE.write_text(json.dumps(events, ensure_ascii=False, indent=2), encoding="utf-8")


def all_events() -> list[dict]:
    with _lock:
        return _load()


def add(title: str, day: str, time_: str = "", note: str = "") -> dict:
    day = normalize_date(day)
    time_ = normalize_time(time_)
    with _lock:
        events = _load()
        ev = {"id": max((e["id"] for e in events), default=0) + 1, "titre": " ".join(title.split()),
              "date": day, "heure": time_, "note": note.strip(), "cree": datetime.now().isoformat(timespec="seconds")}
        events.append(ev)
        _save(events)
        return ev


def remove(query: str) -> list[dict]:
    """Supprime par numéro, ou tous les événements dont le titre (ou la date) correspond au texte."""
    with _lock:
        events = _load()
        if query.strip().isdigit():
            gone = [e for e in events if e["id"] == int(query)]
        else:
            q = _norm(query)
            gone = [e for e in events if q and (q in _norm(e["titre"]) or q == e["date"])]
        if gone:
            _save([e for e in events if e not in gone])
        return gone


def between(start: date, end: date) -> list[dict]:
    return [e for e in all_events() if start.isoformat() <= e["date"] <= end.isoformat()]


def upcoming(days: int = 14) -> list[dict]:
    today = date.today()
    return between(today, today + timedelta(days=days))


def normalize_date(s: str) -> str:
    """Accepte AAAA-MM-JJ, JJ/MM/AAAA, JJ/MM ; renvoie AAAA-MM-JJ (lève ValueError sinon)."""
    s = s.strip()
    m = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})$", s)
    if m:
        return date(int(m[1]), int(m[2]), int(m[3])).isoformat()
    m = re.match(r"^(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?$", s)
    if m:
        y = int(m[3]) if m[3] else date.today().year
        if y < 100:
            y += 2000
        d = date(y, int(m[2]), int(m[1]))
        if not m[3] and d < date.today():
            d = date(y + 1, int(m[2]), int(m[1]))
        return d.isoformat()
    raise ValueError(f"date non comprise : {s!r} (attendu AAAA-MM-JJ)")


def normalize_time(s: str) -> str:
    s = (s or "").strip().lower().replace("h", ":").rstrip(":")  # « 15h » -> « 15 », « 15h30 » -> « 15:30 »
    if not s:
        return ""
    m = re.match(r"^(\d{1,2})(?::(\d{2}))?$", s)
    if not m:
        raise ValueError(f"heure non comprise : {s!r} (attendu HH:MM)")
    return f"{int(m[1]):02d}:{int(m[2] or 0):02d}"


def fmt(ev: dict) -> str:
    d = date.fromisoformat(ev["date"])
    when = f"{JOURS[d.weekday()]} {d.day} {MOIS[d.month - 1]}"
    if d.year != date.today().year:
        when += f" {d.year}"
    if ev.get("heure"):
        when += f" à {ev['heure'].replace(':', 'h')}"
    note = f" ({ev['note']})" if ev.get("note") else ""
    return f"n°{ev['id']} {when} : {ev['titre']}{note}"


def today_line() -> str:
    now = datetime.now()
    return f"{JOURS[now.weekday()]} {now.day} {MOIS[now.month - 1]} {now.year}, {now.strftime('%H:%M')} (date ISO {now.date().isoformat()})"


def due_reminders(now: datetime | None = None) -> list[str]:
    """Rappels à dire maintenant (et marqués comme dits) : X minutes avant un rendez-vous à heure fixe,
    et le point du matin (config.MORNING_BRIEF_HOUR) pour la journée, événements sans heure compris."""
    now = now or datetime.now()
    out: list[str] = []
    with _lock:
        events = _load()
        changed = False
        today = now.date().isoformat()
        for e in events:
            done = e.setdefault("rappels", [])
            if e["date"] == today and e.get("heure"):
                h, m = map(int, e["heure"].split(":"))
                start = now.replace(hour=h, minute=m, second=0, microsecond=0)
                delta = (start - now).total_seconds() / 60
                if delta < -1:
                    continue  # rendez-vous passé
                pending = [mins for mins in config.REMINDER_MINUTES if f"m{mins}" not in done and delta <= mins]
                if pending:
                    left = max(0, round(delta))
                    when = "maintenant" if left <= 1 else f"dans {left} minutes"
                    out.append(f"Rappel : {e['titre']} {when}, à {e['heure'].replace(':', 'h')}." + (f" {e['note']}." if e.get("note") else ""))
                    done.extend(f"m{mins}" for mins in pending)  # toutes les fenêtres déjà atteintes sont dites
                    changed = True
        # point du matin : une fois par jour, dès que l'heure est passée
        brief_key = f"brief{today}"
        if now.hour >= config.MORNING_BRIEF_HOUR:
            todays = [e for e in events if e["date"] == today]
            if todays and not any(brief_key in e.get("rappels", []) for e in todays):
                parts = []
                for e in sorted(todays, key=lambda x: x.get("heure") or "99"):
                    parts.append((f"à {e['heure'].replace(':', 'h')}, " if e.get("heure") else "") + e["titre"])
                    e.setdefault("rappels", []).append(brief_key)
                out.insert(0, "Programme du jour : " + " ; ".join(parts) + ".")
                changed = True
        if changed:
            _save(events)
    return out


def view_payload() -> dict:
    """Ce que reçoit l'interface : tous les événements + aujourd'hui."""
    return {"today": date.today().isoformat(), "events": all_events()}
