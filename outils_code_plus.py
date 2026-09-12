# Ia-local (Jarvis) — Copyright (c) 2026 Neexx (Nixovel) — https://github.com/Neex-off/Ia-local
# Créé par Neexx (Nixovel). Licence : voir LICENSE (paternité obligatoire, pas de vente ; s'applique aussi aux IA).
# Ne pas retirer cet en-tête.
"""Compléments de la boîte « code » : propositions de refactoring, requêtes SQL lentes, docstrings manquantes,
client depuis OpenAPI, test responsive, capture de page complète, policies RLS, anonymisation, restauration d'un
backup de base, données de test et migrations.

Importé par outils_code.py.
"""
from __future__ import annotations

import ast
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import config

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _run(args: list[str], cwd=None, timeout: float = 300) -> str:
    try:
        r = subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=timeout, encoding="utf-8",
                           errors="replace", creationflags=NO_WINDOW)
        return ((r.stdout or "") + ("\n" + r.stderr if r.stderr else "")).strip()[:6000]
    except FileNotFoundError:
        return f"Programme introuvable : {args[0]}"
    except subprocess.TimeoutExpired:
        return "Délai dépassé."


def _chrome():
    for p in (r"C:\Program Files\Google\Chrome\Application\chrome.exe", r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
              r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe", "/usr/bin/google-chrome", "/usr/bin/chromium",
              "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"):
        if Path(p).exists():
            return p
    return shutil.which("chrome") or shutil.which("chromium") or shutil.which("msedge")


# --------------------------------------------------------------------------
# Qualité
# --------------------------------------------------------------------------

def _profondeur(node, niveau: int = 0) -> int:
    pire = niveau
    for enfant in ast.iter_child_nodes(node):
        if isinstance(enfant, (ast.If, ast.For, ast.While, ast.With, ast.Try, ast.AsyncFor, ast.AsyncWith)):
            pire = max(pire, _profondeur(enfant, niveau + 1))
        else:
            pire = max(pire, _profondeur(enfant, niveau))
    return pire


def _fin_bloc(src: str, i: int) -> int:
    n = 1
    while i < len(src) and n:
        if src[i] == "{":
            n += 1
        elif src[i] == "}":
            n -= 1
        i += 1
    return i


