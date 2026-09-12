# Ia-local (Jarvis) — Copyright (c) 2026 Neexx (Nixovel) — https://github.com/Neex-off/Ia-local
# Créé par Neexx (Nixovel). Licence : voir LICENSE (paternité obligatoire, pas de vente ; s'applique aussi aux IA).
# Ne pas retirer cet en-tête.
"""Boîte à outils « ia » : modèles locaux, comparaison, transcription, images, base de connaissances.

Chargée à la demande par tools.open_toolbox("ia").
Catalogue : module IA & modèles, et une partie de Multi-agents & tâches de fond.
"""
from __future__ import annotations

import json
import math
import re
import shutil
import subprocess
import time
import unicodedata
from pathlib import Path

import config

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
INDEX = config.ROOT / "memoire" / "index_documents.json"
DOCS = {".txt", ".md", ".py", ".js", ".ts", ".json", ".csv", ".html", ".yml", ".yaml", ".ini"}


def _p(chemin: str) -> Path:
    brut = str(chemin).strip('" ')
    p = Path(brut).expanduser()
    if p.is_absolute():
        return p
    if brut in (".", "./", ".\\"):
        return config.ROOT
    for base in (config.ROOT, config.WORKSPACE, Path.cwd(), Path.home() / "Documents", Path.home() / "Desktop"):
        if (base / p).exists():
            return base / p
    return config.WORKSPACE / p


def _run(args: list[str], timeout: float = 120) -> str:
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=timeout, encoding="utf-8",
                           errors="replace", creationflags=NO_WINDOW)
        return ((r.stdout or "").strip() or (r.stderr or "").strip())[:3000]
    except FileNotFoundError:
        return f"Erreur : « {args[0]} » n'est pas installé."
    except Exception as exc:  # noqa: BLE001
        return f"Erreur : {exc}"


