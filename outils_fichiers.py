# Ia-local (Jarvis) — Copyright (c) 2026 Neexx (Nixovel) — https://github.com/Neex-off/Ia-local
# Créé par Neexx (Nixovel). Licence : voir LICENSE (paternité obligatoire, pas de vente ; s'applique aussi aux IA).
# Ne pas retirer cet en-tête.
"""Boîte à outils « fichiers » : recherche dans le contenu, rangement, archives, documents, images.

Chargée à la demande par tools.open_toolbox("fichiers").
"""
from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
import time
import zipfile
from datetime import datetime
from pathlib import Path

import config

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
IGNORE = {"node_modules", "__pycache__", ".git", ".venv", "venv", "site-packages", "AppData", "Windows"}
TEXTE = {".txt", ".md", ".py", ".js", ".ts", ".json", ".csv", ".html", ".css", ".yml", ".yaml", ".log", ".ini", ".xml"}


def _p(chemin: str) -> Path:
    """Chemin absolu tel quel ; sinon on cherche le nom donné aux endroits plausibles (dossier de travail,
    dossier du projet, dossier personnel) avant de retomber sur le dossier de travail."""
    brut = str(chemin).strip('" ')
    p = Path(brut).expanduser()
    if p.is_absolute():
        return p
    if brut in (".", "./", ".\\"):
        return config.ROOT
    for base in (config.WORKSPACE, config.ROOT, Path.cwd(), Path.home(), Path.home() / "Downloads",
                 Path.home() / "Desktop", Path.home() / "Documents"):
        try:
            if (base / p).exists():
                return base / p
        except OSError:
            continue
    return config.WORKSPACE / p


def _dest(chemin: str) -> Path:
    """Chemin d'un fichier ou d'un dossier À CRÉER : on résout d'après le dossier parent, qui lui existe déjà.
    « workspace/essai.zip » donne donc le workspace du projet, et non un workspace dans le workspace."""
    brut = str(chemin).strip('" ')
    p = Path(brut).expanduser()
    if p.is_absolute():
        return p
    for parent in list(p.parents)[:-1]:      # du plus proche au plus lointain, sans le « . » final
        base = _p(str(parent))
        if base.is_dir():
            return base / p.relative_to(parent)
    return config.WORKSPACE / p


def _walk(racine: Path, max_fichiers: int = 60000):
    n = 0
    for dossier, sous, fichiers in os.walk(racine):
        sous[:] = [d for d in sous if d not in IGNORE and not d.startswith(".")]
        for f in fichiers:
            n += 1
            if n > max_fichiers:
                return
            yield Path(dossier) / f


# --------------------------------------------------------------------------
# Recherche et rangement
# --------------------------------------------------------------------------

def search_in_files(text: str, folder: str, extension: str = "") -> str:
    """Cherche un texte À L'INTÉRIEUR des fichiers d'un dossier, pas seulement dans leur nom.

    Args:
        text: Le texte ou le mot à trouver dans le contenu.
        folder: Dossier où chercher, sous-dossiers compris.
        extension: Ne garder qu'une extension, par exemple "py" ou "txt". Vide = tous les fichiers texte.
    """
    racine = _p(folder)
    if not racine.is_dir():
        return f"Dossier introuvable : {racine}"
    ext = "." + extension.lstrip(".").lower() if extension else ""
    cible, trouves, lus = text.lower(), [], 0
    for f in _walk(racine):
        if ext and f.suffix.lower() != ext:
            continue
        if not ext and f.suffix.lower() not in TEXTE:
            continue
        try:
            if f.stat().st_size > 3_000_000:
                continue
            contenu = f.read_text(encoding="utf-8", errors="ignore")
            lus += 1
        except Exception:  # noqa: BLE001
            continue
        for i, ligne in enumerate(contenu.splitlines(), 1):
            if cible in ligne.lower():
                trouves.append(f"{f} ligne {i} : {ligne.strip()[:120]}")
                break
        if len(trouves) >= 40:
            break
    if not trouves:
        return f"« {text} » introuvable dans le contenu de {lus} fichier(s) sous {racine}."
    return f"{len(trouves)} fichier(s) contiennent « {text} » sur {lus} lus :\n" + "\n".join(trouves)