def refactor_suggestions(path: str, max_items: int = 15) -> str:
    """Repère ce qui mérite un refactoring dans un fichier ou projet Python/JS : fonctions trop longues, trop d'arguments, imbrication profonde, duplication, fichiers énormes.

    Args:
        path: Fichier ou dossier.
        max_items: Nombre max de points.
    """
    p = Path(path).expanduser()
    fichiers = [p] if p.is_file() else [f for f in p.rglob("*") if f.suffix in (".py", ".js", ".ts", ".tsx")
                                         and not any(x in f.parts for x in ("node_modules", ".venv", "dist", "build"))]
    points = []
    blocs: dict[str, list[str]] = {}
    for f in fichiers[:400]:
        try:
            src = f.read_text(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            continue
        lignes = src.splitlines()
        if len(lignes) > 800:
            points.append((3, f"{f.name} : {len(lignes)} lignes, à découper en modules"))
        if f.suffix == ".py":
            try:
                arbre = ast.parse(src)
            except SyntaxError:
                continue
            for node in ast.walk(arbre):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    taille = (node.end_lineno or node.lineno) - node.lineno
                    if taille > 60:
                        points.append((2, f"{f.name}:{node.lineno} {node.name}() fait {taille} lignes : extraire des sous-fonctions"))
                    nargs = len(node.args.args) + len(node.args.kwonlyargs)
                    if nargs > 6:
                        points.append((1, f"{f.name}:{node.lineno} {node.name}() a {nargs} paramètres : regrouper dans un objet"))
                    prof = _profondeur(node)
                    if prof > 4:
                        points.append((2, f"{f.name}:{node.lineno} {node.name}() imbriqué sur {prof} niveaux : retours anticipés / découpage"))
        else:
            for m in re.finditer(r"(?:function\s+(\w+)|(\w+)\s*=\s*(?:async\s*)?\([^)]*\)\s*=>)\s*\{", src):
                debut = src.count("\n", 0, m.start())
                nom = m.group(1) or m.group(2)
                taille = src.count("\n", m.start(), _fin_bloc(src, m.end()))
                if taille > 60:
                    points.append((2, f"{f.name}:{debut + 1} {nom}() fait {taille} lignes"))
        for i in range(0, len(lignes) - 6):
            bloc = "\n".join(l.strip() for l in lignes[i:i + 6])
            if len(bloc) > 120 and not bloc.startswith(("import", "from", "#", "//")):
                blocs.setdefault(bloc, []).append(f"{f.name}:{i + 1}")
    points += [(1, f"Bloc dupliqué ({len(v)}×) : {', '.join(v[:4])}") for v in blocs.values() if len(v) > 1][:5]
    points.sort(key=lambda x: -x[0])
    if not points:
        return "Rien de flagrant : fonctions courtes, peu d'imbrication, pas de duplication évidente."
    return ("Refactorings proposés (par priorité) :\n" + "\n".join(f"- {t}" for _, t in points[:max_items])
            + "\nPropose à l'utilisateur lequel faire, puis fais-le avec write_file.")


def _connect(dsn: str):
    dsn = dsn or getattr(config, "DB_DSN", "")
    if not dsn:
        raise ValueError("Donne une chaîne de connexion postgresql:// (ou DB_DSN dans config.py).")
    try:
        import psycopg

        return psycopg.connect(dsn)
    except ImportError:
        import psycopg2

        return psycopg2.connect(dsn)


def slow_queries(dsn: str = "", query: str = "", min_ms: float = 100) -> str:
    """Requêtes SQL lentes : statistiques pg_stat_statements d'une base PostgreSQL, ou EXPLAIN ANALYZE d'une requête donnée.

    Args:
        dsn: Chaîne de connexion (postgresql://user:mdp@hote/base) ; vide = config.DB_DSN.
        query: Une requête à expliquer (vide = top des requêtes lentes).
        min_ms: Seuil de temps moyen en ms.
    """
    try:
        with _connect(dsn) as conn, conn.cursor() as cur:
            if query:
                cur.execute("EXPLAIN (ANALYZE, BUFFERS) " + query)
                plan = "\n".join(r[0] for r in cur.fetchall())
                return plan[:3000] + ("\n\nUn Seq Scan apparaît : un index sur la colonne filtrée accélérerait probablement la requête." if "Seq Scan" in plan else "")
            cur.execute("SELECT calls, round(mean_exec_time::numeric,1), round(total_exec_time::numeric), left(query,140) "
                        "FROM pg_stat_statements WHERE mean_exec_time > %s ORDER BY total_exec_time DESC LIMIT 15", (min_ms,))
            rows = cur.fetchall()
    except ImportError:
        return "Il faut le paquet psycopg (pip install psycopg[binary])."
    except Exception as exc:  # noqa: BLE001
        msg = str(exc)
        if "pg_stat_statements" in msg:
            return "L'extension pg_stat_statements n'est pas activée : CREATE EXTENSION pg_stat_statements; (et shared_preload_libraries)."
        return f"Erreur : {msg[:300]}"
    if not rows:
        return f"Aucune requête au-dessus de {min_ms} ms en moyenne."
    return "\n".join(f"- {r[0]} appels, {r[1]} ms/appel, {r[2]} ms total : {r[3]}" for r in rows)


def missing_docstrings(path: str, max_items: int = 40) -> str:
    """Liste les fonctions, classes et méthodes Python sans docstring (avec leur signature) pour que tu les rédiges.

    Args:
        path: Fichier ou dossier Python.
        max_items: Nombre max.
    """
    p = Path(path).expanduser()
    fichiers = [p] if p.is_file() else [f for f in p.rglob("*.py") if ".venv" not in f.parts]
    out = []
    for f in fichiers[:300]:
        try:
            arbre = ast.parse(f.read_text(encoding="utf-8", errors="replace"))
        except Exception:  # noqa: BLE001
            continue
        for node in ast.walk(arbre):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and not ast.get_docstring(node) and not node.name.startswith("_"):
                sig = node.name + (f"({', '.join(a.arg for a in node.args.args)})" if not isinstance(node, ast.ClassDef) else "")
                out.append(f"{f.name}:{node.lineno} {sig}")
    if not out:
        return "Tout est documenté."
    return (f"{len(out)} sans docstring :\n" + "\n".join(out[:max_items])
            + "\nRédige une docstring d'une ligne (+ Args si utile) pour chacune et insère-la avec write_file.")


# --------------------------------------------------------------------------
# API et web
# --------------------------------------------------------------------------

def openapi_client(spec_url: str, output: str = "", language: str = "python") -> str:
    """Génère un client API depuis une spec OpenAPI (URL ou fichier) : openapi-python-client si présent, sinon un client requests simple.

    Args:
        spec_url: URL ou chemin du openapi.json / .yaml.
        output: Dossier ou fichier de sortie (vide = workspace/client_api.py).
        language: "python" (ou "typescript" via openapi-typescript).
    """
    if language == "typescript":
        out = output or str(config.WORKSPACE / "api.d.ts")
        return _run(["npx.cmd" if sys.platform.startswith("win") else "npx", "-y", "openapi-typescript", spec_url, "-o", out], timeout=600) + f"\nTypes écrits dans {out}"
    if shutil.which("openapi-python-client"):
        out = output or str(config.WORKSPACE / "client_api")
        return _run(["openapi-python-client", "generate", "--url" if spec_url.startswith("http") else "--path", spec_url, "--output-path", out, "--overwrite"], timeout=600)
    import requests
    import yaml

    try:
        texte = requests.get(spec_url, timeout=30).text if spec_url.startswith("http") else Path(spec_url).read_text(encoding="utf-8")
        spec = json.loads(texte) if texte.lstrip().startswith("{") else yaml.safe_load(texte)
    except Exception as exc:  # noqa: BLE001
        return f"Spec illisible : {exc}"
    base = (spec.get("servers") or [{"url": ""}])[0].get("url", "")
    lignes = ["import requests", "", f'BASE_URL = "{base}"', "", "", "class Client:",
              "    def __init__(self, base_url: str = BASE_URL, token: str = ''):",
              "        self.base, self.s = base_url.rstrip('/'), requests.Session()",
              "        if token:", "            self.s.headers['Authorization'] = f'Bearer {token}'", ""]
    n = 0
    for chemin, ops in (spec.get("paths") or {}).items():
        for methode, op in ops.items():
            if methode.lower() not in ("get", "post", "put", "patch", "delete") or not isinstance(op, dict):
                continue
            nom = re.sub(r"\W+", "_", op.get("operationId") or f"{methode}_{chemin}").strip("_").lower()
            params = [pr["name"] for pr in op.get("parameters", []) if pr.get("in") == "path"]
            args = ", ".join(params + ["params=None", "json=None"])
            lignes += [f"    def {nom}(self, {args}):", f'        """{(op.get("summary") or "").strip()}"""',
                       f"        r = self.s.{methode.lower()}(f'{{self.base}}{chemin}', params=params, json=json)",
                       "        r.raise_for_status()", "        return r.json() if r.content else None", ""]
            n += 1
    out = Path(output) if output else config.WORKSPACE / "client_api.py"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lignes), encoding="utf-8")
    return f"Client Python généré : {out} ({n} méthodes)."


