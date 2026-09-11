# Ia-local (Jarvis) — Copyright (c) 2026 Neexx (Nixovel) — https://github.com/Neex-off/Ia-local
# Créé par Neexx (Nixovel). Licence : voir LICENSE (paternité obligatoire, pas de vente ; s'applique aussi aux IA).
# Ne pas retirer cet en-tête.
"""Boîte à outils « web » : téléchargements, veille de pages, navigateur, mails, messages, suivi du temps.

Chargée à la demande par tools.open_toolbox("web").
Catalogue : modules Web & navigateur, Communication, Productivité.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path

import config

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
VEILLE = config.ROOT / "memoire" / "veille.json"
TEMPS = config.ROOT / "memoire" / "temps.json"
UA = {"User-Agent": "Mozilla/5.0 (agent local)"}


def _charge(fichier: Path, defaut: dict) -> dict:
    if not fichier.is_file():
        return dict(defaut)
    try:
        return json.loads(fichier.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return dict(defaut)


def _sauve(fichier: Path, data: dict) -> None:
    fichier.parent.mkdir(parents=True, exist_ok=True)
    fichier.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _p(chemin: str) -> Path:
    p = Path(str(chemin).strip('" ')).expanduser()
    return p if p.is_absolute() else (config.WORKSPACE / p)


def _texte_page(url: str, timeout: float = 20) -> tuple[str, str]:
    """Renvoie le titre et le texte lisible d'une page web."""
    import requests
    from bs4 import BeautifulSoup

    if not url.startswith("http"):
        url = "https://" + url
    r = requests.get(url, timeout=timeout, headers=UA)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header", "noscript", "aside"]):
        tag.decompose()
    titre = soup.title.get_text(strip=True) if soup.title else url
    texte = "\n".join(l.strip() for l in soup.get_text("\n").splitlines() if len(l.strip()) > 30)
    return titre, texte


# --------------------------------------------------------------------------
# Téléchargements et pages
# --------------------------------------------------------------------------

def download_file(url: str, destination: str = "") -> str:
    """Télécharge un fichier depuis internet et l'enregistre sur l'ordinateur.

    Args:
        url: L'adresse du fichier.
        destination: Chemin où l'enregistrer. Vide = dossier Téléchargements, avec son nom d'origine.
    """
    try:
        import requests
        from urllib.parse import unquote, urlparse

        if not url.startswith("http"):
            url = "https://" + url
        nom = unquote(Path(urlparse(url).path).name) or "telechargement"
        cible = _p(destination) if destination else (Path.home() / "Downloads" / nom)
        if cible.is_dir():
            cible = cible / nom
        cible.parent.mkdir(parents=True, exist_ok=True)
        t0, total = time.time(), 0
        with requests.get(url, stream=True, timeout=60, headers=UA) as r:
            r.raise_for_status()
            with open(cible, "wb") as f:
                for morceau in r.iter_content(chunk_size=262144):
                    f.write(morceau)
                    total += len(morceau)
        return f"Téléchargé : {cible}, {total / 2**20:.1f} Mo en {time.time() - t0:.1f} s"
    except Exception as exc:  # noqa: BLE001
        return f"Erreur de téléchargement : {exc}"


def save_page(url: str, destination: str = "") -> str:
    """Enregistre une page web sur l'ordinateur pour la relire plus tard, même hors ligne.

    Args:
        url: L'adresse de la page.
        destination: Chemin du fichier à créer. Vide = dossier de travail.
    """
    try:
        import requests

        if not url.startswith("http"):
            url = "https://" + url
        r = requests.get(url, timeout=30, headers=UA)
        r.raise_for_status()
        nom = re.sub(r"[^a-zA-Z0-9]+", "-", url.split("//", 1)[-1])[:60] + ".html"
        cible = _p(destination) if destination else (config.WORKSPACE / nom)
        cible.parent.mkdir(parents=True, exist_ok=True)
        cible.write_text(r.text, encoding="utf-8", errors="ignore")
        return f"Page enregistrée : {cible}, {len(r.text) / 1024:.0f} Ko"
    except Exception as exc:  # noqa: BLE001
        return f"Erreur : {exc}"