def find_duplicates(folder: str) -> str:
    """Trouve les fichiers en double dans un dossier, même contenu exact, pour faire de la place.

    Args:
        folder: Dossier à analyser.
    """
    racine = _p(folder)
    if not racine.is_dir():
        return f"Dossier introuvable : {racine}"
    par_taille: dict[int, list[Path]] = {}
    for f in _walk(racine):
        try:
            t = f.stat().st_size
        except OSError:
            continue
        if t > 0:
            par_taille.setdefault(t, []).append(f)
    doublons, gagne = [], 0
    for taille, fichiers in par_taille.items():
        if len(fichiers) < 2:
            continue
        par_hash: dict[str, list[Path]] = {}
        for f in fichiers:
            try:
                h = hashlib.md5(f.read_bytes()[:1_000_000]).hexdigest()
            except Exception:  # noqa: BLE001
                continue
            par_hash.setdefault(h, []).append(f)
        for groupe in par_hash.values():
            if len(groupe) > 1:
                gagne += taille * (len(groupe) - 1)
                doublons.append(f"{taille / 2**20:.1f} Mo x{len(groupe)} : " + " | ".join(str(g) for g in groupe[:3]))
    if not doublons:
        return f"Aucun doublon sous {racine}."
    return (f"{len(doublons)} groupe(s) de doublons, {gagne / 2**20:.0f} Mo récupérables :\n"
            + "\n".join(doublons[:25]))


def find_big_files(folder: str, count: int = 15) -> str:
    """Liste les plus gros fichiers d'un dossier, pour libérer de l'espace disque.

    Args:
        folder: Dossier à analyser.
        count: Nombre de fichiers à renvoyer.
    """
    racine = _p(folder)
    if not racine.is_dir():
        return f"Dossier introuvable : {racine}"
    tailles = []
    for f in _walk(racine):
        try:
            tailles.append((f.stat().st_size, f))
        except OSError:
            continue
    tailles.sort(key=lambda x: -x[0])
    if not tailles:
        return f"Aucun fichier sous {racine}."
    return f"Plus gros fichiers de {racine} :\n" + "\n".join(
        f"{t / 2**20:8.1f} Mo  {f}" for t, f in tailles[:max(1, int(count))])


def find_old_files(folder: str, days: int = 365) -> str:
    """Liste les fichiers qui n'ont pas été ouverts depuis longtemps, candidats au ménage.

    Args:
        folder: Dossier à analyser.
        days: Nombre de jours sans ouverture.
    """
    racine = _p(folder)
    if not racine.is_dir():
        return f"Dossier introuvable : {racine}"
    limite = time.time() - max(1, int(days)) * 86400
    vieux = []
    for f in _walk(racine):
        try:
            st = f.stat()
            if st.st_atime < limite:
                vieux.append((st.st_atime, st.st_size, f))
        except OSError:
            continue
    vieux.sort(key=lambda x: x[0])
    if not vieux:
        return f"Aucun fichier inutilisé depuis {days} jours sous {racine}."
    total = sum(t for _a, t, _f in vieux) / 2**20
    lignes = [f"{datetime.fromtimestamp(a):%d/%m/%Y}  {t / 2**20:7.1f} Mo  {f}" for a, t, f in vieux[:25]]
    return f"{len(vieux)} fichier(s) inutilisés depuis {days} jours, {total:.0f} Mo :\n" + "\n".join(lignes)