def responsive_test(url: str, sizes: str = "375x812,768x1024,1440x900") -> str:
    """Capture une page à plusieurs tailles d'écran (mobile, tablette, desktop) avec Chrome headless, pour vérifier le responsive.

    Args:
        url: Adresse de la page.
        sizes: Tailles "largeurxhauteur" séparées par des virgules.
    """
    chrome = _chrome()
    if not chrome:
        return "Chrome ou Edge introuvable."
    fichiers = []
    for t in sizes.split(","):
        w, h = t.strip().split("x")
        f = config.WORKSPACE / f"responsive-{w}x{h}.png"
        f.parent.mkdir(parents=True, exist_ok=True)
        _run([chrome, "--headless=new", "--disable-gpu", "--hide-scrollbars", f"--window-size={w},{h}", f"--screenshot={f}", url], timeout=90)
        if f.exists():
            fichiers.append(f)
    if not fichiers:
        return "Aucune capture produite."
    return (f"[[image:{fichiers[0]}]]\nCaptures : {', '.join(str(f) for f in fichiers)}\n"
            "Regarde chaque image (open_file) et signale débordements, textes coupés, boutons trop petits.")


def full_page_capture(url: str, width: int = 1440, output: str = "") -> str:
    """Capture d'une page web entière (toute la hauteur) en image.

    Args:
        url: Adresse de la page.
        width: Largeur de fenêtre.
        output: Fichier PNG (vide = workspace/page-complete.png).
    """
    chrome = _chrome()
    if not chrome:
        return "Chrome ou Edge introuvable."
    out = Path(output) if output else config.WORKSPACE / "page-complete.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    _run([chrome, "--headless=new", "--disable-gpu", "--hide-scrollbars", f"--window-size={width},8000", f"--screenshot={out}", url], timeout=120)
    if not out.exists():
        return "Capture échouée."
    try:
        from PIL import Image

        img = Image.open(out)
        px = img.convert("L").load()
        bas = img.height
        for y in range(img.height - 1, 0, -40):
            if any(px[x, y] < 250 for x in range(0, img.width, 20)):
                bas = min(img.height, y + 60)
                break
        img.crop((0, 0, img.width, bas)).save(out)
    except Exception:  # noqa: BLE001
        pass
    return f"[[image:{out}]]\nPage complète capturée : {out}"