def watch_page(url: str, note: str = "") -> str:
    """Surveille une page web : Jarvis retient son contenu et pourra dire plus tard si elle a changé.

    Args:
        url: L'adresse de la page à surveiller.
        note: Ce qu'on surveille, par exemple "le prix" ou "les nouvelles offres".
    """
    try:
        titre, texte = _texte_page(url)
        d = _charge(VEILLE, {"pages": {}})
        d.setdefault("pages", {})[url] = {
            "titre": titre, "note": note,
            "hash": hashlib.sha1(texte.encode("utf-8")).hexdigest(),
            "vu": datetime.now().isoformat(timespec="seconds"),
            "extrait": texte[:400],
        }
        _sauve(VEILLE, d)
        return f"Je surveille « {titre} ». Demande-moi plus tard si cette page a changé."
    except Exception as exc:  # noqa: BLE001
        return f"Erreur : {exc}"


def check_watched() -> str:
    """Vérifie toutes les pages surveillées et dit lesquelles ont changé depuis la dernière fois."""
    d = _charge(VEILLE, {"pages": {}})
    pages = d.get("pages", {})
    if not pages:
        return "Aucune page surveillée. Utilise watch_page pour en ajouter une."
    changees, inchangees, erreurs = [], 0, []
    for url, info in pages.items():
        try:
            titre, texte = _texte_page(url)
            h = hashlib.sha1(texte.encode("utf-8")).hexdigest()
            if h != info.get("hash"):
                changees.append(f"CHANGÉ : {titre} ({info.get('note') or url})\n"
                                f"   avant : {info.get('extrait', '')[:150]}\n   maintenant : {texte[:150]}")
                info.update({"hash": h, "extrait": texte[:400],
                             "vu": datetime.now().isoformat(timespec="seconds")})
            else:
                inchangees += 1
        except Exception as exc:  # noqa: BLE001
            erreurs.append(f"{url} : {exc}")
    _sauve(VEILLE, d)
    out = []
    if changees:
        out.append("\n".join(changees))
    out.append(f"{inchangees} page(s) inchangée(s) sur {len(pages)} surveillées.")
    if erreurs:
        out.append("Injoignables : " + " ; ".join(erreurs[:3]))
    return "\n".join(out)


def list_watched() -> str:
    """Liste les pages web actuellement surveillées."""
    d = _charge(VEILLE, {"pages": {}})
    pages = d.get("pages", {})
    if not pages:
        return "Aucune page surveillée."
    lignes = [f"- {i.get('titre', u)} ({i.get('note') or 'sans note'}), vu le "
              f"{str(i.get('vu', '?'))[:16].replace('T', ' à ')}\n  {u}" for u, i in pages.items()]
    return f"{len(pages)} page(s) surveillée(s) :\n" + "\n".join(lignes)


def unwatch_page(url_or_text: str) -> str:
    """Arrête de surveiller une page web.

    Args:
        url_or_text: L'adresse, ou un mot du titre de la page.
    """
    d = _charge(VEILLE, {"pages": {}})
    q = url_or_text.lower()
    a_retirer = [u for u, i in d.get("pages", {}).items()
                 if q in u.lower() or q in str(i.get("titre", "")).lower()]
    for u in a_retirer:
        del d["pages"][u]
    _sauve(VEILLE, d)
    return f"{len(a_retirer)} page(s) retirée(s) de la surveillance." if a_retirer else "Aucune page ne correspond."


def summarize_video(url: str) -> str:
    """Récupère le titre, la chaîne, la durée et la description d'une vidéo pour pouvoir en parler.

    Args:
        url: L'adresse de la vidéo, par exemple un lien YouTube.
    """
    try:
        import requests

        html = requests.get(url, timeout=25, headers=UA).text
        titre = re.search(r'<meta name="title" content="([^"]+)"', html)
        chaine = re.search(r'"ownerChannelName":"([^"]+)"', html)
        desc = re.search(r'"shortDescription":"(.*?)","', html, re.S)
        duree = re.search(r'"lengthSeconds":"(\d+)"', html)
        if not titre:
            return "Je n'ai pas pu lire les informations de cette vidéo. Ouvre-la et je regarderai l'écran."
        d = desc.group(1).encode().decode("unicode_escape") if desc else ""
        secs = int(duree.group(1)) if duree else 0
        return (f"Titre : {titre.group(1)}\nChaîne : {chaine.group(1) if chaine else '?'}\n"
                f"Durée : {secs // 60} min {secs % 60} s\n\nDescription :\n{d[:1500]}")
    except Exception as exc:  # noqa: BLE001
        return f"Erreur : {exc}"