def tidy_folder(folder: str) -> str:
    """Range un dossier en triant ses fichiers dans des sous-dossiers par type : Images, Documents, Videos…

    Args:
        folder: Dossier à ranger, par exemple le dossier Téléchargements.
    """
    racine = _p(folder)
    if not racine.is_dir():
        return f"Dossier introuvable : {racine}"
    familles = {
        "Images": {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".svg", ".heic"},
        "Documents": {".pdf", ".docx", ".doc", ".txt", ".md", ".xlsx", ".pptx", ".csv", ".odt"},
        "Videos": {".mp4", ".mkv", ".avi", ".mov", ".webm"},
        "Audio": {".mp3", ".wav", ".flac", ".ogg", ".m4a"},
        "Archives": {".zip", ".rar", ".7z", ".tar", ".gz"},
        "Programmes": {".exe", ".msi", ".bat", ".ps1"},
    }
    deplaces: dict[str, int] = {}
    for f in list(racine.iterdir()):
        if not f.is_file():
            continue
        for nom, exts in familles.items():
            if f.suffix.lower() in exts:
                cible = racine / nom
                cible.mkdir(exist_ok=True)
                dest = cible / f.name
                i = 1
                while dest.exists():
                    dest = cible / f"{f.stem} ({i}){f.suffix}"
                    i += 1
                try:
                    shutil.move(str(f), str(dest))
                    deplaces[nom] = deplaces.get(nom, 0) + 1
                except Exception:  # noqa: BLE001
                    pass
                break
    if not deplaces:
        return f"Rien à ranger dans {racine}."
    return f"Rangé dans {racine} : " + ", ".join(f"{n} fichier(s) vers {d}" for d, n in deplaces.items())


# --------------------------------------------------------------------------
# Manipulation
# --------------------------------------------------------------------------

def make_folder(path: str) -> str:
    """Crée un dossier, et les dossiers parents s'il en manque.

    Args:
        path: Chemin du dossier à créer.
    """
    p = _dest(path)
    p.mkdir(parents=True, exist_ok=True)
    return f"Dossier créé : {p}"


def rename_path(path: str, new_name: str) -> str:
    """Renomme un fichier ou un dossier.

    Args:
        path: Chemin actuel.
        new_name: Nouveau nom, sans le dossier.
    """
    p = _p(path)
    if not p.exists():
        return f"Introuvable : {p}"
    cible = p.with_name(new_name)
    if cible.exists():
        return f"Il existe déjà un élément nommé {new_name}."
    p.rename(cible)
    return f"Renommé : {p.name} devient {cible.name}"


def copy_path(source: str, destination: str) -> str:
    """Copie un fichier ou un dossier entier vers une destination.

    Args:
        source: Fichier ou dossier à copier.
        destination: Dossier ou chemin de destination.
    """
    s, d = _p(source), _dest(destination)
    if not s.exists():
        return f"Introuvable : {s}"
    if d.is_dir():
        d = d / s.name
    if s.is_dir():
        shutil.copytree(s, d, dirs_exist_ok=True)
    else:
        d.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(s, d)
    return f"Copié : {s} vers {d}"


def move_path(source: str, destination: str) -> str:
    """Déplace un fichier ou un dossier.

    Args:
        source: Fichier ou dossier à déplacer.
        destination: Dossier ou chemin de destination.
    """
    s, d = _p(source), _dest(destination)
    if not s.exists():
        return f"Introuvable : {s}"
    if d.is_dir():
        d = d / s.name
    d.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(s), str(d))
    return f"Déplacé : {s} vers {d}"


def trash_path(path: str) -> str:
    """Met un fichier ou un dossier à la corbeille. Récupérable, ce n'est jamais une suppression définitive.

    Args:
        path: Chemin à envoyer à la corbeille.
    """
    p = _p(path)
    if not p.exists():
        return f"Introuvable : {p}"
    try:
        from send2trash import send2trash

        send2trash(str(p))
        return f"Envoyé à la corbeille : {p}. Récupérable depuis la corbeille."
    except Exception as exc:  # noqa: BLE001
        return f"Erreur : {exc}"


