# Ia-local (Jarvis) — Copyright (c) 2026 Neexx (Nixovel) — https://github.com/Neex-off/Ia-local
# Créé par Neexx (Nixovel). Licence : voir LICENSE (paternité obligatoire, pas de vente ; s'applique aussi aux IA).
# Ne pas retirer cet en-tête.
"""Noyau : journal d'audit, permissions à trois niveaux, annulation, arrêt d'urgence, modules,
mode privé, statistiques et personnalités.

Tout ce qui est ici est toujours présent, quel que soit le jeu de boîtes à outils ouvert.
Le reste du programme n'a besoin que de trois points d'entrée :
    - before_call(nom, args)  -> None si l'outil peut s'exécuter, sinon le texte à renvoyer au modèle
    - after_call(nom, args, resultat, duree)
    - hooks : callables posés par jarvis_core (arrêter la parole, couper le micro, dire une phrase)
"""
from __future__ import annotations

import json
import re
import threading
import time
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable

import config

MEM = config.ROOT / "memoire"
AUDIT = MEM / "audit.jsonl"
ETAT = MEM / "noyau.json"
_LOCK = threading.Lock()

hooks: dict[str, Callable] = {}          # posés par jarvis_core : "stop", "mic", "dire"

# --------------------------------------------------------------------------
# Permissions : vert = direct, orange = confirmation, rouge = interdit.
# La confirmation ne s'applique que si config.CONFIRM_SENSITIVE est vrai (l'utilisateur a choisi
# l'exécution directe par défaut) ; un outil orange appelé une première fois renvoie alors une
# demande de confirmation, et le même appel dans les trois minutes suivantes passe.
# --------------------------------------------------------------------------
ORANGE = {
    "shutdown_pc", "delete_forever", "registry_write", "install_windows_updates", "restore_point_restore",
    "firewall_rule", "set_dns", "set_proxy", "block_sites", "cut_network", "send_email", "send_message",
    "git_push", "deploy_site", "rollback_deploy", "uninstall_software", "kill_process", "db_write",
    "remove_model", "refund_payment", "send_invoice", "encrypt_path", "sync_folders", "auto_backup",
    "windows_features", "scheduled_tasks", "default_apps", "display_settings", "update_drivers",
    "repair_system", "wifi_passwords", "self_update", "install_module", "create_tool", "import_config",
    "toggle_module", "install_apk", "send_sms", "publish_reply", "schedule_post", "contact_prospects",
    "send_contract", "presence_simulation", "moderate_discord", "ota_update", "submit_build",
    "renew_tls", "reverse_proxy", "deploy_env", "restore_backup", "git_init", "git_prune_branches",
    "create_pull_request", "create_issues", "git_release", "fill_pdf_form", "photos_by_date",
    "replace_in_files", "record_macro", "run_elevated", "remote_control",
}

# Ce qui est interdit dans tous les cas, même via run_command / ssh_run.
_ROUGE = re.compile(
    r"(\bformat\s+[a-z]:|\bdiskpart\b|\bclean\s+all\b|\bbcdedit\b|\bmanage-bde\b.*(-off|-on|-lock)|"
    r"\bnet\s+user\b.*/add|\bnet\s+localgroup\s+administra|Add-LocalGroupMember|"
    r"Set-MpPreference\s+-Disable|netsh\s+advfirewall\s+set\s+\w+\s+state\s+off|"
    r"EnableLUA|\breg\s+delete\s+HKLM\\SYSTEM|rm\s+-rf\s+/(\s|$)|\bmkfs\b|\bdd\s+if=|"
    r"vssadmin\s+delete\s+shadows|cipher\s+/w|\bsystemreset\b|Reset-Computer|"
    r"Windows\\System32\\.*\b(del|rm|Remove-Item)\b|Get-ChildItem.*Cookies|Login Data|"
    r"\\Local State\b|credential\s*manager|vaultcmd|\bmimikatz\b|\blsass\b)",
    re.I)

_pending: dict[str, float] = {}


