# Ia-local (Jarvis) — Copyright (c) 2026 Neexx (Nixovel) — https://github.com/Neex-off/Ia-local
# Créé par Neexx (Nixovel). Licence : voir LICENSE (paternité obligatoire, pas de vente ; s'applique aussi aux IA).
# Ne pas retirer cet en-tête.
"""Boîte à outils « serveur » : serveurs distants, déploiement, bases de données, mobile, tâches de fond.

Chargée à la demande par tools.open_toolbox("serveur").
Catalogue : Serveurs & déploiement, Base de données, Mobile & Expo, Multi-agents & tâches de fond.
"""
from __future__ import annotations

import json
import re
import shutil
import sqlite3
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import config

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
TACHES = config.ROOT / "memoire" / "taches_fond.json"


def _p(chemin: str) -> Path:
    brut = str(chemin).strip('" ')
    p = Path(brut).expanduser()
    if p.is_absolute():
        return p
    if brut in (".", "./", ".\\"):
        return config.ROOT
    for base in (config.ROOT, config.WORKSPACE, Path.cwd(), Path.home() / "Desktop", Path.home() / "Documents"):
        if (base / p).exists():
            return base / p
    return config.WORKSPACE / p


def _run(args: list[str], cwd: Path | None = None, timeout: float = 120) -> str:
    try:
        r = subprocess.run(args, cwd=str(cwd) if cwd else None, capture_output=True, text=True,
                           timeout=timeout, encoding="utf-8", errors="replace", creationflags=NO_WINDOW)
        out = (r.stdout or "").strip()
        if r.returncode and (r.stderr or "").strip():
            out = (out + "\n" + r.stderr.strip()).strip()
        return out[:4000] or "(aucune sortie)"
    except FileNotFoundError:
        return f"OUTIL_ABSENT:{args[0]}"
    except subprocess.TimeoutExpired:
        return "La commande a mis trop de temps."
    except Exception as exc:  # noqa: BLE001
        return f"Erreur : {exc}"


def _serveurs() -> dict:
    """Serveurs déclarés dans config.SERVEURS = {"nom": "utilisateur@adresse"}."""
    return getattr(config, "SERVEURS", {})


def _ssh(server: str, command: str, timeout: float = 90) -> str:
    if not shutil.which("ssh"):
        return "Le client SSH n'est pas installé sur cet ordinateur."
    cible = _serveurs().get(server, server)
    out = _run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=12", cible, command], timeout=timeout)
    return "Le client SSH n'est pas installé." if out.startswith("OUTIL_ABSENT") else out


# --------------------------------------------------------------------------
# Serveurs distants
# --------------------------------------------------------------------------

def list_servers() -> str:
    """Liste les serveurs distants déclarés dans la configuration."""
    s = _serveurs()
    if not s:
        return ("Aucun serveur déclaré. Ajoute SERVEURS = {\"prod\": \"root@monsite.fr\"} dans config.py, "
                "avec une clé SSH déjà en place pour se connecter sans mot de passe.")
    return "Serveurs connus :\n" + "\n".join(f"- {nom} : {cible}" for nom, cible in s.items())


def server_status(server: str) -> str:
    """État d'un serveur distant : temps de fonctionnement, charge, mémoire et espace disque.

    Args:
        server: Nom du serveur déclaré dans la configuration, ou "utilisateur@adresse".
    """
    out = _ssh(server, "uptime; echo '---'; free -h 2>/dev/null | head -3; echo '---'; df -h / | tail -2")
    return f"Serveur {server} :\n{out}"


def server_logs(server: str, service: str = "", lines: int = 40) -> str:
    """Lit les derniers journaux d'un serveur distant et met en avant les erreurs.

    Args:
        server: Nom du serveur.
        service: Nom du service, par exemple "nginx". Vide = journal général.
        lines: Nombre de lignes.
    """
    n = max(10, min(200, int(lines)))
    cmd = f"journalctl -u {service} -n {n} --no-pager" if service else f"journalctl -n {n} --no-pager"
    out = _ssh(server, cmd, timeout=120)
    erreurs = [l for l in out.splitlines() if re.search(r"error|erreur|fail|fatal|critical", l, re.I)]
    if erreurs:
        return f"{len(erreurs)} ligne(s) d'erreur sur {server} :\n" + "\n".join(erreurs[-20:])
    return f"Aucune erreur dans les {n} dernières lignes de {server}.\n{out[-1200:]}"