# --------------------------------------------------------------------------
# Navigateur
# --------------------------------------------------------------------------

def _profils_navigateur() -> list[Path]:
    base = Path(os.environ.get("LOCALAPPDATA", Path.home()))
    return [base / "Google/Chrome/User Data/Default", base / "Microsoft/Edge/User Data/Default",
            base / "BraveSoftware/Brave-Browser/User Data/Default"]


def browser_history(query: str = "", days: int = 7, count: int = 25) -> str:
    """Cherche dans l'historique de navigation les sites visités récemment.

    Args:
        query: Mot-clé à chercher dans le titre ou l'adresse. Vide = les plus récents.
        days: Remonter de combien de jours.
        count: Nombre de résultats.
    """
    for prof in _profils_navigateur():
        src = prof / "History"
        if not src.is_file():
            continue
        copie = config.WORKSPACE / "_hist.db"
        try:
            shutil.copy2(src, copie)
            con = sqlite3.connect(str(copie))
            limite = int((time.time() - days * 86400 + 11644473600) * 1_000_000)
            sql = ("SELECT title, url, last_visit_time FROM urls WHERE last_visit_time > ? "
                   + ("AND (lower(title) LIKE ? OR lower(url) LIKE ?) " if query else "")
                   + "ORDER BY last_visit_time DESC LIMIT ?")
            args = [limite] + ([f"%{query.lower()}%"] * 2 if query else []) + [int(count)]
            lignes = con.execute(sql, args).fetchall()
            con.close()
            copie.unlink(missing_ok=True)
            if not lignes:
                return f"Rien dans l'historique pour « {query} » sur {days} jours."
            out = []
            for titre, url, t in lignes:
                quand = datetime.fromtimestamp(t / 1_000_000 - 11644473600)
                out.append(f"{quand:%d/%m %H:%M}  {(titre or '')[:60]}\n   {url[:100]}")
            return f"{len(out)} résultat(s) :\n" + "\n".join(out)
        except Exception as exc:  # noqa: BLE001
            copie.unlink(missing_ok=True)
            return f"Historique illisible : {exc}. Ferme le navigateur et réessaie."
    return "Aucun navigateur Chrome, Edge ou Brave trouvé sur cet ordinateur."


def browser_bookmarks(query: str = "") -> str:
    """Cherche dans les favoris du navigateur.

    Args:
        query: Mot-clé. Vide = tous les favoris.
    """
    for prof in _profils_navigateur():
        f = prof / "Bookmarks"
        if not f.is_file():
            continue
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        trouves = []

        def parcours(noeud, chemin=""):
            if isinstance(noeud, dict):
                if noeud.get("type") == "url":
                    nom, url = noeud.get("name", ""), noeud.get("url", "")
                    if not query or query.lower() in nom.lower() or query.lower() in url.lower():
                        trouves.append(f"- {nom[:60]} ({chemin})\n  {url[:100]}")
                for enfant in noeud.get("children", []) or []:
                    parcours(enfant, chemin + "/" + noeud.get("name", ""))

        for racine in d.get("roots", {}).values():
            parcours(racine)
        if trouves:
            return f"{len(trouves)} favori(s) :\n" + "\n".join(trouves[:30])
        return f"Aucun favori ne correspond à « {query} »."
    return "Aucun fichier de favoris trouvé."