# --------------------------------------------------------------------------
# Base de données
# --------------------------------------------------------------------------

def check_rls(dsn: str = "", schema: str = "public") -> str:
    """Vérifie les policies de sécurité (RLS) d'une base PostgreSQL/Supabase : tables sans RLS, tables avec RLS mais sans policy.

    Args:
        dsn: Chaîne de connexion (vide = config.DB_DSN).
        schema: Schéma à vérifier.
    """
    try:
        with _connect(dsn) as conn, conn.cursor() as cur:
            cur.execute("SELECT c.relname, c.relrowsecurity, (SELECT count(*) FROM pg_policies p WHERE p.tablename=c.relname AND p.schemaname=%s) "
                        "FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname=%s AND c.relkind='r' ORDER BY 1", (schema, schema))
            rows = cur.fetchall()
    except ImportError:
        return "Il faut le paquet psycopg (pip install psycopg[binary])."
    except Exception as exc:  # noqa: BLE001
        return f"Erreur : {str(exc)[:300]}"
    sans, vides, ok = [], [], []
    for nom, rls, npol in rows:
        (ok if rls and npol else vides if rls else sans).append(nom)
    return (f"Tables sans RLS (tout le monde lit tout via l'API) : {', '.join(sans) or 'aucune'}\n"
            f"RLS activée mais AUCUNE policy (personne ne peut lire) : {', '.join(vides) or 'aucune'}\n"
            f"Protégées : {', '.join(ok) or 'aucune'}")