def server_restart_service(server: str, service: str) -> str:
    """Redémarre un service sur un serveur distant et vérifie qu'il est bien reparti.

    Args:
        server: Nom du serveur.
        service: Nom du service, par exemple "nginx" ou "postgresql".
    """
    out = _ssh(server, f"sudo systemctl restart {service} && sleep 2 && systemctl is-active {service}", timeout=120)
    etat = "actif" if "active" in out and "inactive" not in out else "PROBLÈME"
    return f"{service} sur {server} : {etat}.\n{out[-600:]}"


def server_updates(server: str, install: bool = False) -> str:
    """Vérifie ou installe les mises à jour de sécurité d'un serveur distant.

    Args:
        server: Nom du serveur.
        install: False pour seulement lister, True pour installer.
    """
    if install:
        return _ssh(server, "sudo apt-get update -qq && sudo apt-get -y upgrade", timeout=900)[-1500:]
    out = _ssh(server, "apt list --upgradable 2>/dev/null | tail -30", timeout=180)
    n = len([l for l in out.splitlines() if "/" in l])
    return f"{n} paquet(s) à mettre à jour sur {server} :\n{out[-1200:]}"


def ssh_run(server: str, command: str) -> str:
    """Exécute une commande sur un serveur distant par SSH.

    Args:
        server: Nom du serveur.
        command: La commande à lancer.
    """
    return f"$ {command}\n{_ssh(server, command, timeout=300)}"


def dns_records(domain: str) -> str:
    """Montre les enregistrements DNS d'un domaine : où pointent le site et les mails.

    Args:
        domain: Le nom de domaine, par exemple "monsite.fr".
    """
    hote = re.sub(r"^https?://", "", domain).split("/")[0]
    out = []
    for genre in ("A", "AAAA", "MX", "TXT", "NS"):
        if shutil.which("nslookup"):
            r = _run(["nslookup", "-type=" + genre, hote], timeout=30)
        else:
            r = _run(["dig", "+short", genre, hote], timeout=30)
        lignes = [l.strip() for l in r.splitlines()
                  if l.strip() and not l.lower().startswith(("serveur", "server", "address:", "adresse"))]
        if lignes:
            out.append(f"{genre} : " + " | ".join(lignes[:4]))
    return f"DNS de {hote} :\n" + "\n".join(out) if out else f"Aucun enregistrement trouvé pour {hote}."


def deploy_site(folder: str, target: str = "auto") -> str:
    """Publie un site ou une application en ligne.

    Args:
        folder: Dossier du projet.
        target: "auto", "git", "vercel" ou "netlify".
    """
    d = _p(folder)
    if not d.is_dir():
        return f"Dossier introuvable : {d}"
    t = target.lower()
    if t == "auto":
        if (d / "vercel.json").is_file() or (d / ".vercel").is_dir():
            t = "vercel"
        elif (d / "netlify.toml").is_file():
            t = "netlify"
        else:
            t = "git"
    if t == "vercel":
        out = _run(["npx", "--yes", "vercel", "--prod", "--yes"], d, 900)
        url = re.search(r"https://\S+", out)
        return f"Déployé sur Vercel : {url.group(0) if url else out[-500:]}"
    if t == "netlify":
        return f"Déploiement Netlify :\n{_run(['npx', '--yes', 'netlify-cli', 'deploy', '--prod', '--dir', '.'], d, 900)[-800:]}"
    branche = _run(["git", "branch", "--show-current"], d, 30)
    out = _run(["git", "push"], d, 300)
    return (f"Poussé sur la branche {branche}. Si un déploiement automatique est branché, il démarre "
            f"maintenant.\n{out[-500:]}")