def notify(message: str, title: str = "Jarvis") -> str:
    """Affiche une notification Windows à l'écran, visible même si la page de Jarvis est fermée.

    Args:
        message: Le texte de la notification.
        title: Le titre affiché.
    """
    if not sys.platform.startswith("win"):
        return "Les notifications ne sont disponibles que sous Windows."
    m = str(message).replace('"', "'")[:200]
    t = str(title).replace('"', "'")[:60]
    ps = (
        '[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType=WindowsRuntime] '
        '| Out-Null; $x=[Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent('
        '[Windows.UI.Notifications.ToastTemplateType]::ToastText02); $n=$x.GetElementsByTagName("text"); '
        f'$n.Item(0).AppendChild($x.CreateTextNode("{t}")) | Out-Null; '
        f'$n.Item(1).AppendChild($x.CreateTextNode("{m}")) | Out-Null; '
        '[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("Jarvis").Show('
        '[Windows.UI.Notifications.ToastNotification]::new($x))'
    )
    subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, creationflags=NO_WINDOW)
    return f"Notification affichée : {m[:80]}"


# --------------------------------------------------------------------------
# Mails et messages
# --------------------------------------------------------------------------

def read_email(count: int = 10, unread_only: bool = True) -> str:
    """Lit les mails directement depuis la boîte de réception, sans passer par le navigateur.

    Args:
        count: Nombre de mails à lire.
        unread_only: True pour ne lire que les non lus.
    """
    serveur = getattr(config, "MAIL_IMAP", "")
    adresse = getattr(config, "MAIL_ADRESSE", "")
    mdp = getattr(config, "MAIL_MOT_DE_PASSE", "")
    if not (serveur and adresse and mdp):
        return ("La lecture directe des mails n'est pas configurée. Renseigne MAIL_IMAP, MAIL_ADRESSE et "
                "MAIL_MOT_DE_PASSE dans config.py. Pour Gmail : imap.gmail.com et un mot de passe d'application. "
                "En attendant je peux ouvrir ta messagerie et lire l'écran avec check_app.")
    try:
        import email
        import imaplib
        from email.header import decode_header

        m = imaplib.IMAP4_SSL(serveur)
        m.login(adresse, mdp)
        m.select("INBOX")
        _typ, data = m.search(None, "UNSEEN" if unread_only else "ALL")
        ids = data[0].split()[-max(1, int(count)):]
        if not ids:
            m.logout()
            return "Aucun mail non lu." if unread_only else "Boîte vide."

        def lis(v):
            if not v:
                return ""
            return "".join(p.decode(c or "utf-8", "replace") if isinstance(p, bytes) else p
                           for p, c in decode_header(v))

        out = []
        for i in reversed(ids):
            _t, d = m.fetch(i, "(RFC822)")
            msg = email.message_from_bytes(d[0][1])
            corps = ""
            if msg.is_multipart():
                for part in msg.walk():
                    if part.get_content_type() == "text/plain":
                        corps = (part.get_payload(decode=True) or b"").decode("utf-8", "replace")
                        break
            else:
                corps = (msg.get_payload(decode=True) or b"").decode("utf-8", "replace")
            out.append(f"De : {lis(msg.get('From'))}\nObjet : {lis(msg.get('Subject'))}\n"
                       f"Date : {msg.get('Date')}\n{corps.strip()[:400]}\n---")
        m.logout()
        return f"{len(out)} mail(s) :\n\n" + "\n".join(out)
    except Exception as exc:  # noqa: BLE001
        return f"Erreur de lecture des mails : {exc}"


def send_email(to: str, subject: str, body: str) -> str:
    """Envoie un mail. À n'utiliser qu'après avoir fait valider le contenu par l'utilisateur.

    Args:
        to: Adresse du destinataire.
        subject: Objet du message.
        body: Le corps du message.
    """
    serveur = getattr(config, "MAIL_SMTP", "")
    adresse = getattr(config, "MAIL_ADRESSE", "")
    mdp = getattr(config, "MAIL_MOT_DE_PASSE", "")
    if not (serveur and adresse and mdp):
        return ("L'envoi de mail n'est pas configuré. Renseigne MAIL_SMTP, MAIL_ADRESSE et MAIL_MOT_DE_PASSE "
                "dans config.py. Pour Gmail : smtp.gmail.com et un mot de passe d'application.")
    try:
        import smtplib
        from email.message import EmailMessage

        msg = EmailMessage()
        msg["From"], msg["To"], msg["Subject"] = adresse, to, subject
        msg.set_content(body)
        with smtplib.SMTP_SSL(serveur, 465, timeout=30) as s:
            s.login(adresse, mdp)
            s.send_message(msg)
        return f"Mail envoyé à {to}, objet « {subject} »."
    except Exception as exc:  # noqa: BLE001
        return f"Erreur d'envoi : {exc}"