def bulk_rename(folder: str, search: str, replace: str, extension: str = "") -> str:
    """Renomme en masse les fichiers d'un dossier en remplaçant un morceau de leur nom.

    Args:
        folder: Dossier contenant les fichiers.
        search: Texte à remplacer dans les noms.
        replace: Texte de remplacement.
        extension: Ne traiter qu'une extension, par exemple "jpg". Vide = toutes.
    """
    racine = _p(folder)
    if not racine.is_dir():
        return f"Dossier introuvable : {racine}"
    ext = "." + extension.lstrip(".").lower() if extension else ""
    faits = []
    for f in sorted(racine.iterdir()):
        if not f.is_file() or (ext and f.suffix.lower() != ext) or search not in f.name:
            continue
        cible = f.with_name(f.name.replace(search, replace))
        if cible.exists():
            continue
        f.rename(cible)
        faits.append(f"{f.name} devient {cible.name}")
    if not faits:
        return f"Aucun fichier de {racine} ne contient « {search} »."
    return f"{len(faits)} fichier(s) renommés :\n" + "\n".join(faits[:20])


def zip_folder(source: str, destination: str = "") -> str:
    """Compresse un fichier ou un dossier en archive zip.

    Args:
        source: Fichier ou dossier à compresser.
        destination: Chemin du zip à créer. Vide = à côté de la source.
    """
    s = _p(source)
    if not s.exists():
        return f"Introuvable : {s}"
    d = _dest(destination) if destination else s.with_suffix(".zip")
    if d.suffix.lower() != ".zip":
        d = d.with_suffix(".zip")
    with zipfile.ZipFile(d, "w", zipfile.ZIP_DEFLATED) as z:
        if s.is_file():
            z.write(s, s.name)
        else:
            for f in _walk(s):
                z.write(f, f.relative_to(s.parent))
    return f"Archive créée : {d}, {d.stat().st_size / 2**20:.1f} Mo"


def unzip_file(archive: str, destination: str = "") -> str:
    """Décompresse une archive zip dans un dossier.

    Args:
        archive: Le fichier zip.
        destination: Dossier de destination. Vide = un dossier du même nom à côté.
    """
    a = _p(archive)
    if not a.is_file():
        return f"Archive introuvable : {a}"
    d = _dest(destination) if destination else a.with_suffix("")
    d.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(a) as z:
        noms = z.namelist()
        z.extractall(d)
    return f"{len(noms)} élément(s) extraits dans {d}"


def compare_files(file_a: str, file_b: str) -> str:
    """Compare deux fichiers texte et montre les lignes qui diffèrent.

    Args:
        file_a: Premier fichier.
        file_b: Deuxième fichier.
    """
    import difflib

    a, b = _p(file_a), _p(file_b)
    if not a.is_file() or not b.is_file():
        return "Un des deux fichiers est introuvable."
    la = a.read_text(encoding="utf-8", errors="ignore").splitlines()
    lb = b.read_text(encoding="utf-8", errors="ignore").splitlines()
    diff = list(difflib.unified_diff(la, lb, a.name, b.name, lineterm="", n=1))
    if not diff:
        return f"{a.name} et {b.name} sont identiques."
    return f"Différences, {len(diff)} lignes :\n" + "\n".join(diff[:60])


def print_file(path: str) -> str:
    """Envoie un fichier à l'imprimante par défaut.

    Args:
        path: Chemin du document à imprimer.
    """
    p = _p(path)
    if not p.is_file():
        return f"Introuvable : {p}"
    if not sys.platform.startswith("win"):
        subprocess.run(["lp", str(p)], capture_output=True)
        return f"Envoyé à l'imprimante : {p.name}"
    try:
        os.startfile(str(p), "print")  # noqa: S606
        return f"Envoyé à l'imprimante par défaut : {p.name}"
    except Exception as exc:  # noqa: BLE001
        return f"Erreur d'impression : {exc}"


# --------------------------------------------------------------------------
# Documents et images
# --------------------------------------------------------------------------