def rollback_deploy(folder: str) -> str:
    """Revient à la version précédente du projet en annulant le dernier changement publié.

    Args:
        folder: Dossier du projet.
    """
    d = _p(folder)
    if not (d / ".git").is_dir():
        return f"{d} n'est pas un dépôt git, je ne peux pas revenir en arrière."
    dernier = _run(["git", "log", "-1", "--pretty=format:%h %s"], d, 30)
    out = _run(["git", "revert", "--no-edit", "HEAD"], d, 60)
    return f"Annulation du dernier changement ({dernier}) :\n{out[-500:]}\nPense à republier avec deploy_site."


def status_page(urls: str, destination: str = "statut.html") -> str:
    """Crée une page qui montre si tes sites sont en ligne, avec leur temps de réponse.

    Args:
        urls: Les adresses à surveiller, séparées par des points-virgules.
        destination: Le fichier HTML à créer.
    """
    try:
        import requests

        lignes = []
        for u in [x.strip() for x in urls.split(";") if x.strip()]:
            adresse = u if u.startswith("http") else "https://" + u
            try:
                t0 = time.time()
                r = requests.get(adresse, timeout=20, headers={"User-Agent": "Mozilla/5.0 (agent local)"})
                lignes.append((adresse, r.status_code < 400, f"{r.status_code}, {(time.time() - t0) * 1000:.0f} ms"))
            except Exception as exc:  # noqa: BLE001
                lignes.append((adresse, False, str(exc)[:60]))
        html = ["<!doctype html><meta charset='utf-8'><title>Statut</title>",
                "<style>body{font:16px system-ui;background:#0b1220;color:#e8eef8;padding:40px}",
                ".l{display:flex;gap:12px;align-items:center;padding:10px 0;border-bottom:1px solid #1e2a3e}",
                ".p{width:10px;height:10px;border-radius:50%}.ok{background:#22c55e}.ko{background:#ef4444}",
                ".d{color:#8aa0bd;margin-left:auto}</style>",
                f"<h1>Statut des services</h1><p class='d'>Vérifié le {datetime.now():%d/%m/%Y à %H:%M}</p>"]
        for adresse, ok, detail in lignes:
            html.append(f"<div class='l'><span class='p {'ok' if ok else 'ko'}'></span>"
                        f"<a href='{adresse}' style='color:inherit'>{adresse}</a>"
                        f"<span class='d'>{detail}</span></div>")
        d = _p(destination)
        d.write_text("\n".join(html), encoding="utf-8")
        return f"Page de statut créée : {d}. {sum(1 for _a, ok, _d in lignes if ok)} service(s) en ligne sur {len(lignes)}."
    except Exception as exc:  # noqa: BLE001
        return f"Erreur : {exc}"


# --------------------------------------------------------------------------
# Bases de données
# --------------------------------------------------------------------------

def _sqlite(database: str) -> Path | None:
    p = _p(database)
    return p if p.is_file() and p.suffix.lower() in (".db", ".sqlite", ".sqlite3", ".db3") else None


