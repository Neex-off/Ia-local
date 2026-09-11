# Ia-local (Jarvis) — Copyright (c) 2026 Neexx (Nixovel) — https://github.com/Neex-off/Ia-local
# Créé par Neexx (Nixovel). Licence : voir LICENSE (paternité obligatoire, pas de vente ; s'applique aussi aux IA).
# Ne pas retirer cet en-tête.
"""Boîte à outils « code » : qualité du code, tests, dépendances, API et outils web.

Chargée à la demande par tools.open_toolbox("code"). Catalogue : modules Qualité de code et API & outils web dev.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import config

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _p(chemin: str) -> Path:
    brut = str(chemin).strip('" ')
    p = Path(brut).expanduser()
    if p.is_absolute():
        return p
    if brut in (".", "./", ".\\"):
        return config.ROOT
    for base in (config.ROOT, config.WORKSPACE, Path.cwd(), Path.home() / "Desktop"):
        if (base / p).exists():
            return base / p
    return config.WORKSPACE / p


def _run(args: list[str], cwd: Path | None = None, timeout: float = 180) -> str:
    try:
        r = subprocess.run(args, cwd=str(cwd) if cwd else None, capture_output=True, text=True,
                           timeout=timeout, encoding="utf-8", errors="replace", creationflags=NO_WINDOW)
        out = (r.stdout or "").strip()
        if (r.stderr or "").strip():
            out = (out + "\n" + r.stderr.strip()).strip()
        return out[:4000] or "(aucune sortie)"
    except FileNotFoundError:
        return f"OUTIL_ABSENT:{args[0]}"
    except subprocess.TimeoutExpired:
        return "Erreur : la commande a mis trop de temps."
    except Exception as exc:  # noqa: BLE001
        return f"Erreur : {exc}"


def _kind(d: Path) -> str:
    """Type de projet : python, node, rust ou autre."""
    if (d / "package.json").is_file():
        return "node"
    if (d / "Cargo.toml").is_file():
        return "rust"
    if any((d / f).is_file() for f in ("pyproject.toml", "requirements.txt", "setup.py")) or list(d.glob("*.py")):
        return "python"
    return "autre"


def _try(*commandes, cwd=None, timeout=180) -> str:
    """Essaie plusieurs commandes et renvoie la sortie de la première qui existe."""
    absents = []
    for cmd in commandes:
        out = _run(cmd, cwd, timeout)
        if out.startswith("OUTIL_ABSENT:"):
            absents.append(out.split(":", 1)[1])
            continue
        return out
    return f"Aucun outil disponible. Manquants : {', '.join(absents)}. Installe-les avec install_package."


# --------------------------------------------------------------------------
# Qualité de code
# --------------------------------------------------------------------------

def lint_code(folder: str) -> str:
    """Analyse le code d'un projet et signale les erreurs de style et les problèmes détectés.

    Args:
        folder: Dossier du projet.
    """
    d = _p(folder)
    k = _kind(d)
    if k == "node":
        return _try(["npx", "--yes", "eslint", ".", "--max-warnings", "50"], cwd=d)
    if k == "rust":
        return _try(["cargo", "clippy"], cwd=d)
    return _try([sys.executable, "-m", "ruff", "check", "."], [sys.executable, "-m", "flake8", "."], cwd=d)


def format_code(folder: str) -> str:
    """Reformate automatiquement tout le code d'un projet selon les conventions du langage.

    Args:
        folder: Dossier du projet.
    """
    d = _p(folder)
    k = _kind(d)
    if k == "node":
        return _try(["npx", "--yes", "prettier", "--write", "."], cwd=d)
    if k == "rust":
        return _try(["cargo", "fmt"], cwd=d)
    return _try([sys.executable, "-m", "ruff", "format", "."], [sys.executable, "-m", "black", "."], cwd=d)


def run_tests(folder: str) -> str:
    """Lance les tests automatisés d'un projet et montre ce qui passe et ce qui échoue.

    Args:
        folder: Dossier du projet.
    """
    d = _p(folder)
    k = _kind(d)
    if k == "node":
        return _try(["npm", "test"], cwd=d, timeout=600)
    if k == "rust":
        return _try(["cargo", "test"], cwd=d, timeout=600)
    return _try([sys.executable, "-m", "pytest", "-q"], cwd=d, timeout=600)


def test_coverage(folder: str) -> str:
    """Mesure quelle part du code est réellement couverte par les tests.

    Args:
        folder: Dossier du projet.
    """
    d = _p(folder)
    if _kind(d) == "node":
        return _try(["npm", "run", "coverage"], ["npx", "--yes", "jest", "--coverage"], cwd=d, timeout=600)
    return _try([sys.executable, "-m", "pytest", "--cov", "--cov-report=term-missing", "-q"], cwd=d, timeout=600)


def dead_code(folder: str) -> str:
    """Trouve le code mort : fonctions, variables et fichiers qui ne servent plus à rien.

    Args:
        folder: Dossier du projet.
    """
    d = _p(folder)
    if _kind(d) == "node":
        return _try(["npx", "--yes", "knip"], ["npx", "--yes", "ts-prune"], cwd=d, timeout=300)
    return _try([sys.executable, "-m", "vulture", "."], cwd=d, timeout=300)


def type_check(folder: str) -> str:
    """Vérifie la cohérence des types dans le code et signale les erreurs.

    Args:
        folder: Dossier du projet.
    """
    d = _p(folder)
    if _kind(d) == "node":
        return _try(["npx", "--yes", "tsc", "--noEmit"], cwd=d, timeout=300)
    return _try([sys.executable, "-m", "mypy", "."], cwd=d, timeout=300)


def audit_deps(folder: str) -> str:
    """Cherche les bibliothèques du projet qui ont une faille de sécurité connue.

    Args:
        folder: Dossier du projet.
    """
    d = _p(folder)
    if _kind(d) == "node":
        return _try(["npm", "audit"], cwd=d, timeout=300)
    return _try([sys.executable, "-m", "pip_audit"], [sys.executable, "-m", "safety", "check"], cwd=d, timeout=300)


def check_licenses(folder: str) -> str:
    """Liste les licences des bibliothèques utilisées, pour vérifier qu'on a le droit de s'en servir.

    Args:
        folder: Dossier du projet.
    """
    d = _p(folder)
    if _kind(d) == "node":
        return _try(["npx", "--yes", "license-checker", "--summary"], cwd=d, timeout=300)
    return _try([sys.executable, "-m", "piplicenses", "--summary"],
                [sys.executable, "-m", "pip", "list", "--format=json"], cwd=d, timeout=180)


def update_deps(folder: str) -> str:
    """Met à jour les bibliothèques du projet, puis relance les tests pour vérifier que rien n'est cassé.

    Args:
        folder: Dossier du projet.
    """
    d = _p(folder)
    maj = _try(["npm", "update"], cwd=d, timeout=900) if _kind(d) == "node" else \
        _try([sys.executable, "-m", "pip", "install", "--upgrade", "-r", "requirements.txt"], cwd=d, timeout=900)
    return f"Mise à jour :\n{maj[:1200]}\n\nTests après mise à jour :\n{run_tests(folder)[:1200]}"


def bundle_size(folder: str) -> str:
    """Mesure le poids du site ou de l'application une fois compilé, fichier par fichier.

    Args:
        folder: Dossier du projet.
    """
    d = _p(folder)
    for nom in ("dist", "build", ".next", "out"):
        cible = d / nom
        if cible.is_dir():
            tailles = sorted(((f.stat().st_size, f) for f in cible.rglob("*") if f.is_file()), key=lambda x: -x[0])
            total = sum(t for t, _f in tailles)
            lignes = [f"{t / 1024:8.0f} Ko  {f.relative_to(cible)}" for t, f in tailles[:20]]
            return f"Dossier {nom}, {total / 2**20:.1f} Mo au total :\n" + "\n".join(lignes)
    return f"Aucun dossier compilé dans {d}. Compile d'abord le projet, par exemple avec npm run build."


def profile_code(file: str) -> str:
    """Mesure le temps passé dans chaque fonction d'un script Python, pour trouver ce qui est lent.

    Args:
        file: Le fichier Python à analyser.
    """
    p = _p(file)
    if not p.is_file():
        return f"Introuvable : {p}"
    return _run([sys.executable, "-m", "cProfile", "-s", "cumtime", str(p)], p.parent, 300)[:2500]


def read_logs(path: str, lines: int = 60, errors_only: bool = True) -> str:
    """Lit la fin d'un fichier de journal et met en avant les erreurs, pour comprendre un plantage.

    Args:
        path: Chemin du fichier de journal.
        lines: Nombre de lignes à examiner depuis la fin.
        errors_only: True pour ne garder que les lignes d'erreur.
    """
    p = _p(path)
    if not p.is_file():
        return f"Introuvable : {p}"
    contenu = p.read_text(encoding="utf-8", errors="ignore").splitlines()[-max(10, int(lines)):]
    if errors_only:
        motifs = ("error", "erreur", "exception", "traceback", "failed", "échec", "fatal", "critical")
        gardees = [l for l in contenu if any(m in l.lower() for m in motifs)]
        if gardees:
            return f"{len(gardees)} ligne(s) d'erreur dans {p.name} :\n" + "\n".join(gardees[-30:])
        return f"Aucune erreur dans les {len(contenu)} dernières lignes de {p.name}."
    return f"Fin de {p.name} :\n" + "\n".join(contenu)


# --------------------------------------------------------------------------
# API et outils web
# --------------------------------------------------------------------------

def test_api(url: str, method: str = "GET", body: str = "", headers: str = "") -> str:
    """Interroge une API et montre le code de réponse, le temps, les en-têtes et le contenu reçu.

    Args:
        url: L'adresse de l'API.
        method: "GET", "POST", "PUT", "PATCH" ou "DELETE".
        body: Le corps de la requête en JSON, pour POST et PUT.
        headers: En-têtes au format "Cle: valeur" séparés par des points-virgules.
    """
    try:
        import requests

        h = {}
        for morceau in str(headers).split(";"):
            if ":" in morceau:
                k, v = morceau.split(":", 1)
                h[k.strip()] = v.strip()
        data = None
        if body.strip():
            try:
                data = json.loads(body)
                h.setdefault("Content-Type", "application/json")
            except json.JSONDecodeError:
                return "Le corps de la requête n'est pas du JSON valide."
        r = requests.request(method.upper(), url, json=data, headers=h, timeout=30)
        return (f"{method.upper()} {url}\nCode : {r.status_code} {r.reason} en {r.elapsed.total_seconds():.2f} s\n"
                f"Type : {r.headers.get('Content-Type', '?')}\n\n{r.text[:1500]}")
    except Exception as exc:  # noqa: BLE001
        return f"Erreur : {exc}"


def decode_jwt(token: str) -> str:
    """Décode un jeton d'authentification JWT et montre son contenu et sa date d'expiration.

    Args:
        token: Le jeton, avec ou sans le préfixe Bearer.
    """
    import base64
    from datetime import datetime

    t = token.strip().replace("Bearer ", "")
    morceaux = t.split(".")
    if len(morceaux) < 2:
        return "Ce n'est pas un jeton JWT : il faut trois parties séparées par des points."
    out = []
    for nom, m in (("En-tête", morceaux[0]), ("Contenu", morceaux[1])):
        try:
            d = json.loads(base64.urlsafe_b64decode(m + "=" * (-len(m) % 4)))
            out.append(f"{nom} : {json.dumps(d, ensure_ascii=False, indent=2)}")
            if nom == "Contenu" and "exp" in d:
                exp = datetime.fromtimestamp(d["exp"])
                out.append(f"Expiration : {exp:%d/%m/%Y %H:%M} ({'EXPIRÉ' if exp < datetime.now() else 'valide'})")
        except Exception:  # noqa: BLE001
            out.append(f"{nom} : illisible")
    return "\n".join(out)


def format_json(text: str) -> str:
    """Vérifie et met en forme du JSON, en indiquant précisément où se trouve l'erreur s'il y en a une.

    Args:
        text: Le JSON à vérifier, ou le chemin d'un fichier JSON.
    """
    contenu = text
    if len(text) < 300 and not text.strip().startswith(("{", "[")):
        p = _p(text)
        if p.is_file():
            contenu = p.read_text(encoding="utf-8", errors="ignore")
    try:
        d = json.loads(contenu)
    except json.JSONDecodeError as exc:
        return f"JSON invalide : {exc.msg}, ligne {exc.lineno}, colonne {exc.colno}."
    joli = json.dumps(d, ensure_ascii=False, indent=2)
    return f"JSON valide, {len(joli)} caractères :\n{joli[:2500]}"


def test_regex(pattern: str, text: str) -> str:
    """Teste une expression régulière sur un texte et montre tout ce qu'elle capture.

    Args:
        pattern: L'expression régulière.
        text: Le texte sur lequel l'essayer.
    """
    try:
        r = re.compile(pattern)
    except re.error as exc:
        return f"Expression invalide : {exc}"
    trouves = list(r.finditer(text))
    if not trouves:
        return f"Aucune correspondance de « {pattern} » dans ce texte."
    lignes = [f"{i}. « {m.group(0)[:80]} » position {m.start()}"
              + (f" groupes {m.groups()}" if m.groups() else "") for i, m in enumerate(trouves[:20], 1)]
    return f"{len(trouves)} correspondance(s) :\n" + "\n".join(lignes)


def convert_value(value: str, kind: str = "auto") -> str:
    """Convertit une valeur : horodatage en date, couleur hexadécimale en RVB, octets en Mo, et l'inverse.

    Args:
        value: La valeur à convertir.
        kind: "timestamp", "couleur", "octets", ou "auto" pour deviner.
    """
    from datetime import datetime

    v = value.strip()
    k = kind.lower()
    try:
        if k in ("auto", "couleur") and re.fullmatch(r"#?[0-9a-fA-F]{6}", v):
            h = v.lstrip("#")
            r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
            return f"#{h.upper()} = rgb({r}, {g}, {b})"
        if k in ("auto", "timestamp") and re.fullmatch(r"\d{9,13}", v):
            n = int(v)
            n = n / 1000 if n > 10**11 else n
            return f"{v} = {datetime.fromtimestamp(n):%d/%m/%Y %H:%M:%S}"
        if k in ("auto", "octets") and re.fullmatch(r"\d+", v):
            n = int(v)
            return f"{n} octets = {n / 1024:.1f} Ko = {n / 2**20:.2f} Mo = {n / 2**30:.3f} Go"
        if re.fullmatch(r"rgb\(\s*\d+\s*,\s*\d+\s*,\s*\d+\s*\)", v, re.I):
            r, g, b = (int(x) for x in re.findall(r"\d+", v))
            return f"{v} = #{r:02X}{g:02X}{b:02X}"
        return f"Je ne sais pas convertir « {v} ». Précise le type : timestamp, couleur ou octets."
    except Exception as exc:  # noqa: BLE001
        return f"Erreur : {exc}"


def security_headers(url: str) -> str:
    """Vérifie les en-têtes de sécurité d'un site web et dit lesquels manquent.

    Args:
        url: L'adresse du site.
    """
    try:
        import requests

        if not url.startswith("http"):
            url = "https://" + url
        r = requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0 (agent local)"})
        attendus = {
            "Strict-Transport-Security": "force le HTTPS",
            "Content-Security-Policy": "bloque les scripts non autorisés",
            "X-Frame-Options": "empêche l'affichage dans une iframe",
            "X-Content-Type-Options": "empêche la devinette de type",
            "Referrer-Policy": "limite les informations envoyées aux autres sites",
            "Permissions-Policy": "limite l'accès à la caméra et au micro",
        }
        presents = [f"OK      {k}" for k in attendus if k in r.headers]
        manquants = [f"MANQUE  {k} : {d}" for k, d in attendus.items() if k not in r.headers]
        return (f"En-têtes de sécurité de {url}, {len(presents)} sur {len(attendus)} :\n"
                + "\n".join(presents + manquants))
    except Exception as exc:  # noqa: BLE001
        return f"Erreur : {exc}"


def broken_links(url: str, max_links: int = 40) -> str:
    """Parcourt une page web et signale tous les liens qui ne fonctionnent plus.

    Args:
        url: L'adresse de la page à vérifier.
        max_links: Nombre de liens à tester au maximum.
    """
    try:
        from concurrent.futures import ThreadPoolExecutor
        from urllib.parse import urljoin

        import requests
        from bs4 import BeautifulSoup

        if not url.startswith("http"):
            url = "https://" + url
        ua = {"User-Agent": "Mozilla/5.0 (agent local)"}
        r = requests.get(url, timeout=20, headers=ua)
        soup = BeautifulSoup(r.text, "html.parser")
        liens = []
        for a in soup.find_all("a", href=True):
            lien = urljoin(url, a["href"])
            if lien.startswith("http") and lien not in liens:
                liens.append(lien)
        liens = liens[:max(1, int(max_links))]

        def teste(l):
            try:
                rep = requests.head(l, timeout=10, allow_redirects=True, headers=ua)
                if rep.status_code >= 400:
                    rep = requests.get(l, timeout=10, headers=ua)
                return l, rep.status_code
            except Exception:  # noqa: BLE001
                return l, 0

        with ThreadPoolExecutor(max_workers=10) as pool:
            res = list(pool.map(teste, liens))
        casses = [f"{code if code else 'injoignable'} : {l}" for l, code in res if code == 0 or code >= 400]
        if not casses:
            return f"Les {len(liens)} liens de {url} fonctionnent."
        return f"{len(casses)} lien(s) cassés sur {len(liens)} testés :\n" + "\n".join(casses[:25])
    except Exception as exc:  # noqa: BLE001
        return f"Erreur : {exc}"


def accessibility_check(url_or_file: str) -> str:
    """Vérifie l'accessibilité d'une page : images sans description, langue, titres, champs sans étiquette.

    Args:
        url_or_file: Adresse d'une page web ou chemin d'un fichier HTML.
    """
    try:
        from bs4 import BeautifulSoup

        cible = url_or_file.strip()
        if cible.startswith("http"):
            import requests
            html = requests.get(cible, timeout=20, headers={"User-Agent": "Mozilla/5.0 (agent local)"}).text
        else:
            p = _p(cible)
            if not p.is_file():
                return f"Introuvable : {p}"
            html = p.read_text(encoding="utf-8", errors="ignore")
        soup = BeautifulSoup(html, "html.parser")
        pbs = []
        imgs = soup.find_all("img")
        sans_alt = [i for i in imgs if not i.get("alt")]
        if sans_alt:
            pbs.append(f"{len(sans_alt)} image(s) sur {len(imgs)} sans description alt")
        if not (soup.html and soup.html.get("lang")):
            pbs.append("la langue de la page n'est pas déclarée, attribut lang manquant")
        h1 = soup.find_all("h1")
        if not h1:
            pbs.append("aucun titre principal h1")
        elif len(h1) > 1:
            pbs.append(f"{len(h1)} titres h1, il n'en faut qu'un")
        sans_label = [c for c in soup.find_all("input") if not c.get("aria-label") and not c.get("id")]
        if sans_label:
            pbs.append(f"{len(sans_label)} champ(s) de formulaire sans étiquette")
        boutons = [b for b in soup.find_all("button") if not b.get_text(strip=True) and not b.get("aria-label")]
        if boutons:
            pbs.append(f"{len(boutons)} bouton(s) sans texte ni description")
        if not soup.find("title"):
            pbs.append("la page n'a pas de titre")
        if not pbs:
            return f"Accessibilité de base correcte pour {cible}."
        return f"{len(pbs)} problème(s) d'accessibilité sur {cible} :\n- " + "\n- ".join(pbs)
    except Exception as exc:  # noqa: BLE001
        return f"Erreur : {exc}"


def generate_sitemap(folder: str, base_url: str = "https://exemple.fr") -> str:
    """Crée le fichier sitemap.xml et le robots.txt d'un site à partir de ses pages HTML.

    Args:
        folder: Dossier du site.
        base_url: Adresse du site une fois en ligne.
    """
    d = _p(folder)
    if not d.is_dir():
        return f"Dossier introuvable : {d}"
    pages = sorted(f for f in d.rglob("*.html") if "node_modules" not in str(f))
    if not pages:
        return f"Aucune page HTML dans {d}."
    base = base_url.rstrip("/")
    urls = []
    for f in pages:
        rel = f.relative_to(d).as_posix()
        rel = "" if rel == "index.html" else rel
        urls.append(f"  <url><loc>{base}/{rel}</loc></url>")
    xml = ('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
           + "\n".join(urls) + "\n</urlset>\n")
    (d / "sitemap.xml").write_text(xml, encoding="utf-8")
    (d / "robots.txt").write_text(f"User-agent: *\nAllow: /\nSitemap: {base}/sitemap.xml\n", encoding="utf-8")
    return f"sitemap.xml créé avec {len(urls)} page(s), et robots.txt, dans {d}"


def lighthouse_audit(url: str) -> str:
    """Note la performance, l'accessibilité et le référencement d'une page web.

    Args:
        url: L'adresse de la page.
    """
    if not url.startswith("http"):
        url = "https://" + url
    if not shutil.which("npx"):
        return ("Node.js n'est pas installé, l'audit complet est impossible. "
                "Je peux quand même faire accessibility_check et security_headers sur cette page.")
    sortie = config.WORKSPACE / "lighthouse.json"
    out = _run(["npx", "--yes", "lighthouse", url, "--quiet", "--chrome-flags=--headless",
                "--output=json", f"--output-path={sortie}"], timeout=300)
    if sortie.is_file():
        try:
            d = json.loads(sortie.read_text(encoding="utf-8"))
            notes = [f"{c.get('title', k)} : {round((c.get('score') or 0) * 100)} sur 100"
                     for k, c in d.get("categories", {}).items()]
            return f"Audit de {url} :\n" + "\n".join(notes)
        except Exception:  # noqa: BLE001
            pass
    return f"Audit impossible :\n{out[:800]}"


def mock_api(port: int = 8900, routes: str = "/api/test") -> str:
    """Démarre une fausse API locale qui répond du JSON, pour développer une interface sans le vrai serveur.

    Args:
        port: Le port d'écoute.
        routes: Les chemins à servir, séparés par des points-virgules.
    """
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer

    chemins = [r.strip() for r in routes.split(";") if r.strip()]

    class H(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            self.send_response(200 if self.path in chemins else 404)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({"ok": True, "chemin": self.path,
                                         "donnees": [{"id": 1, "nom": "exemple"}]}).encode())

        do_POST = do_GET  # noqa: N815

        def log_message(self, *a):
            return

    try:
        srv = HTTPServer(("127.0.0.1", int(port)), H)
    except OSError as exc:
        return f"Impossible d'écouter sur le port {port} : {exc}"
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return (f"Fausse API démarrée sur http://127.0.0.1:{port}, chemins : {', '.join(chemins)}. "
            "Elle répond du JSON d'exemple et s'arrête avec Jarvis.")


TOOLS = [lint_code, format_code, run_tests, test_coverage, dead_code, type_check, audit_deps, check_licenses,
         update_deps, bundle_size, profile_code, read_logs,
         test_api, decode_jwt, format_json, test_regex, convert_value, security_headers, broken_links,
         accessibility_check, generate_sitemap, lighthouse_audit, mock_api]