def anonymize_data(input_path: str, output_path: str = "", columns: str = "") -> str:
    """Anonymise un CSV ou JSON pour les tests : noms, e-mails, téléphones, adresses, IBAN remplacés par des valeurs fictives cohérentes.

    Args:
        input_path: Fichier CSV ou JSON.
        output_path: Fichier de sortie (vide = -anonyme).
        columns: Colonnes à anonymiser en plus de la détection automatique, séparées par des virgules.
    """
    import csv
    import hashlib
    import random

    p = Path(input_path).expanduser()
    if not p.exists():
        return f"Introuvable : {p}"
    forces = {c.strip().lower() for c in columns.split(",") if c.strip()}
    prenoms = ["Alice", "Bruno", "Chloé", "David", "Emma", "Farid", "Gaëlle", "Hugo", "Inès", "Jules", "Karim", "Léa", "Marc", "Nora", "Omar", "Pauline"]
    noms = ["Martin", "Bernard", "Dubois", "Thomas", "Robert", "Richard", "Petit", "Durand", "Leroy", "Moreau", "Simon", "Laurent"]
    sensibles = ("nom", "name", "prenom", "first", "last", "mail", "tel", "phone", "adresse", "address", "iban", "naissance", "birth", "ssn", "secu", "passport")

    def faux(cle: str, valeur: str) -> str:
        if not valeur:
            return valeur
        g = random.Random(hashlib.md5((cle + valeur).encode()).hexdigest())
        k = cle.lower()
        if "mail" in k or "@" in valeur:
            return f"user{g.randint(1000, 9999)}@exemple.test"
        if "tel" in k or "phone" in k or re.fullmatch(r"[+\d][\d .-]{8,}", valeur):
            return "06" + "".join(str(g.randint(0, 9)) for _ in range(8))
        if "iban" in k:
            return "FR76" + "".join(str(g.randint(0, 9)) for _ in range(23))
        if "adresse" in k or "address" in k or "rue" in k:
            return f"{g.randint(1, 120)} rue des Tests, {g.randint(10000, 95000)} Ville"
        if "prenom" in k or "first" in k:
            return g.choice(prenoms)
        if "nom" in k or "name" in k or "last" in k:
            return g.choice(noms)
        if "naissance" in k or "birth" in k:
            return f"{g.randint(1960, 2005)}-{g.randint(1, 12):02d}-{g.randint(1, 28):02d}"
        return f"anon-{hashlib.md5(valeur.encode()).hexdigest()[:8]}"

    def sensible(k: str) -> bool:
        return k.lower() in forces or any(s in k.lower() for s in sensibles)

    n = 0
    out = Path(output_path) if output_path else p.with_name(p.stem + "-anonyme" + p.suffix)
    if p.suffix.lower() == ".csv":
        with p.open(encoding="utf-8", newline="") as f:
            rows = list(csv.DictReader(f))
        cols = [c for c in (rows[0].keys() if rows else []) if sensible(c)]
        for r in rows:
            for c in cols:
                r[c] = faux(c, r[c])
                n += 1
        with out.open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()) if rows else [])
            w.writeheader()
            w.writerows(rows)
    else:
        data = json.loads(p.read_text(encoding="utf-8"))

        def marcher(o):
            nonlocal n
            if isinstance(o, dict):
                for k, v in o.items():
                    if isinstance(v, str) and sensible(k):
                        o[k] = faux(k, v)
                        n += 1
                    else:
                        marcher(v)
            elif isinstance(o, list):
                for x in o:
                    marcher(x)

        marcher(data)
        out.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return f"{n} valeurs anonymisées -> {out}"