def db_schema(database: str) -> str:
    """Montre la structure d'une base de données : ses tables, ses colonnes et le nombre de lignes.

    Args:
        database: Chemin d'un fichier SQLite, ou adresse de connexion PostgreSQL.
    """
    p = _sqlite(database)
    if p:
        con = sqlite3.connect(str(p))
        tables = [r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
        out = [f"Base SQLite {p.name}, {len(tables)} table(s) :"]
        for t in tables:
            cols = con.execute(f"PRAGMA table_info({t})").fetchall()
            n = con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            out.append(f"\n{t}, {n} lignes : " + ", ".join(f"{c[1]} {c[2]}" for c in cols))
        con.close()
        return "\n".join(out)
    if shutil.which("psql"):
        return _run(["psql", database, "-c", "\\dt+"], timeout=60)
    return "Base non reconnue. Donne le chemin d'un fichier SQLite, ou installe psql pour PostgreSQL."


def db_query(database: str, sql: str) -> str:
    """Exécute une requête de LECTURE sur une base de données et montre le résultat.

    Args:
        database: Chemin d'un fichier SQLite, ou adresse de connexion PostgreSQL.
        sql: La requête SELECT.
    """
    if not re.match(r"^\s*(select|with|pragma|explain)\b", sql, re.I):
        return ("Cette fonction ne fait que lire. Pour modifier des données, utilise db_write "
                "après avoir fait confirmer par l'utilisateur.")
    p = _sqlite(database)
    if p:
        try:
            con = sqlite3.connect(str(p))
            cur = con.execute(sql)
            colonnes = [c[0] for c in cur.description] if cur.description else []
            lignes = cur.fetchmany(60)
            con.close()
            if not lignes:
                return "Aucun résultat."
            out = [" | ".join(colonnes)] + [" | ".join(str(v)[:30] for v in l) for l in lignes]
            return f"{len(lignes)} ligne(s) :\n" + "\n".join(out)
        except Exception as exc:  # noqa: BLE001
            return f"Erreur SQL : {exc}"
    if shutil.which("psql"):
        return _run(["psql", database, "-c", sql], timeout=120)
    return "Base non reconnue ou psql absent."


def db_write(database: str, sql: str) -> str:
    """Exécute une requête qui MODIFIE une base de données. Une sauvegarde est faite avant.

    Args:
        database: Chemin d'un fichier SQLite, ou adresse de connexion PostgreSQL.
        sql: La requête INSERT, UPDATE, DELETE ou CREATE.
    """
    p = _sqlite(database)
    if p:
        sauvegarde = p.with_name(f"{p.stem}_avant_{datetime.now():%Y%m%d_%H%M%S}{p.suffix}")
        shutil.copy2(p, sauvegarde)
        try:
            con = sqlite3.connect(str(p))
            cur = con.execute(sql)
            con.commit()
            n = cur.rowcount
            con.close()
            return f"{n} ligne(s) modifiées. Sauvegarde avant modification : {sauvegarde.name}"
        except Exception as exc:  # noqa: BLE001
            return f"Erreur SQL : {exc}. La base n'a pas été modifiée, sauvegarde dans {sauvegarde.name}"
    if shutil.which("psql"):
        return _run(["psql", database, "-c", sql], timeout=120)
    return "Base non reconnue ou psql absent."


def db_export_csv(database: str, table: str) -> str:
    """Exporte une table de base de données en fichier CSV.

    Args:
        database: Chemin d'un fichier SQLite.
        table: Nom de la table.
    """
    import csv

    p = _sqlite(database)
    if not p:
        return "Donne le chemin d'un fichier SQLite."
    try:
        con = sqlite3.connect(str(p))
        cur = con.execute(f"SELECT * FROM {table}")
        colonnes = [c[0] for c in cur.description]
        d = config.WORKSPACE / f"{table}.csv"
        n = 0
        with open(d, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f, delimiter=";")
            w.writerow(colonnes)
            for ligne in cur:
                w.writerow(ligne)
                n += 1
        con.close()
        return f"{n} ligne(s) exportées dans {d}"
    except Exception as exc:  # noqa: BLE001
        return f"Erreur : {exc}"


def db_import_csv(database: str, table: str, csv_file: str) -> str:
    """Importe un fichier CSV dans une table de base de données.

    Args:
        database: Chemin d'un fichier SQLite.
        table: Nom de la table à remplir.
        csv_file: Le fichier CSV à importer.
    """
    import csv

    p = _sqlite(database)
    c = _p(csv_file)
    if not p:
        return "Donne le chemin d'un fichier SQLite."
    if not c.is_file():
        return f"CSV introuvable : {c}"
    try:
        premiere = c.open(encoding="utf-8-sig").readline()
        sep = ";" if premiere.count(";") >= premiere.count(",") else ","
        with open(c, newline="", encoding="utf-8-sig") as f:
            lecteur = csv.reader(f, delimiter=sep)
            entetes = next(lecteur)
            lignes = list(lecteur)
        con = sqlite3.connect(str(p))
        con.executemany(f"INSERT INTO {table} ({','.join(entetes)}) VALUES ({','.join('?' * len(entetes))})", lignes)
        con.commit()
        con.close()
        return f"{len(lignes)} ligne(s) importées dans {table}."
    except Exception as exc:  # noqa: BLE001
        return f"Erreur : {exc}"


def db_health(database: str) -> str:
    """Analyse une base de données : taille, tables les plus lourdes, index probablement manquants.

    Args:
        database: Chemin d'un fichier SQLite.
    """
    p = _sqlite(database)
    if not p:
        return "Donne le chemin d'un fichier SQLite."
    try:
        con = sqlite3.connect(str(p))
        tables = [r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
        infos, sansindex = [], []
        for t in tables:
            n = con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            idx = con.execute(f"PRAGMA index_list({t})").fetchall()
            infos.append((n, t, len(idx)))
            cols = [c[1] for c in con.execute(f"PRAGMA table_info({t})").fetchall()]
            candidats = [c for c in cols if c.lower().endswith("_id") or c.lower() in ("email", "slug")]
            if n > 500 and candidats and not idx:
                sansindex.append(f"{t}, {n} lignes : penser à indexer {', '.join(candidats[:3])}")
        con.close()
        infos.sort(key=lambda x: -x[0])
        out = [f"Base {p.name}, {p.stat().st_size / 2**20:.1f} Mo, {len(tables)} table(s).", "",
               "Tables les plus remplies :"]
        out += [f"  {n:8d} lignes  {t}, {i} index" for n, t, i in infos[:10]]
        if sansindex:
            out += ["", "Index probablement manquants :"] + [f"  - {s}" for s in sansindex]
        return "\n".join(out)
    except Exception as exc:  # noqa: BLE001
        return f"Erreur : {exc}"


# --------------------------------------------------------------------------
# Mobile
# --------------------------------------------------------------------------

def expo_start(folder: str) -> str:
    """Démarre une application mobile Expo et affiche le QR code pour la tester sur le téléphone.

    Args:
        folder: Dossier du projet.
    """
    d = _p(folder)
    if not (d / "package.json").is_file():
        return f"{d} ne ressemble pas à un projet Expo, il n'y a pas de package.json."
    try:
        drapeau = getattr(subprocess, "CREATE_NEW_CONSOLE", 0) if sys.platform.startswith("win") else 0
        subprocess.Popen(["npx", "expo", "start"], cwd=str(d), creationflags=drapeau)
        return ("Expo démarre dans une fenêtre à part. Le QR code s'y affiche, scanne-le avec "
                "l'application Expo Go sur ton téléphone.")
    except FileNotFoundError:
        return "Node.js n'est pas installé, je ne peux pas démarrer Expo."


def android_emulator(name: str = "") -> str:
    """Lance l'émulateur Android pour tester une application sans téléphone branché.

    Args:
        name: Nom de l'appareil virtuel. Vide = le premier disponible.
    """
    import os

    sdk = os.environ.get("ANDROID_HOME") or str(Path.home() / "AppData/Local/Android/Sdk")
    emu = Path(sdk) / "emulator" / ("emulator.exe" if sys.platform.startswith("win") else "emulator")
    if not emu.is_file():
        return "L'émulateur Android est introuvable. Installe Android Studio et ses outils."
    avds = [l.strip() for l in _run([str(emu), "-list-avds"], timeout=30).splitlines()
            if l.strip() and "OUTIL" not in l]
    if not avds:
        return "Aucun appareil virtuel créé. Ouvre Android Studio et crée un appareil dans Device Manager."
    cible = name if name in avds else avds[0]
    subprocess.Popen([str(emu), "-avd", cible], creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0))
    return f"Émulateur « {cible} » en cours de démarrage. Appareils disponibles : {', '.join(avds)}"


def generate_app_icons(logo: str, folder: str = "") -> str:
    """Génère toutes les icônes et l'écran de démarrage d'une application mobile à partir d'un logo.

    Args:
        logo: Le logo de départ, idéalement carré et en haute résolution.
        folder: Dossier où déposer les images. Vide = un sous-dossier à côté du logo.
    """
    try:
        from PIL import Image

        p = _p(logo)
        if not p.is_file():
            return f"Introuvable : {p}"
        dossier = _p(folder) if folder else p.parent / "icones"
        dossier.mkdir(parents=True, exist_ok=True)
        img = Image.open(p).convert("RGBA")
        faits = []
        for taille in (1024, 512, 192, 180, 144, 96, 72, 48):
            img.resize((taille, taille), Image.LANCZOS).save(dossier / f"icon-{taille}.png")
            faits.append(str(taille))
        splash = Image.new("RGBA", (1284, 2778), img.getpixel((1, 1)))
        logo_grand = img.resize((512, 512), Image.LANCZOS)
        splash.paste(logo_grand, ((1284 - 512) // 2, (2778 - 512) // 2), logo_grand)
        splash.convert("RGB").save(dossier / "splash.png")
        return f"Icônes {', '.join(faits)} et écran de démarrage créés dans {dossier}"
    except Exception as exc:  # noqa: BLE001
        return f"Erreur : {exc}"


# --------------------------------------------------------------------------
# Tâches de fond
# --------------------------------------------------------------------------

def _charge_taches() -> dict:
    if not TACHES.is_file():
        return {"taches": []}
    try:
        return json.loads(TACHES.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {"taches": []}


def background_task(command: str, name: str = "") -> str:
    """Lance une commande longue en arrière-plan et garde son journal, pour la consulter plus tard.

    Args:
        command: La commande à exécuter.
        name: Un nom court pour la retrouver.
    """
    nom = name or re.sub(r"[^a-zA-Z0-9]+", "-", command)[:25]
    journal = config.WORKSPACE / f"tache_{nom}_{datetime.now():%H%M%S}.log"
    try:
        f = open(journal, "w", encoding="utf-8")
        shell = (["powershell", "-NoProfile", "-Command", command] if sys.platform.startswith("win")
                 else ["bash", "-lc", command])
        p = subprocess.Popen(shell, stdout=f, stderr=subprocess.STDOUT, creationflags=NO_WINDOW)
        d = _charge_taches()
        d["taches"].append({"nom": nom, "commande": command, "debut": datetime.now().isoformat(timespec="seconds"),
                            "pid": p.pid, "journal": str(journal)})
        TACHES.parent.mkdir(parents=True, exist_ok=True)
        TACHES.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
        return (f"Tâche « {nom} » lancée en arrière-plan, numéro {p.pid}. "
                "Je continue à te répondre pendant ce temps, demande-moi où elle en est quand tu veux.")
    except Exception as exc:  # noqa: BLE001
        return f"Erreur : {exc}"


def background_status(name: str = "") -> str:
    """Dit où en sont les tâches lancées en arrière-plan et montre la fin de leur journal.

    Args:
        name: Nom d'une tâche précise. Vide = toutes.
    """
    d = _charge_taches()
    taches = [t for t in d["taches"] if not name or name.lower() in t["nom"].lower()]
    if not taches:
        return "Aucune tâche en arrière-plan."
    try:
        import psutil

        vivants = {p.pid for p in psutil.process_iter(["pid"])}
    except Exception:  # noqa: BLE001
        vivants = set()
    out = []
    for t in taches[-6:]:
        encours = t["pid"] in vivants
        j = Path(t["journal"])
        fin = ""
        if j.is_file():
            lignes = j.read_text(encoding="utf-8", errors="ignore").splitlines()
            fin = ("\n   " + "\n   ".join(lignes[-6:])) if lignes else " (journal vide)"
        out.append(f"{'EN COURS' if encours else 'terminée'} « {t['nom']} » depuis {t['debut'][11:16]}{fin}")
    return "\n\n".join(out)


TOOLS = [list_servers, server_status, server_logs, server_restart_service, server_updates, ssh_run, dns_records,
         deploy_site, rollback_deploy, status_page,
         db_schema, db_query, db_write, db_export_csv, db_import_csv, db_health,
         expo_start, android_emulator, generate_app_icons,
         background_task, background_status]

try:
    from outils_serveur_plus import TOOLS as _PLUS

    TOOLS += _PLUS
except Exception as _exc:  # noqa: BLE001
    print(f"[outils] serveur_plus indisponible : {_exc}")