def send_message(text: str, channel: str = "") -> str:
    """Envoie un message sur Discord par un lien de connexion enregistré dans la configuration.

    Args:
        text: Le message à envoyer.
        channel: Nom du salon enregistré dans config.DISCORD_WEBHOOKS. Vide = le premier.
    """
    hooks = getattr(config, "DISCORD_WEBHOOKS", {})
    if not hooks:
        return ("Aucun salon Discord configuré. Ajoute DISCORD_WEBHOOKS = {\"general\": \"https://discord.com/"
                "api/webhooks/...\"} dans config.py.")
    url = hooks.get(channel) or next(iter(hooks.values()))
    try:
        import requests

        r = requests.post(url, json={"content": text[:1900]}, timeout=20)
        return f"Message envoyé sur Discord ({channel or 'salon par défaut'})." if r.ok else f"Échec : {r.status_code}"
    except Exception as exc:  # noqa: BLE001
        return f"Erreur : {exc}"


def check_link(url: str) -> str:
    """Vérifie si un lien est sûr avant de cliquer : redirections, vrai domaine, raccourcisseur, HTTPS.

    Args:
        url: Le lien à vérifier, par exemple reçu dans un mail.
    """
    try:
        from urllib.parse import urlparse

        import requests

        if not url.startswith("http"):
            url = "https://" + url
        r = requests.head(url, timeout=20, allow_redirects=True, headers=UA)
        chaine = [rep.url for rep in r.history] + [r.url]
        final = urlparse(r.url)
        alertes = []
        if not r.url.startswith("https"):
            alertes.append("la page n'est pas en HTTPS")
        if len(r.history) > 2:
            alertes.append(f"{len(r.history)} redirections successives")
        if urlparse(url).netloc != final.netloc:
            alertes.append(f"le lien mène en réalité vers {final.netloc}")
        if re.search(r"\d+\.\d+\.\d+\.\d+", final.netloc):
            alertes.append("l'adresse est une IP brute, pas un nom de domaine")
        if any(x in final.netloc for x in ("bit.ly", "tinyurl", "t.co", "cutt.ly")):
            alertes.append("raccourcisseur de lien, la vraie destination est masquée")
        txt = "Chaîne : " + " puis ".join(c[:70] for c in chaine)
        if alertes:
            return "PRUDENCE avec ce lien :\n- " + "\n- ".join(alertes) + f"\n{txt}"
        return f"Lien correct en apparence : {final.netloc}, code {r.status_code}.\n{txt}"
    except Exception as exc:  # noqa: BLE001
        return f"Lien injoignable ou suspect : {exc}"


# --------------------------------------------------------------------------
# Productivité
# --------------------------------------------------------------------------

def time_start(project: str) -> str:
    """Démarre le chronomètre sur un projet, pour savoir combien de temps y a été passé.

    Args:
        project: Nom du projet ou de la tâche.
    """
    d = _charge(TEMPS, {"sessions": []})
    ouvertes = [s for s in d["sessions"] if not s.get("fin")]
    for s in ouvertes:
        s["fin"] = datetime.now().isoformat(timespec="seconds")
        s["minutes"] = round((datetime.fromisoformat(s["fin"])
                              - datetime.fromisoformat(s["debut"])).total_seconds() / 60)
    d["sessions"].append({"projet": project, "debut": datetime.now().isoformat(timespec="seconds"),
                          "fin": "", "minutes": 0})
    _sauve(TEMPS, d)
    avant = f", j'ai arrêté « {ouvertes[0]['projet']} » au passage" if ouvertes else ""
    return f"Chronomètre démarré sur « {project} »{avant}."