def read_document(path: str, max_chars: int = 6000) -> str:
    """Lit le contenu d'un PDF, d'un Word (.docx) ou d'un Excel (.xlsx) pour pouvoir le résumer ou en parler.

    Args:
        path: Chemin du document.
        max_chars: Longueur maximale du texte renvoyé.
    """
    p = _p(path)
    if not p.is_file():
        return f"Introuvable : {p}"
    ext = p.suffix.lower()
    try:
        if ext == ".pdf":
            from pypdf import PdfReader

            r = PdfReader(str(p))
            texte = "\n".join((page.extract_text() or "") for page in r.pages)
            entete = f"PDF « {p.name} », {len(r.pages)} page(s) :\n"
        elif ext == ".docx":
            import docx

            d = docx.Document(str(p))
            texte = "\n".join(par.text for par in d.paragraphs)
            entete = f"Word « {p.name} », {len(d.paragraphs)} paragraphe(s) :\n"
        elif ext in (".xlsx", ".xlsm"):
            import openpyxl

            wb = openpyxl.load_workbook(str(p), data_only=True)
            morceaux = []
            for ws in wb.worksheets:
                morceaux.append(f"--- Feuille « {ws.title} », {ws.max_row} lignes ---")
                for ligne in ws.iter_rows(max_row=40, values_only=True):
                    cells = [str(c) for c in ligne if c is not None]
                    if cells:
                        morceaux.append(" | ".join(cells))
            texte = "\n".join(morceaux)
            entete = f"Excel « {p.name} », {len(wb.worksheets)} feuille(s) :\n"
        else:
            texte = p.read_text(encoding="utf-8", errors="ignore")
            entete = f"Fichier « {p.name} » :\n"
        texte = texte.strip()
        if not texte:
            return f"{entete}Le document ne contient pas de texte lisible, il est peut-être scanné en image."
        return entete + texte[:max_chars] + ("\n... [tronqué]" if len(texte) > max_chars else "")
    except Exception as exc:  # noqa: BLE001
        return f"Erreur de lecture : {exc}"


def merge_pdf(files: str, destination: str) -> str:
    """Fusionne plusieurs PDF en un seul.

    Args:
        files: Les chemins des PDF séparés par des points-virgules, dans l'ordre voulu.
        destination: Chemin du PDF à créer.
    """
    try:
        from pypdf import PdfWriter

        chemins = [_p(f) for f in str(files).split(";") if f.strip()]
        manquants = [str(c) for c in chemins if not c.is_file()]
        if manquants:
            return "PDF introuvable(s) : " + ", ".join(manquants)
        w = PdfWriter()
        for c in chemins:
            w.append(str(c))
        d = _dest(destination)
        d.parent.mkdir(parents=True, exist_ok=True)
        with open(d, "wb") as f:
            w.write(f)
        return f"{len(chemins)} PDF fusionnés dans {d}"
    except Exception as exc:  # noqa: BLE001
        return f"Erreur : {exc}"


def split_pdf(path: str, pages: str, destination: str = "") -> str:
    """Extrait certaines pages d'un PDF dans un nouveau fichier.

    Args:
        path: Le PDF d'origine.
        pages: Les pages voulues, par exemple "1-3" ou "2,5,9". La première page porte le numéro 1.
        destination: Chemin du PDF à créer. Vide = à côté de l'original.
    """
    try:
        from pypdf import PdfReader, PdfWriter

        p = _p(path)
        if not p.is_file():
            return f"Introuvable : {p}"
        r = PdfReader(str(p))
        voulues: list[int] = []
        for morceau in str(pages).replace(" ", "").split(","):
            if "-" in morceau:
                a, b = morceau.split("-")
                voulues += list(range(int(a), int(b) + 1))
            elif morceau:
                voulues.append(int(morceau))
        voulues = [n for n in voulues if 1 <= n <= len(r.pages)]
        if not voulues:
            return f"Aucune page valide, le document a {len(r.pages)} pages."
        w = PdfWriter()
        for n in voulues:
            w.add_page(r.pages[n - 1])
        d = _dest(destination) if destination else p.with_name(f"{p.stem}_extrait.pdf")
        with open(d, "wb") as f:
            w.write(f)
        return f"{len(voulues)} page(s) extraites dans {d}"
    except Exception as exc:  # noqa: BLE001
        return f"Erreur : {exc}"