def restore_backup(dsn: str, backup_path: str, clean: bool = False) -> str:
    """Restaure un backup PostgreSQL (.sql via psql, .dump/.backup via pg_restore) dans une base.

    Args:
        dsn: Chaîne de connexion de la base cible.
        backup_path: Fichier de sauvegarde.
        clean: Supprimer les objets existants avant (pg_restore --clean).
    """
    b = Path(backup_path).expanduser()
    if not b.exists():
        return f"Introuvable : {b}"
    if b.suffix.lower() == ".sql":
        if not shutil.which("psql"):
            return "psql introuvable : installe les outils PostgreSQL."
        return _run(["psql", dsn, "-v", "ON_ERROR_STOP=1", "-f", str(b)], timeout=3600)[-2000:] or "Restauration terminée."
    if not shutil.which("pg_restore"):
        return "pg_restore introuvable : installe les outils PostgreSQL."
    args = ["pg_restore", "--no-owner", "--dbname", dsn] + (["--clean", "--if-exists"] if clean else []) + [str(b)]
    return _run(args, timeout=3600)[-2000:] or "Restauration terminée."


def generate_test_data(dsn: str = "", table: str = "", rows: int = 20, migration_name: str = "") -> str:
    """Génère des données de test (INSERT) d'après le schéma d'une table, ou un squelette de migration SQL horodaté.

    Args:
        dsn: Chaîne de connexion (vide = config.DB_DSN).
        table: Table cible (vide avec migration_name = juste le squelette).
        rows: Nombre de lignes.
        migration_name: Si donné, écrit workspace/migrations/AAAAMMJJHHMM_nom.sql avec up/down.
    """
    import random

    out = []
    if migration_name:
        d = config.WORKSPACE / "migrations"
        d.mkdir(parents=True, exist_ok=True)
        slug = re.sub(r"\W+", "_", migration_name).lower()
        f = d / f"{datetime.now():%Y%m%d%H%M}_{slug}.sql"
        f.write_text(f"-- Migration : {migration_name}\n-- +migrate Up\nBEGIN;\n\n-- TODO\n\nCOMMIT;\n\n-- +migrate Down\nBEGIN;\n\n-- TODO\n\nCOMMIT;\n", encoding="utf-8")
        out.append(f"Migration créée : {f}")
    if table:
        try:
            with _connect(dsn) as conn, conn.cursor() as cur:
                cur.execute("SELECT column_name, data_type, column_default FROM information_schema.columns WHERE table_name=%s ORDER BY ordinal_position", (table,))
                cols = cur.fetchall()
        except Exception as exc:  # noqa: BLE001
            return "\n".join(out + [f"Erreur : {str(exc)[:300]}"])
        cols = [c for c in cols if not (c[2] or "").startswith(("nextval", "gen_random"))]
        g = random.Random(42)
        lignes = []
        for i in range(int(rows)):
            vals = []
            for nom, typ, _d in cols:
                t, k = typ.lower(), nom.lower()
                if "int" in t or "numeric" in t or "double" in t or "real" in t:
                    vals.append(str(g.randint(1, 1000)))
                elif "bool" in t:
                    vals.append(g.choice(["true", "false"]))
                elif "timestamp" in t or "date" in t:
                    vals.append(f"'2026-{g.randint(1, 12):02d}-{g.randint(1, 28):02d}'")
                elif "uuid" in t:
                    vals.append("gen_random_uuid()")
                elif "json" in t:
                    vals.append("'{}'")
                elif "mail" in k:
                    vals.append(f"'user{i}@exemple.test'")
                elif "nom" in k or "name" in k:
                    vals.append(f"'Test {i}'")
                else:
                    vals.append(f"'valeur {i}'")
            lignes.append(f"({', '.join(vals)})")
        sql = f"INSERT INTO {table} ({', '.join(c[0] for c in cols)}) VALUES\n" + ",\n".join(lignes) + ";\n"
        f = config.WORKSPACE / f"seed_{table}.sql"
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(sql, encoding="utf-8")
        out.append(f"{rows} lignes de test écrites dans {f} (db_write pour les insérer) :\n{sql[:800]}")
    return "\n".join(out) or "Donne une table ou un nom de migration."


TOOLS = [refactor_suggestions, slow_queries, missing_docstrings, openapi_client, responsive_test, full_page_capture,
         check_rls, anonymize_data, restore_backup, generate_test_data]