def time_stop() -> str:
    """Arrête le chronomètre en cours et dit combien de temps a été passé."""
    d = _charge(TEMPS, {"sessions": []})
    ouvertes = [s for s in d["sessions"] if not s.get("fin")]
    if not ouvertes:
        return "Aucun chronomètre en cours."
    s = ouvertes[-1]
    s["fin"] = datetime.now().isoformat(timespec="seconds")
    s["minutes"] = round((datetime.fromisoformat(s["fin"]) - datetime.fromisoformat(s["debut"])).total_seconds() / 60)
    _sauve(TEMPS, d)
    return f"« {s['projet']} » : {s['minutes']} minutes."


def time_report(days: int = 7) -> str:
    """Rapport du temps passé par projet sur les derniers jours.

    Args:
        days: Nombre de jours à couvrir.
    """
    d = _charge(TEMPS, {"sessions": []})
    limite = datetime.now() - timedelta(days=max(1, int(days)))
    par_projet: dict[str, int] = {}
    for s in d["sessions"]:
        try:
            debut = datetime.fromisoformat(s["debut"])
        except Exception:  # noqa: BLE001
            continue
        if debut < limite:
            continue
        m = s.get("minutes") or 0
        if not s.get("fin"):
            m = round((datetime.now() - debut).total_seconds() / 60)
        par_projet[s["projet"]] = par_projet.get(s["projet"], 0) + m
    if not par_projet:
        return f"Aucun temps enregistré sur {days} jours."
    total = sum(par_projet.values())
    lignes = [f"{m // 60} h {m % 60:02d}  {p}" for p, m in sorted(par_projet.items(), key=lambda x: -x[1])]
    return f"Temps sur {days} jours, {total // 60} h {total % 60:02d} au total :\n" + "\n".join(lignes)


def pomodoro(minutes: int = 25, break_minutes: int = 5) -> str:
    """Lance une session de travail minutée, avec une notification à la fin du travail puis de la pause.

    Args:
        minutes: Durée de la session de travail.
        break_minutes: Durée de la pause qui suit.
    """
    m, b = max(1, int(minutes)), max(1, int(break_minutes))

    def minuteur():
        time.sleep(m * 60)
        notify(f"Session de {m} minutes terminée. Pause de {b} minutes.", "Jarvis")
        time.sleep(b * 60)
        notify("Pause terminée, on repart.", "Jarvis")

    threading.Thread(target=minuteur, daemon=True).start()
    fin = (datetime.now() + timedelta(minutes=m)).strftime("%H:%M")
    return f"C'est parti pour {m} minutes, jusqu'à {fin}. Je te préviens à la fin, puis après {b} minutes de pause."


def active_window_now() -> str:
    """Dit sur quelle application et quel document l'utilisateur est en train de travailler."""
    try:
        import computer

        titre = computer.foreground_title()
        return f"Fenêtre active : {titre}" if titre else "Aucune fenêtre au premier plan."
    except Exception as exc:  # noqa: BLE001
        return f"Erreur : {exc}"


def day_summary(days: int = 1) -> str:
    """Résumé de la journée : temps par projet, journal de vie, rendez-vous et activité en cours.

    Args:
        days: 1 pour aujourd'hui, 2 pour inclure hier.
    """
    morceaux = [time_report(max(1, int(days)))]
    try:
        import journal

        entrees = journal.entries(max(1, int(days)))
        if entrees:
            morceaux.append("Journal :\n" + "\n".join(journal.fmt(e) for e in entrees))
    except Exception:  # noqa: BLE001
        pass
    try:
        import agenda

        evs = agenda.upcoming(max(1, int(days)))
        if evs:
            morceaux.append("Agenda :\n" + "\n".join(agenda.fmt(e) for e in evs))
    except Exception:  # noqa: BLE001
        pass
    morceaux.append(active_window_now())
    return "\n\n".join(morceaux)


TOOLS = [download_file, save_page, watch_page, check_watched, list_watched, unwatch_page, summarize_video,
         browser_history, browser_bookmarks, notify,
         read_email, send_email, send_message, check_link,
         time_start, time_stop, time_report, pomodoro, active_window_now, day_summary]