def _mots(texte: str) -> list[str]:
    t = unicodedata.normalize("NFKD", texte.lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.findall(r"[a-z0-9]{3,}", t)


# --------------------------------------------------------------------------
# Modèles locaux
# --------------------------------------------------------------------------

def compare_models(question: str, models: str = "") -> str:
    """Pose la même question à plusieurs modèles et compare leurs réponses et leur vitesse.

    Args:
        question: La question à poser.
        models: Les modèles séparés par des virgules. Vide = les profils du catalogue qui sont installés.
    """
    try:
        import ollama

        if models.strip():
            noms = [m.strip() for m in models.split(",") if m.strip()]
        else:
            installes = [m.model for m in ollama.list().models]
            noms = [config.MODELS[t]["name"] for t in config.MODEL_ORDER
                    if any(config.MODELS[t]["name"] in i for i in installes)][:3]
        if not noms:
            return "Aucun modèle à comparer."
        out = []
        for nom in noms:
            t0 = time.time()
            try:
                r = ollama.chat(model=nom, messages=[{"role": "user", "content": question}], think=False,
                                options={"num_ctx": 4096, "num_predict": 220}, keep_alive="2m")
                dt = time.time() - t0
                vit = (r.eval_count or 0) / max(0.1, (r.eval_duration or 1) / 1e9)
                out.append(f"=== {nom}, {dt:.1f} s, {vit:.0f} mots-machine par seconde ===\n"
                           f"{(r.message.content or '').strip()[:700]}")
            except Exception as exc:  # noqa: BLE001
                out.append(f"=== {nom}, échec : {exc} ===")
            finally:
                try:
                    ollama.generate(model=nom, prompt="", keep_alive=0)
                except Exception:  # noqa: BLE001
                    pass
        return "\n\n".join(out)
    except Exception as exc:  # noqa: BLE001
        return f"Erreur : {exc}"


def benchmark_model(model: str = "") -> str:
    """Mesure la vitesse d'un modèle : temps de chargement et nombre de mots produits par seconde.

    Args:
        model: Nom du modèle. Vide = le modèle actuellement utilisé.
    """
    try:
        import ollama
        import tools as _t

        nom = model.strip() or getattr(_t, "CURRENT_MODEL", config.MODEL)
        ollama.generate(model=nom, prompt="", keep_alive=0)
        time.sleep(1)
        t0 = time.time()
        r = ollama.chat(model=nom, think=False, keep_alive="2m",
                        messages=[{"role": "user", "content": "Explique en cinq phrases ce qu'est un ordinateur."}],
                        options={"num_ctx": 4096, "num_predict": 300})
        total = time.time() - t0
        vit = (r.eval_count or 0) / max(0.1, (r.eval_duration or 1) / 1e9)
        return (f"{nom} : {total:.1f} s au total, {(r.load_duration or 0) / 1e9:.1f} s de chargement, "
                f"{r.eval_count} mots-machine à {vit:.0f} par seconde, prompt de {r.prompt_eval_count} jetons.")
    except Exception as exc:  # noqa: BLE001
        return f"Erreur : {exc}"


def recommend_model() -> str:
    """Conseille le modèle à utiliser d'après la mémoire libre de la carte graphique."""
    try:
        libre_go = None
        if shutil.which("nvidia-smi"):
            out = _run(["nvidia-smi", "--query-gpu=memory.used,memory.total", "--format=csv,noheader,nounits"], 15)
            used, total = (int(x) for x in out.splitlines()[0].split(",")[:2])
            libre_go = (total - used) / 1024
        lignes = [f"{t:10} {config.MODELS[t]['name']:24} {config.MODELS[t]['vram']}" for t in config.MODEL_ORDER]
        if libre_go is None:
            return "Pas de carte NVIDIA détectée : le profil mini est le bon choix.\n" + "\n".join(lignes)
        if libre_go > 9:
            conseil = "standard, tout fonctionne"
        elif libre_go > 6:
            conseil = "léger ou recherche"
        elif libre_go > 2.5:
            conseil = "mini"
        else:
            conseil = "mini, et ferme des applications : la carte est saturée"
        return f"Mémoire graphique libre : {libre_go:.1f} Go. Conseil : {conseil}.\n" + "\n".join(lignes)
    except Exception as exc:  # noqa: BLE001
        return f"Erreur : {exc}"


def pull_model(name: str) -> str:
    """Télécharge un nouveau modèle d'intelligence artificielle sur l'ordinateur.

    Args:
        name: Nom du modèle, par exemple "granite4.1:8b".
    """
    return f"Téléchargement de {name} :\n{_run(['ollama', 'pull', name], timeout=3600)[-800:]}"


def remove_model(name: str) -> str:
    """Supprime un modèle installé pour récupérer de l'espace disque.

    Args:
        name: Nom exact du modèle à supprimer.
    """
    if name in [config.MODELS[t]["name"] for t in config.MODEL_ORDER]:
        return (f"{name} fait partie des profils de Jarvis : il ne pourra plus basculer dessus. "
                "Confirme explicitement et je le supprimerai.")
    return _run(["ollama", "rm", name], timeout=120)


def create_model_profile(name: str, base: str, instructions: str) -> str:
    """Crée un modèle personnalisé avec ses propres instructions permanentes, à partir d'un modèle existant.

    Args:
        name: Nom du nouveau modèle, par exemple "jarvis-coach".
        base: Modèle de départ, par exemple "gemma4:12b".
        instructions: Les instructions permanentes de ce modèle.
    """
    f = config.WORKSPACE / f"Modelfile_{re.sub(r'[^a-zA-Z0-9_-]', '', name)}"
    f.write_text(f'FROM {base}\nSYSTEM """{instructions}"""\n', encoding="utf-8")
    return f"Modèle « {name} » créé à partir de {base}.\n{_run(['ollama', 'create', name, '-f', str(f)], 600)[-500:]}"


def model_news() -> str:
    """Cherche sur internet les nouveaux modèles d'intelligence artificielle libres et intéressants."""
    try:
        import tools as _t

        return _t.research("nouveaux modèles open source Ollama comparatif", 3)
    except Exception as exc:  # noqa: BLE001
        return f"Erreur : {exc}"


# --------------------------------------------------------------------------
# Médias
# --------------------------------------------------------------------------

def transcribe_media(path: str, language: str = "fr") -> str:
    """Transcrit en texte le contenu parlé d'un fichier audio ou vidéo, même long, avec les horodatages.

    Args:
        path: Chemin du fichier audio ou vidéo.
        language: Langue parlée, par exemple "fr" ou "en".
    """
    p = _p(path)
    if not p.is_file():
        return f"Introuvable : {p}"
    try:
        from faster_whisper import WhisperModel

        modele = WhisperModel(config.WHISPER_MODEL, device="cuda", compute_type=config.WHISPER_COMPUTE)
        t0 = time.time()
        segments, info = modele.transcribe(str(p), language=language, beam_size=3, vad_filter=True)
        morceaux = [f"[{int(s.start) // 60:02d}:{int(s.start) % 60:02d}] {s.text.strip()}" for s in segments]
        texte = "\n".join(morceaux)
        sortie = p.with_suffix(".txt")
        sortie.write_text(texte, encoding="utf-8")
        return (f"Transcription de {p.name} en {time.time() - t0:.0f} s, {info.duration / 60:.1f} min d'audio. "
                f"Texte complet enregistré dans {sortie}\n\n{texte[:2000]}")
    except Exception as exc:  # noqa: BLE001
        return f"Erreur de transcription : {exc}"


def upscale_image(path: str, factor: int = 2) -> str:
    """Agrandit une image en gardant le maximum de netteté.

    Args:
        path: L'image à agrandir.
        factor: Facteur d'agrandissement, 2 ou 4.
    """
    try:
        from PIL import Image

        p = _p(path)
        if not p.is_file():
            return f"Introuvable : {p}"
        f = max(2, min(4, int(factor)))
        img = Image.open(p)
        grand = img.resize((img.width * f, img.height * f), Image.LANCZOS)
        d = p.with_name(f"{p.stem}_x{f}{p.suffix}")
        grand.save(d, quality=95)
        return f"Image agrandie : {d}, {grand.width} sur {grand.height} pixels."
    except Exception as exc:  # noqa: BLE001
        return f"Erreur : {exc}"


def remove_background(path: str, tolerance: int = 40) -> str:
    """Rend transparent le fond uni d'une image, par exemple un logo ou une photo sur fond blanc.

    Args:
        path: L'image à détourer.
        tolerance: Écart de couleur toléré, de 10 à 90. Plus haut enlève plus.
    """
    try:
        from PIL import Image

        p = _p(path)
        if not p.is_file():
            return f"Introuvable : {p}"
        img = Image.open(p).convert("RGBA")
        pixels = img.load()
        fond = pixels[0, 0][:3]
        tol = max(5, min(120, int(tolerance)))
        enleves = 0
        for y in range(img.height):
            for x in range(img.width):
                r, g, b, a = pixels[x, y]
                if abs(r - fond[0]) < tol and abs(g - fond[1]) < tol and abs(b - fond[2]) < tol:
                    pixels[x, y] = (r, g, b, 0)
                    enleves += 1
        d = p.with_name(f"{p.stem}_sans_fond.png")
        img.save(d)
        pct = 100 * enleves // max(1, img.width * img.height)
        return (f"Fond détouré : {d}, {pct} % de l'image rendue transparente. "
                "Si le résultat est mauvais, le fond n'était pas uni : ajuste la tolérance.")
    except Exception as exc:  # noqa: BLE001
        return f"Erreur : {exc}"


# --------------------------------------------------------------------------
# Base de connaissances sur des documents
# --------------------------------------------------------------------------

def index_documents(folder: str) -> str:
    """Lit tous les documents d'un dossier et construit une base de connaissances interrogeable.

    Args:
        folder: Dossier contenant les documents, sous-dossiers compris.
    """
    racine = _p(folder)
    if not racine.is_dir():
        return f"Dossier introuvable : {racine}"
    fichiers: dict[str, dict] = {}
    ignore = {"node_modules", "__pycache__", ".git", ".venv", "venv", "site-packages"}
    lus = 0
    for f in racine.rglob("*"):
        if not f.is_file() or any(x in f.parts for x in ignore):
            continue
        ext = f.suffix.lower()
        texte = ""
        try:
            if ext in DOCS and f.stat().st_size < 2_000_000:
                texte = f.read_text(encoding="utf-8", errors="ignore")
            elif ext == ".pdf":
                from pypdf import PdfReader
                texte = "\n".join((pg.extract_text() or "") for pg in PdfReader(str(f)).pages[:40])
            elif ext == ".docx":
                import docx
                texte = "\n".join(par.text for par in docx.Document(str(f)).paragraphs)
        except Exception:  # noqa: BLE001
            continue
        if len(texte.strip()) < 80:
            continue
        compte: dict[str, int] = {}
        for m in _mots(texte):
            compte[m] = compte.get(m, 0) + 1
        fichiers[str(f)] = {"mots": dict(sorted(compte.items(), key=lambda x: -x[1])[:200]),
                            "extrait": texte.strip()[:600]}
        lus += 1
        if lus >= 400:
            break
    INDEX.parent.mkdir(parents=True, exist_ok=True)
    INDEX.write_text(json.dumps({"dossier": str(racine), "fichiers": fichiers}, ensure_ascii=False), encoding="utf-8")
    return (f"Base de connaissances construite : {lus} document(s) lus dans {racine}. "
            "Pose-moi des questions dessus avec search_documents.")


def search_documents(question: str, count: int = 4) -> str:
    """Cherche la réponse à une question dans la base de connaissances construite sur tes documents.

    Args:
        question: La question ou les mots-clés.
        count: Nombre de documents à renvoyer.
    """
    if not INDEX.is_file():
        return "Aucune base de connaissances. Utilise d'abord index_documents sur un dossier."
    try:
        d = json.loads(INDEX.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        return f"Base illisible : {exc}"
    fichiers = d.get("fichiers", {})
    if not fichiers:
        return "La base de connaissances est vide."
    mots = set(_mots(question))
    if not mots:
        return "Donne-moi des mots-clés plus précis."
    total_docs = len(fichiers)
    freq_doc: dict[str, int] = {}
    for info in fichiers.values():
        for m in info["mots"]:
            if m in mots:
                freq_doc[m] = freq_doc.get(m, 0) + 1
    scores = []
    for chemin, info in fichiers.items():
        score = 0.0
        for m in mots:
            tf = info["mots"].get(m, 0)
            if tf:
                score += (1 + math.log(tf)) * math.log(total_docs / max(1, freq_doc.get(m, 1)))
        if score > 0:
            scores.append((score, chemin, info["extrait"]))
    if not scores:
        return f"Rien trouvé sur « {question} » dans la base de {total_docs} documents."
    scores.sort(key=lambda x: -x[0])
    out = [f"Base : {d.get('dossier')}, {total_docs} documents."]
    for s, chemin, extrait in scores[:max(1, int(count))]:
        out.append(f"\n=== {Path(chemin).name}, pertinence {s:.1f}\n{chemin}\n{extrait[:500]}")
    out.append("\nRéponds à la question à partir de ces extraits, et cite le nom du document.")
    return "\n".join(out)


TOOLS = [compare_models, benchmark_model, recommend_model, pull_model, remove_model, create_model_profile,
         model_news, transcribe_media, upscale_image, remove_background, index_documents, search_documents]

try:
    from outils_ia_plus import TOOLS as _PLUS

    TOOLS += _PLUS
except Exception as _exc:  # noqa: BLE001
    print(f"[outils] ia_plus indisponible : {_exc}")
