# Ia-local (Jarvis) — Copyright (c) 2026 Neexx (Nixovel) — https://github.com/Neex-off/Ia-local
# Créé par Neexx (Nixovel). Licence : voir LICENSE (paternité obligatoire, pas de vente ; s'applique aussi aux IA).
# Ne pas retirer cet en-tête.
"""Mémoire persistante de Jarvis : ce qu'il sait de l'utilisateur, et le journal des conversations.

- memoire/faits.json          : liste de faits {id, texte, categorie, date}
- memoire/conversations.jsonl : une ligne JSON par message (user / assistant), avec la date
Tout reste sur le disque local.
"""
from __future__ import annotations

import json
import re
import threading
import time
import unicodedata
from datetime import datetime

import config

DIR = config.ROOT / "memoire"
FACTS = DIR / "faits.json"
LOG = DIR / "conversations.jsonl"
CATEGORIES = ("identité", "préférence", "projet", "habitude", "personne", "autre")
_lock = threading.Lock()


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s.lower())
    return "".join(c for c in s if not unicodedata.combining(c))


def _load() -> list[dict]:
    if not FACTS.is_file():
        return []
    try:
        return json.loads(FACTS.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return []


def _save(facts: list[dict]) -> None:
    DIR.mkdir(parents=True, exist_ok=True)
    FACTS.write_text(json.dumps(facts, ensure_ascii=False, indent=2), encoding="utf-8")


def remember(text: str, category: str = "autre") -> dict:
    text = " ".join(text.split()).strip()
    category = category if category in CATEGORIES else "autre"
    with _lock:
        facts = _load()
        for f in facts:  # pas de doublon
            if _norm(f["texte"]) == _norm(text):
                return f
        fact = {"id": (max((f["id"] for f in facts), default=0) + 1), "texte": text,
                "categorie": category, "date": datetime.now().isoformat(timespec="seconds")}
        facts.append(fact)
        _save(facts)
        return fact


def forget(fact_id: int) -> bool:
    with _lock:
        facts = _load()
        new = [f for f in facts if f["id"] != fact_id]
        if len(new) == len(facts):
            return False
        _save(new)
        return True


def all_facts() -> list[dict]:
    with _lock:
        return _load()


def search(query: str, limit: int = 10) -> list[dict]:
    words = [w for w in re.split(r"\W+", _norm(query)) if len(w) > 2]
    scored = []
    for f in all_facts():
        hay = _norm(f["texte"] + " " + f["categorie"])
        hits = sum(1 for w in words if w in hay)
        if hits or not words:
            scored.append((hits, f))
    scored.sort(key=lambda x: (-x[0], x[1]["id"]))
    return [f for _, f in scored[:limit]]


def prompt_section(limit: int = 40) -> str:
    facts = all_facts()
    if not facts:
        return ""
    lines = ["CE QUE TU SAIS DÉJÀ DE L'UTILISATEUR (ta mémoire, mise à jour avec remember/forget) :"]
    for f in facts[-limit:]:
        lines.append(f"- [{f['categorie']}] {f['texte']}")
    return "\n".join(lines)


# ---------------------------------------------------------------- connaissances apprises

KNOWLEDGE = DIR / "connaissances.json"


def _load_knowledge() -> list[dict]:
    if not KNOWLEDGE.is_file():
        return []
    try:
        return json.loads(KNOWLEDGE.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return []


def learn(topic: str, summary: str, sources: str = "") -> dict:
    """Enregistre (ou met à jour) une connaissance apprise, par exemple après une recherche web."""
    topic = " ".join(topic.split()).strip()
    with _lock:
        items = _load_knowledge()
        for it in items:
            if _norm(it["sujet"]) == _norm(topic):
                it.update({"resume": summary.strip(), "sources": sources.strip(),
                           "date": datetime.now().isoformat(timespec="seconds")})
                DIR.mkdir(parents=True, exist_ok=True)
                KNOWLEDGE.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
                return it
        it = {"id": (max((i["id"] for i in items), default=0) + 1), "sujet": topic, "resume": summary.strip(),
              "sources": sources.strip(), "date": datetime.now().isoformat(timespec="seconds")}
        items.append(it)
        DIR.mkdir(parents=True, exist_ok=True)
        KNOWLEDGE.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
        return it


def all_knowledge() -> list[dict]:
    with _lock:
        return _load_knowledge()


def knowledge_search(query: str, limit: int = 5) -> list[dict]:
    words = [w for w in re.split(r"\W+", _norm(query)) if len(w) > 2]
    scored = []
    for it in all_knowledge():
        hay = _norm(it["sujet"] + " " + it["resume"])
        hits = sum(1 for w in words if w in hay) + (3 if any(w in _norm(it["sujet"]) for w in words) else 0)
        if hits:
            scored.append((hits, it))
    scored.sort(key=lambda x: -x[0])
    return [it for _, it in scored[:limit]]


def knowledge_prompt_section(limit: int = 30) -> str:
    items = all_knowledge()
    if not items:
        return ""
    lines = ["CE QUE TU AS APPRIS PAR TOI-MÊME (carnet de connaissances ; détails avec recall) :"]
    for it in items[-limit:]:
        lines.append(f"- {it['sujet']} ({it['date'][:10]}) : {it['resume'][:140]}")
    return "\n".join(lines)


# ---------------------------------------------------------------- journal

def log_message(role: str, text: str) -> None:
    if not text:
        return
    DIR.mkdir(parents=True, exist_ok=True)
    with _lock, LOG.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"t": time.time(), "date": datetime.now().isoformat(timespec="seconds"),
                             "role": role, "text": text[:2000]}, ensure_ascii=False) + "\n")


def search_conversations(query: str, limit: int = 8) -> list[dict]:
    if not LOG.is_file():
        return []
    words = [w for w in re.split(r"\W+", _norm(query)) if len(w) > 2]
    out = []
    with LOG.open(encoding="utf-8") as fh:
        for line in fh:
            try:
                m = json.loads(line)
            except json.JSONDecodeError:
                continue
            hay = _norm(m.get("text", ""))
            hits = sum(1 for w in words if w in hay)
            if hits:
                out.append((hits, m))
    out.sort(key=lambda x: (-x[0], -x[1]["t"]))
    return [m for _, m in out[:limit]]