def convert_image(path: str, to_format: str = "jpg", width: int = 0) -> str:
    """Convertit une image dans un autre format et la redimensionne si besoin.

    Args:
        path: Image d'origine.
        to_format: Format voulu : "jpg", "png" ou "webp".
        width: Largeur voulue en pixels. 0 = garder la taille.
    """
    try:
        from PIL import Image

        p = _p(path)
        if not p.is_file():
            return f"Introuvable : {p}"
        img = Image.open(p)
        if width and int(width) > 0:
            h = int(img.height * int(width) / img.width)
            img = img.resize((int(width), h), Image.LANCZOS)
        fmt = to_format.lower().lstrip(".")
        d = p.with_suffix("." + ("jpg" if fmt in ("jpg", "jpeg") else fmt))
        if fmt in ("jpg", "jpeg") and img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
        img.save(d, quality=90)
        return f"Image convertie : {d}, {img.width}x{img.height}, {d.stat().st_size / 1024:.0f} Ko"
    except Exception as exc:  # noqa: BLE001
        return f"Erreur : {exc}"


def compress_image(path: str, quality: int = 75, max_width: int = 1920) -> str:
    """Compresse une image pour l'alléger, par exemple avant un envoi par mail ou une mise en ligne.

    Args:
        path: Image à compresser.
        quality: Qualité de 40 à 95. 75 est un bon compromis.
        max_width: Largeur maximale en pixels.
    """
    try:
        from PIL import Image

        p = _p(path)
        if not p.is_file():
            return f"Introuvable : {p}"
        avant = p.stat().st_size
        img = Image.open(p)
        if img.width > int(max_width):
            h = int(img.height * int(max_width) / img.width)
            img = img.resize((int(max_width), h), Image.LANCZOS)
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
        d = p.with_name(f"{p.stem}_compresse.jpg")
        img.save(d, quality=max(40, min(95, int(quality))), optimize=True)
        apres = d.stat().st_size
        gain = 100 - apres * 100 // max(avant, 1)
        return f"Compressée : {d}, de {avant / 1024:.0f} Ko à {apres / 1024:.0f} Ko, {gain} % de gagné"
    except Exception as exc:  # noqa: BLE001
        return f"Erreur : {exc}"


def strip_exif(path: str) -> str:
    """Supprime les métadonnées d'une image, lieu GPS, appareil et date, avant de la partager.

    Args:
        path: Image à nettoyer.
    """
    try:
        from PIL import Image

        p = _p(path)
        if not p.is_file():
            return f"Introuvable : {p}"
        img = Image.open(p)
        avait = bool(getattr(img, "_getexif", lambda: None)())
        propre = Image.new(img.mode, img.size)
        propre.putdata(list(img.getdata()))
        d = p.with_name(f"{p.stem}_sans_metadonnees{p.suffix}")
        propre.save(d)
        return f"Métadonnées {'supprimées' if avait else 'déjà absentes'} : {d}"
    except Exception as exc:  # noqa: BLE001
        return f"Erreur : {exc}"


TOOLS = [search_in_files, find_duplicates, find_big_files, find_old_files, tidy_folder,
         make_folder, rename_path, copy_path, move_path, trash_path, bulk_rename,
         zip_folder, unzip_file, compare_files, print_file,
         read_document, merge_pdf, split_pdf, convert_image, compress_image, strip_exif]

try:
    from outils_fichiers_plus import TOOLS as _PLUS

    TOOLS += _PLUS
except Exception as _exc:  # noqa: BLE001
    print(f"[outils] fichiers_plus indisponible : {_exc}")