def _etat() -> dict:
    try:
        return json.loads(ETAT.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def _sauve(e: dict) -> None:
    MEM.mkdir(parents=True, exist_ok=True)
    ETAT.write_text(json.dumps(e, ensure_ascii=False, indent=2), encoding="utf-8")


def niveau(nom: str) -> str:
    perso = _etat().get("permissions", {})
    if nom in perso:
        return perso[nom]
    return "orange" if nom in ORANGE else "vert"


def set_niveau(nom: str, niv: str) -> None:
    e = _etat()
    e.setdefault("permissions", {})[nom] = niv
    _sauve(e)


def _cle(nom: str, args: dict) -> str:
    try:
        return nom + json.dumps(args, sort_keys=True, ensure_ascii=False)
    except Exception:  # noqa: BLE001
        return nom + str(args)


def before_call(nom: str, args: dict) -> str | None:
    """None si l'outil peut tourner ; sinon le message à donner au modèle à la place."""
    if ARRET.is_set() and nom not in ("resume_all", "what_did_you_do", "self_check"):
        return "ARRÊT D'URGENCE actif : plus aucune action tant que l'utilisateur n'a pas dit de reprendre (resume_all)."
    niv = niveau(nom)
    if niv == "rouge":
        audit(nom, args, "bloquée", "niveau rouge")
        return f"Interdit : « {nom} » est classé rouge, je ne le ferai dans aucun cas."
    texte = " ".join(str(v) for v in args.values()) if args else ""
    if nom in ("run_command", "ssh_run", "run_elevated") and _ROUGE.search(texte):
        audit(nom, args, "bloquée", "commande interdite")
        return ("Interdit : cette commande touche à quelque chose que je ne dois jamais faire (partitions, "
                "comptes administrateur, antivirus, pare-feu, UAC, chiffrement, mots de passe enregistrés, "
                "fichiers système). Dis-le franchement à l'utilisateur.")
    if niv == "orange" and getattr(config, "CONFIRM_SENSITIVE", False):
        k = _cle(nom, args)
        t = _pending.get(k, 0)
        if time.time() - t < 180:
            _pending.pop(k, None)
            return None
        _pending[k] = time.time()
        audit(nom, args, "en attente", "confirmation demandée")
        return (f"CONFIRMATION REQUISE : « {nom} » est une action sensible. Explique en une phrase ce que tu vas "
                "faire, demande « je confirme ? », et si l'utilisateur dit oui, rappelle exactement le même outil "
                "avec les mêmes arguments dans les trois minutes.")
    return None


def after_call(nom: str, args: dict, resultat: str, duree: float) -> None:
    r = (resultat or "").strip()
    bas = r.lower()
    statut = "ok"
    if bas.startswith(("erreur", "error")):
        statut = "erreur"
    elif bas.startswith("interdit"):
        statut = "refusée"
    elif bas.startswith(("pas ferm", "aucun élément", "aucune fen", "impossible", "introuvable")):
        statut = "échec"
    audit(nom, args, statut, r[:160], duree)


# --------------------------------------------------------------------------
# Journal d'audit
# --------------------------------------------------------------------------

def audit(nom: str, args: dict, statut: str, detail: str = "", duree: float = 0.0) -> None:
    if est_prive() and nom != "private_mode":
        return
    try:
        MEM.mkdir(parents=True, exist_ok=True)
        propre = {k: ("••••••••" if k in ("password", "mot_de_passe", "token", "secret") else v)
                  for k, v in (args or {}).items()}
        ligne = {"t": datetime.now().isoformat(timespec="seconds"), "outil": nom, "args": propre,
                 "statut": statut, "detail": detail[:160], "duree": round(duree, 2)}
        with _LOCK, AUDIT.open("a", encoding="utf-8") as f:
            f.write(json.dumps(ligne, ensure_ascii=False) + "\n")
    except Exception:  # noqa: BLE001
        pass


def lire_audit(n: int = 20, depuis_heures: float = 0) -> list[dict]:
    try:
        lignes = AUDIT.read_text(encoding="utf-8").splitlines()
    except Exception:  # noqa: BLE001
        return []
    out = []
    limite = datetime.now() - timedelta(hours=depuis_heures) if depuis_heures else None
    for l in reversed(lignes):
        try:
            d = json.loads(l)
        except Exception:  # noqa: BLE001
            continue
        if limite and datetime.fromisoformat(d["t"]) < limite:
            break
        out.append(d)
        if len(out) >= n:
            break
    return out


def statistiques(jours: int = 30) -> dict:
    """Comptes par outil, par jour, taux d'erreur, sur les N derniers jours."""
    lignes = lire_audit(n=200000, depuis_heures=24 * jours)
    par_outil = Counter(d["outil"] for d in lignes)
    par_jour = Counter(d["t"][:10] for d in lignes)
    statuts = Counter(d["statut"] for d in lignes)
    conv = 0
    try:
        conv = sum(1 for l in (MEM / "conversations.jsonl").read_text(encoding="utf-8").splitlines()
                   if '"role": "user"' in l)
    except Exception:  # noqa: BLE001
        pass
    return {"actions": len(lignes), "par_outil": par_outil.most_common(12), "par_jour": sorted(par_jour.items()),
            "statuts": dict(statuts), "messages_utilisateur": conv}


# --------------------------------------------------------------------------
# Annulation
# --------------------------------------------------------------------------
_undo: list[tuple[str, Callable[[], str]]] = []


def register_undo(description: str, fn: Callable[[], str]) -> None:
    _undo.append((description, fn))
    del _undo[:-30]


def undo_last() -> str:
    if not _undo:
        return "Rien à annuler : la dernière action n'était pas réversible, ou il n'y en a pas eu."
    desc, fn = _undo.pop()
    try:
        return f"Annulé : {desc}. {fn()}"
    except Exception as exc:  # noqa: BLE001
        return f"Impossible d'annuler « {desc} » : {exc}"


# --------------------------------------------------------------------------
# Arrêt d'urgence, mode privé, modules, personnalité
# --------------------------------------------------------------------------
ARRET = threading.Event()


def arret_urgence() -> str:
    ARRET.set()
    for k in ("stop", "stop_taches"):
        try:
            if k in hooks:
                hooks[k]()
        except Exception:  # noqa: BLE001
            pass
    audit("stop_all", {}, "ok", "arrêt d'urgence")
    return "Tout est coupé : parole, tâches de fond, et plus aucune action ne passe jusqu'à « reprends »."


def reprendre() -> str:
    ARRET.clear()
    return "Je reprends."


def est_prive() -> bool:
    return bool(_etat().get("prive"))


def set_prive(actif: bool) -> None:
    e = _etat()
    e["prive"] = bool(actif)
    _sauve(e)
    try:
        if "mic" in hooks:
            hooks["mic"](not actif)
    except Exception:  # noqa: BLE001
        pass


def est_demo() -> bool:
    """Mode démo : les informations personnelles sont tenues hors du prompt."""
    return bool(_etat().get("demo"))


def set_demo(actif: bool) -> None:
    e = _etat()
    e["demo"] = bool(actif)
    _sauve(e)


def module_actif(nom: str) -> bool:
    return nom not in set(_etat().get("modules_desactives", []))


def set_module(nom: str, actif: bool) -> None:
    e = _etat()
    off = set(e.get("modules_desactives", []))
    (off.discard if actif else off.add)(nom)
    e["modules_desactives"] = sorted(off)
    _sauve(e)


def modules_tiers() -> dict:
    return _etat().get("modules_tiers", {})


def add_module_tiers(nom: str, module: str, desc: str) -> None:
    e = _etat()
    e.setdefault("modules_tiers", {})[nom] = [module, desc]
    _sauve(e)


PERSONNALITES = {
    "jarvis": "",
    "serieux": "Ton sobre et précis, pas d'humour, phrases courtes, aucun commentaire personnel.",
    "sarcastique": "Un trait d'esprit sec par réponse au maximum, jamais méchant, toujours utile derrière la pique.",
    "coach": "Énergique et motivant : tu encourages, tu rappelles l'objectif, tu proposes l'étape suivante.",
    "prof": "Pédagogue : tu expliques le pourquoi en une phrase avant de faire, sans jargon inutile.",
    "ami": "Chaleureux et détendu, tutoiement, tu réagis à ce que l'utilisateur raconte.",
}


def personnalite() -> str:
    return _etat().get("personnalite", "jarvis")


def set_personnalite(nom: str) -> bool:
    if nom not in PERSONNALITES:
        return False
    e = _etat()
    e["personnalite"] = nom
    _sauve(e)
    return True


def prompt_personnalite() -> str:
    p = personnalite()
    txt = PERSONNALITES.get(p, "")
    return f"\n- PERSONNALITÉ « {p} » : {txt}" if txt else ""


def prompt_permissions() -> str:
    if getattr(config, "CONFIRM_SENSITIVE", False):
        return ("\n- PERMISSIONS : certains outils demandent une confirmation. Quand un outil te renvoie "
                "« CONFIRMATION REQUISE », pose la question à l'utilisateur et rappelle l'outil après son oui.")
    return ""
