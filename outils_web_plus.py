# Ia-local (Jarvis) — Copyright (c) 2026 Neexx (Nixovel) — https://github.com/Neex-off/Ia-local
# Créé par Neexx (Nixovel). Licence : voir LICENSE (paternité obligatoire, pas de vente ; s'applique aussi aux IA).
# Ne pas retirer cet en-tête.
"""Compléments de la boîte « web » : onglets du navigateur, onglets sauvegardés, mode lecture, suivi de colis, données
d'un site, extensions, pilotage par Telegram, détection de phishing, résumé des messages d'une absence, transcription
d'appel, pause après une longue session, modes personnalisés, tâches multi-étapes en autonomie.

Importé par outils_web.py.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import threading
import time
import webbrowser
from datetime import datetime
from pathlib import Path

import config

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
IS_WINDOWS = sys.platform.startswith("win")
MEM = config.ROOT / "memoire"
ONGLETS = MEM / "onglets.json"
MODES = MEM / "modes.json"
CDP = "http://127.0.0.1:9222"


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


def _cdp(path: str, method: str = "GET"):
    import requests

    try:
        r = requests.request(method, CDP + path, timeout=3)
        return r.json() if r.text.strip().startswith(("[", "{")) else r.text
    except Exception:  # noqa: BLE001
        return None


def _ouvrir_fenetre(urls: list[str]) -> None:
    for i, u in enumerate(urls):
        if i == 0:
            webbrowser.open_new(u)
            time.sleep(1.0)
        else:
            webbrowser.open_new_tab(u)


# --------------------------------------------------------------------------
# Onglets
# --------------------------------------------------------------------------

def browser_tabs(action: str = "list", target: str = "") -> str:
    """Onglets du navigateur : lister, ouvrir une adresse, fermer (par mot du titre), aller à un onglet, regrouper les onglets d'un même site dans une nouvelle fenêtre.

    Args:
        action: "list", "open", "close", "switch" ou "group".
        target: Adresse (open), mot du titre ou de l'adresse (close/switch), domaine (group).
    """
    onglets = _cdp("/json/list")
    if isinstance(onglets, list):
        pages = [t for t in onglets if t.get("type") == "page"]
        if action == "list":
            return "\n".join(f"- {t.get('title', '')[:60]} — {t.get('url', '')[:80]}" for t in pages) or "Aucun onglet."
        if action == "open":
            _cdp(f"/json/new?{target}", "PUT")
            return f"Onglet ouvert : {target}"
        cibles = [t for t in pages if target.lower() in (t.get("title", "") + t.get("url", "")).lower()]
        if action == "close":
            for t in cibles:
                _cdp(f"/json/close/{t['id']}")
            return f"{len(cibles)} onglet(s) fermé(s)."
        if action == "switch":
            if cibles:
                _cdp(f"/json/activate/{cibles[0]['id']}")
                return f"Onglet « {cibles[0].get('title', '')[:50]} » affiché."
            return "Aucun onglet ne correspond."
        if action == "group":
            urls = [t["url"] for t in cibles]
            for t in cibles:
                _cdp(f"/json/close/{t['id']}")
            if urls:
                _ouvrir_fenetre(urls)
            return f"{len(urls)} onglet(s) de « {target} » regroupés dans une nouvelle fenêtre."
        return "Action : list, open, close, switch ou group."
    import pyautogui

    if action == "open":
        webbrowser.open(target if target.startswith("http") else "https://" + target)
        return f"Ouvert : {target}"
    if action == "close":
        pyautogui.hotkey("ctrl", "w")
        return "Onglet courant fermé (pour viser un onglet précis, lance Chrome avec --remote-debugging-port=9222)."
    if action == "switch":
        pyautogui.hotkey("ctrl", "shift", "a")
        time.sleep(0.4)
        pyautogui.write(target)
        time.sleep(0.4)
        pyautogui.press("enter")
        return f"Recherche d'onglet « {target} » lancée (Ctrl+Maj+A)."
    return ("Liste et regroupement précis demandent Chrome lancé avec --remote-debugging-port=9222 "
            "(je peux modifier le raccourci). En attendant : open, close, switch marchent au clavier.")


def save_tabs(action: str = "save", name: str = "plus-tard") -> str:
    """Sauvegarde les onglets ouverts pour plus tard (et les ferme si demandé), ou les rouvre.

    Args:
        action: "save", "save_close", "restore" ou "list".
        name: Nom du lot.
    """
    base = _json(ONGLETS, {})
    if action == "list":
        return "Lots : " + (", ".join(f"{k} ({len(v)})" for k, v in base.items()) or "aucun")
    if action == "restore":
        urls = base.get(name)
        if not urls:
            return f"Lot inconnu : {name}."
        _ouvrir_fenetre(urls)
        return f"{len(urls)} onglet(s) rouverts."
    onglets = _cdp("/json/list")
    if not isinstance(onglets, list):
        return "Il faut Chrome avec --remote-debugging-port=9222 pour lire les onglets (sinon Ctrl+Maj+D dans Chrome ajoute tous les onglets aux favoris)."
    pages = [t for t in onglets if t.get("type") == "page" and t.get("url", "").startswith("http")]
    base[name] = [t["url"] for t in pages]
    _save(ONGLETS, base)
    if action == "save_close":
        for t in pages:
            _cdp(f"/json/close/{t['id']}")
    return f"{len(pages)} onglet(s) sauvegardés dans « {name} »" + (" et fermés." if action == "save_close" else ".")


def reader_mode(url: str) -> str:
    """Mode lecture sans pub : récupère le texte d'un article et l'affiche dans une page propre (grande police, fond calme).

    Args:
        url: Adresse de l'article.
    """
    try:
        import tools

        texte = tools._page_text(url) if hasattr(tools, "_page_text") else tools.fetch_url(url)
    except Exception as exc:  # noqa: BLE001
        return f"Impossible de lire la page : {exc}"
    titre = re.sub(r"[?#].*$", "", url).rstrip("/").split("/")[-1].replace("-", " ") or url
    paragraphes = [p.strip() for p in re.split(r"\n{2,}|\n(?=[A-ZÉÈÀ])", texte) if len(p.strip()) > 40]
    html = ("<!doctype html><html lang='fr'><head><meta charset='utf-8'><title>Lecture</title><style>"
            "body{max-width:720px;margin:40px auto;padding:0 24px;font:20px/1.7 Georgia,serif;background:#fbf7ef;color:#222}"
            "h1{font-size:30px;line-height:1.25}p{margin:0 0 1.2em}a{color:#555}</style></head><body>"
            f"<p><a href='{url}'>{url}</a></p><h1>{titre}</h1>" + "".join(f"<p>{p}</p>" for p in paragraphes[:200]) + "</body></html>")
    out = config.WORKSPACE / "lecture.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    webbrowser.open(out.as_uri())
    return f"Mode lecture ouvert ({len(paragraphes)} paragraphes). Début : {' '.join(paragraphes[:2])[:300]}"


TRANSPORTEURS = [
    (r"^1Z[0-9A-Z]{16}$", "UPS", "https://www.ups.com/track?loc=fr_FR&tracknum={n}"),
    (r"^(\d{10}|JD\d{18}|JJD\d+)$", "DHL", "https://www.dhl.com/fr-fr/home/tracking.html?tracking-id={n}"),
    (r"^[A-Z]{2}[0-9A-Z]{11,13}$", "La Poste / Colissimo", "https://www.laposte.fr/outils/suivre-vos-envois?code={n}"),
    (r"^(XY|XV|XW|XX|XZ|CX)\d{10,12}[A-Z]{0,2}$", "Chronopost", "https://www.chronopost.fr/tracking-no-cms/suivi-page?listeNumerosLT={n}"),
    (r"^\d{8}$", "Mondial Relay", "https://www.mondialrelay.fr/suivi-de-colis/?numeroExpedition={n}"),
    (r"^TBA\d{12}$", "Amazon Logistics", "https://www.amazon.fr/gp/your-account/order-history"),
    (r"^\d{12}$|^\d{14}$", "FedEx", "https://www.fedex.com/fedextrack/?trknbr={n}"),
    (r"^\d{15}$", "GLS", "https://gls-group.eu/FR/fr/suivi-colis?match={n}"),
    (r"^\d{11}$|^\d{13}$", "DPD / Colis Privé", "https://www.dpd.fr/trace/{n}"),
]


def track_parcel(number: str, carrier: str = "auto") -> str:
    """Suivi de colis : reconnaît le transporteur au numéro, ouvre la page de suivi, et te dit de lire l'état à l'écran.

    Args:
        number: Numéro de suivi.
        carrier: "auto", ou un transporteur pour forcer (ups, dhl, laposte, chronopost, mondialrelay, fedex, gls, dpd).
    """
    n = re.sub(r"\s", "", number).upper()
    trouve = None
    if carrier != "auto":
        c = carrier.lower().replace(" ", "")
        trouve = next(((nom, url) for _r, nom, url in TRANSPORTEURS if c in nom.lower().replace(" ", "").replace("/", "")), None)
    if not trouve:
        trouve = next(((nom, url) for r, nom, url in TRANSPORTEURS if re.match(r, n)), None)
    if not trouve:
        webbrowser.open(f"https://www.17track.net/fr/track?nums={n}")
        return f"Transporteur non reconnu : page 17track ouverte pour {n}. Regarde l'écran et lis l'état (see_screen)."
    nom, url = trouve
    webbrowser.open(url.format(n=n))
    return f"Colis {n} chez {nom} : page de suivi ouverte. Regarde l'écran (see_screen) et lis l'état et la date de livraison."


def clear_site_data(domain: str, browser: str = "chrome") -> str:
    """Vide le cache et les cookies d'UN site (pas de tout le navigateur) : ouvre la page des données du site et clique Effacer.

    Args:
        domain: Le site, ex. "youtube.com".
        browser: "chrome" ou "edge".
    """
    prefixe = "edge" if browser == "edge" else "chrome"
    webbrowser.open(f"{prefixe}://settings/content/all?searchSubpage={domain}")
    time.sleep(2.0)
    try:
        import computer

        computer.ui_elements()
        for nom in ("Effacer les données", "Clear data", "Supprimer les données", "Effacer"):
            e = computer.find_element(nom)
            if e:
                computer.click(e["x"], e["y"])
                return f"Données de {domain} effacées (cache et cookies). Le site te redemandera de te connecter."
    except Exception:  # noqa: BLE001
        pass
    return f"Page des données de {domain} ouverte : clique sur l'icône corbeille du site (see_screen pour que je le fasse)."


def manage_extensions(action: str = "open", browser: str = "chrome") -> str:
    """Gère les extensions du navigateur : liste avec leurs risques, ou ouvre la page des extensions pour activer, désactiver, supprimer à l'écran.

    Args:
        action: "list" ou "open".
        browser: "chrome", "edge", "brave" ou "opera".
    """
    if action == "list":
        try:
            from outils_securite import browser_extensions

            return browser_extensions(browser)
        except Exception as exc:  # noqa: BLE001
            return f"Erreur : {exc}"
    pages = {"chrome": "chrome://extensions", "edge": "edge://extensions", "brave": "brave://extensions", "opera": "opera://extensions"}
    webbrowser.open(pages.get(browser, "chrome://extensions"))
    return "Page des extensions ouverte : dis-moi laquelle activer, désactiver ou supprimer et je clique (see_screen)."


# --------------------------------------------------------------------------
# Communication
# --------------------------------------------------------------------------
_TG: dict = {"thread": None, "stop": threading.Event()}


def telegram_bridge(action: str = "start") -> str:
    """Pilotage à distance par Telegram : ton bot (TELEGRAM_TOKEN) reçoit tes messages et te renvoie les réponses de Jarvis. Seul TELEGRAM_CHAT_ID est écouté.

    Args:
        action: "start", "stop" ou "status".
    """
    token = getattr(config, "TELEGRAM_TOKEN", "")
    chat = str(getattr(config, "TELEGRAM_CHAT_ID", ""))
    if action == "status":
        actif = _TG["thread"] is not None and _TG["thread"].is_alive()
        return f"Passerelle Telegram {'active' if actif else 'arrêtée'}."
    if action == "stop":
        _TG["stop"].set()
        return "Passerelle Telegram arrêtée."
    if not token or not chat:
        return "Il manque TELEGRAM_TOKEN (créé avec @BotFather) et TELEGRAM_CHAT_ID (ton id, donné par @userinfobot) dans config.py."
    if _TG["thread"] and _TG["thread"].is_alive():
        return "Déjà active."
    import requests

    import noyau

    base = f"https://api.telegram.org/bot{token}"

    def envoyer(texte: str) -> None:
        try:
            requests.post(f"{base}/sendMessage", json={"chat_id": chat, "text": texte[:4000]}, timeout=15)
        except Exception:  # noqa: BLE001
            pass

    noyau.hooks.setdefault("reponses", []).append(envoyer)
    _TG["stop"].clear()

    def boucle():
        offset = 0
        while not _TG["stop"].is_set():
            try:
                r = requests.get(f"{base}/getUpdates", params={"offset": offset, "timeout": 25}, timeout=35).json()
                for u in r.get("result", []):
                    offset = u["update_id"] + 1
                    m = u.get("message") or {}
                    if str(m.get("chat", {}).get("id")) != chat:
                        continue
                    texte = (m.get("text") or "").strip()
                    if texte and "texte" in noyau.hooks:
                        noyau.hooks["texte"](texte)
            except Exception:  # noqa: BLE001
                _TG["stop"].wait(5)

    _TG["thread"] = threading.Thread(target=boucle, daemon=True)
    _TG["thread"].start()
    envoyer("Jarvis est à l'écoute ici.")
    return "Passerelle Telegram active : écris à ton bot, je réponds dedans."


_URGENCE = ("urgent", "immédiatement", "sous 24h", "dernier avertissement", "compte suspendu", "sera fermé", "vérifiez votre compte",
            "confirmez vos informations", "gagné", "félicitations", "colis en attente", "frais de douane", "mettre à jour vos coordonnées")
_MARQUES = ("paypal", "amazon", "laposte", "impots", "ameli", "banque", "microsoft", "apple", "google", "netflix", "orange", "sfr",
            "free", "chronopost", "colissimo")


def phishing_check(text: str = "", count: int = 5) -> str:
    """Détection de phishing : analyse un mail collé (ou les N derniers mails via read_email) : urgence, liens trompeurs, domaines sosies, pièces jointes dangereuses, expéditeur douteux.

    Args:
        text: Le texte du mail (avec liens et expéditeur si possible). Vide = lire les derniers mails.
        count: Nombre de mails à analyser si text est vide.
    """
    if not text:
        try:
            import tools

            text = tools.read_email(count)
        except Exception as exc:  # noqa: BLE001
            return f"Impossible de lire les mails : {exc}"
    bas = text.lower()
    points, score = [], 0
    urg = [u for u in _URGENCE if u in bas]
    if urg:
        score += 2
        points.append("pression / urgence : " + ", ".join(urg[:4]))
    for l in re.findall(r"https?://[^\s)>\"']+", text)[:30]:
        dom = re.sub(r"^https?://", "", l).split("/")[0].lower()
        if re.search(r"(bit\.ly|tinyurl|t\.co|goo\.gl|cutt\.ly|rb\.gy)", dom):
            score += 2
            points.append(f"lien raccourci : {dom}")
        if re.search(r"\d+\.\d+\.\d+\.\d+", dom):
            score += 3
            points.append(f"lien vers une adresse IP : {dom}")
        for marque in _MARQUES:
            if marque in dom and not re.search(rf"(^|\.){marque}\.(fr|com|gouv\.fr|net)$", dom):
                score += 3
                points.append(f"domaine sosie de {marque} : {dom}")
    if re.search(r"\.(exe|scr|js|vbs|hta|zip|rar|iso|htm|html)\b", bas) and any(m in bas for m in ("pièce jointe", "attachment", "ci-joint")):
        score += 2
        points.append("pièce jointe à risque")
    exp = re.search(r"(?:from|de|expéditeur)\s*:\s*[^<\n]*<?([\w.+-]+@[\w.-]+)", text, re.I)
    rep = re.search(r"reply-to\s*:\s*[^<\n]*<?([\w.+-]+@[\w.-]+)", text, re.I)
    if exp and rep and exp.group(1).split("@")[1].lower() != rep.group(1).split("@")[1].lower():
        score += 2
        points.append(f"réponse redirigée vers un autre domaine : {rep.group(1)}")
    if exp and re.search(r"@(gmail|outlook|hotmail|yahoo)\.", exp.group(1).lower()) and any(m in bas for m in ("banque", "impots", "amende", "facture", "livraison")):
        score += 1
        points.append("expéditeur grand public pour un sujet officiel")
    verdict = "PHISHING probable" if score >= 5 else "douteux" if score >= 3 else "rien d'alarmant"
    return (f"Verdict : {verdict} (score {score}).\n" + ("\n".join(f"- {p}" for p in points) if points else "- aucun signal")
            + "\nRègle : ne clique pas depuis le mail, tape l'adresse du site toi-même.")


def absence_summary(hours: int = 8, emails: int = 15) -> str:
    """Rassemble ce qui est arrivé pendant une absence : mails récents, notifications du téléphone, pages surveillées, actions de Jarvis, pour que tu en fasses un résumé.

    Args:
        hours: Durée de l'absence.
        emails: Nombre de mails à lire.
    """
    parts = []
    try:
        import tools

        parts.append("## Mails\n" + tools.read_email(emails))
    except Exception as exc:  # noqa: BLE001
        parts.append(f"## Mails : {exc}")
    try:
        from outils_vie import phone_notifications

        parts.append("## Téléphone\n" + phone_notifications())
    except Exception:  # noqa: BLE001
        pass
    try:
        import tools

        parts.append("## Pages surveillées\n" + tools.check_watched())
    except Exception:  # noqa: BLE001
        pass
    try:
        import noyau

        lignes = noyau.lire_audit(n=30, depuis_heures=hours)
        if lignes:
            parts.append("## Ce que j'ai fait pendant ce temps\n" + "\n".join(f"- {d['t'][11:16]} {d['outil']} -> {d['statut']}" for d in lignes))
    except Exception:  # noqa: BLE001
        pass
    return "\n\n".join(parts)[:7000] + f"\n\nRésume en cinq lignes max ce qui compte sur ces {hours} dernières heures, urgent d'abord."


_APPEL: dict = {"stream": None, "stream2": None, "frames": []}


def transcribe_call(action: str = "start") -> str:
    """Transcrit et résume un appel (micro + son du PC si un périphérique « Mixage stéréo » existe). Préviens les participants : l'enregistrement demande leur accord.

    Args:
        action: "start" pour commencer, "stop" pour arrêter et transcrire.
    """
    import numpy as np
    import sounddevice as sd

    if action == "start":
        if _APPEL["stream"]:
            return "Un enregistrement est déjà en cours."
        _APPEL["frames"] = []
        loopback = None
        try:
            for i, d in enumerate(sd.query_devices()):
                nom = d["name"].lower()
                if d["max_input_channels"] > 0 and ("mix" in nom or "loopback" in nom or "stéréo" in nom or "stereo" in nom):
                    loopback = i
                    break
        except Exception:  # noqa: BLE001
            pass

        def cb(indata, frames, t, status):
            _APPEL["frames"].append(indata.copy())

        _APPEL["stream"] = sd.InputStream(samplerate=16000, channels=1, dtype="float32", callback=cb)
        _APPEL["stream"].start()
        if loopback is not None:
            _APPEL["stream2"] = sd.InputStream(device=loopback, samplerate=16000, channels=1, dtype="float32", callback=cb)
            _APPEL["stream2"].start()
        return ("Enregistrement de l'appel lancé (micro" + (" + son du PC" if loopback is not None else ", sans le son du PC : active « Mixage stéréo » dans les périphériques d'enregistrement")
                + "). Rappelle : les participants doivent être d'accord. transcribe_call(\"stop\") pour finir.")
    if not _APPEL["stream"]:
        return "Aucun enregistrement en cours."
    for k in ("stream", "stream2"):
        if _APPEL[k]:
            _APPEL[k].stop()
            _APPEL[k].close()
            _APPEL[k] = None
    if not _APPEL["frames"]:
        return "Rien d'enregistré."
    import soundfile as sf

    audio = np.concatenate(_APPEL["frames"], axis=0)
    f = config.WORKSPACE / f"appel-{datetime.now():%Y%m%d-%H%M}.wav"
    f.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(f), audio, 16000)
    try:
        import tools

        texte = tools.transcribe_media(str(f))
    except Exception as exc:  # noqa: BLE001
        return f"Audio enregistré ({f}) mais transcription impossible : {exc}"
    return f"Transcription ({len(audio)/16000/60:.1f} min) :\n{texte[:6000]}\n\nRésume : sujet, décisions, actions à faire (qui, quoi, quand)."


_PAUSE: dict = {"thread": None, "stop": threading.Event()}


def break_reminder(enable: bool = True, minutes: int = 90) -> str:
    """Propose une pause à la voix après une longue session d'activité continue (clavier/souris), puis toutes les 45 minutes.

    Args:
        enable: True pour activer, False pour arrêter.
        minutes: Durée d'activité avant la première pause.
    """
    if not enable:
        _PAUSE["stop"].set()
        return "Rappel de pause désactivé."
    if _PAUSE["thread"] and _PAUSE["thread"].is_alive():
        return "Déjà actif."
    if not IS_WINDOWS:
        return "Disponible seulement sous Windows (détection d'inactivité)."
    _PAUSE["stop"].clear()

    def inactif_depuis() -> float:
        import ctypes

        class LASTINPUTINFO(ctypes.Structure):
            _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]

        li = LASTINPUTINFO()
        li.cbSize = ctypes.sizeof(LASTINPUTINFO)
        ctypes.windll.user32.GetLastInputInfo(ctypes.byref(li))
        return (ctypes.windll.kernel32.GetTickCount() - li.dwTime) / 1000

    def boucle():
        debut = time.time()
        prochain = minutes * 60
        while not _PAUSE["stop"].is_set():
            if inactif_depuis() > 600:
                debut, prochain = time.time(), minutes * 60
            elif time.time() - debut >= prochain:
                _prevenir("Vous êtes dessus depuis un bon moment, monsieur. Cinq minutes de pause, les yeux loin de l'écran.")
                prochain += 45 * 60
            _PAUSE["stop"].wait(60)

    _PAUSE["thread"] = threading.Thread(target=boucle, daemon=True)
    _PAUSE["thread"].start()
    return f"Rappel de pause actif : après {minutes} minutes d'activité continue."


# --------------------------------------------------------------------------
# Modes et autonomie
# --------------------------------------------------------------------------
_MODES_DEFAUT = {
    "dev": ["do_not_disturb(True)", "open_app(Visual Studio Code)", "set_theme(sombre)"],
    "jeu": ["do_not_disturb(True)", "game_mode(True)", "open_app(Discord)"],
    "nuit": ["set_brightness(30)", "night_light(True)", "do_not_disturb(True)"],
    "travail": ["do_not_disturb(False)", "set_brightness(80)", "night_light(False)"],
}


def custom_modes(action: str = "list", name: str = "", steps: str = "") -> str:
    """Modes personnalisables (dev, jeu, nuit…) : une liste d'actions appliquées d'un coup. list, apply, save, remove.

    Args:
        action: "list", "apply", "save" ou "remove".
        name: Nom du mode.
        steps: Pour save : actions séparées par des points-virgules, sous la forme outil(arg1, arg2), ex. "do_not_disturb(True); open_app(Spotify)".
    """
    base = _json(MODES, {}) or dict(_MODES_DEFAUT)
    if action == "list":
        return "\n".join(f"- {k} : {' ; '.join(v)}" for k, v in base.items())
    if action == "save":
        base[name] = [s.strip() for s in steps.split(";") if s.strip()]
        _save(MODES, base)
        return f"Mode « {name} » enregistré ({len(base[name])} actions)."
    if action == "remove":
        base.pop(name, None)
        _save(MODES, base)
        return f"Mode « {name} » supprimé."
    actions = base.get(name)
    if not actions:
        return f"Mode inconnu : {name}. Modes : {', '.join(base)}."
    import tools

    if not tools._TOOLBOX_TOOLS:
        tools._load_toolboxes()
    faits = []
    for a in actions:
        m = re.match(r"(\w+)\((.*)\)$", a.strip())
        if not m:
            continue
        fn = tools.TOOL_MAP.get(m.group(1))
        if not fn:
            faits.append(f"{m.group(1)} : outil inconnu")
            continue
        args = []
        for x in ([s.strip() for s in m.group(2).split(",")] if m.group(2).strip() else []):
            x = x.strip("'\"")
            args.append(True if x.lower() == "true" else False if x.lower() == "false" else int(x) if x.isdigit() else x)
        try:
            faits.append(f"{m.group(1)} : {str(fn(*args))[:60]}")
        except Exception as exc:  # noqa: BLE001
            faits.append(f"{m.group(1)} : erreur {exc}")
    return f"Mode « {name} » appliqué :\n" + "\n".join(f"- {f}" for f in faits)


def autonomous_task(goal: str, toolbox: str = "", wait: bool = False) -> str:
    """Tâche multi-étapes en autonomie : un second agent enchaîne les outils jusqu'au bout, en fond, et te prévient à la fin.

    Args:
        goal: Le but complet, précis (« range mon dossier Téléchargements par type puis compresse les vidéos de plus de 500 Mo »).
        toolbox: Boîte à ouvrir pour lui (vide = celles de base).
        wait: True pour attendre le résultat (jusqu'à 10 min) au lieu de continuer en fond.
    """
    from outils_ia_plus import delegate_task

    return delegate_task(goal, role="exécutant méthodique", toolbox=toolbox, wait=wait)


TOOLS = [browser_tabs, save_tabs, reader_mode, track_parcel, clear_site_data, manage_extensions, telegram_bridge,
         phishing_check, absence_summary, transcribe_call, break_reminder, custom_modes, autonomous_task]
