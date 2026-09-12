# Ia-local (Jarvis) — Copyright (c) 2026 Neexx (Nixovel) — https://github.com/Neex-off/Ia-local
# Créé par Neexx (Nixovel). Licence : voir LICENSE (paternité obligatoire, pas de vente ; s'applique aussi aux IA).
# Ne pas retirer cet en-tête.
"""Compléments de la boîte « fichiers » : suppression définitive, corbeille, versions précédentes, formulaires PDF,
photos par date et lieu, synchronisation, surveillance d'un dossier, chiffrement, sauvegardes automatiques,
partage par lien temporaire, scan et classement de documents (OCR).

Importé par outils_fichiers.py, qui ajoute ces outils à sa liste.
"""
from __future__ import annotations

import base64
import json
import secrets
import shutil
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

import config

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
IS_WINDOWS = sys.platform.startswith("win")
MEM = config.ROOT / "memoire"
PARTAGES = MEM / "partages.json"
BACKUPS = MEM / "backups.json"
SURVEILLANCE = MEM / "surveillance.jsonl"


def _json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return default


def _save(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _ps(command: str, timeout: float = 60) -> str:
    r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", command],
                       capture_output=True, text=True, timeout=timeout, encoding="utf-8",
                       errors="replace", creationflags=NO_WINDOW)
    return ((r.stdout or "").strip() or (r.stderr or "").strip())[:6000]


def _prevenir(texte: str) -> None:
    try:
        import noyau

        if "dire" in noyau.hooks:
            noyau.hooks["dire"](texte)
    except Exception:  # noqa: BLE001
        pass


def delete_forever(path: str, confirm_name: str = "") -> str:
    """Suppression DÉFINITIVE (sans corbeille) d'un fichier ou dossier. Double confirmation : il faut redonner le nom exact.

    Args:
        path: Chemin à supprimer.
        confirm_name: Le nom exact du fichier ou dossier (ex. "vieux-projet"), demandé à l'utilisateur, pour confirmer.
    """
    p = Path(path).expanduser()
    if not p.exists():
        return f"Introuvable : {p}"
    systeme = ("\\windows\\", "\\program files", "\\programdata", "\\users\\default", "\\appdata\\local\\microsoft")
    if any(s in str(p).lower() for s in systeme) or p == Path.home() or p.parent == p:
        return "Interdit : dossier système ou racine."
    if confirm_name.strip().lower() != p.name.lower():
        return (f"Suppression définitive de « {p.name} » ({'dossier' if p.is_dir() else 'fichier'}) : demande à l'utilisateur "
                f"de confirmer en répétant le nom, puis rappelle delete_forever avec confirm_name=\"{p.name}\".")
    try:
        if p.is_dir():
            shutil.rmtree(p)
        else:
            p.unlink()
    except Exception as exc:  # noqa: BLE001
        return f"Échec : {exc}"
    return f"« {p.name} » supprimé définitivement."


def restore_from_trash(name: str = "") -> str:
    """Restaure un élément de la corbeille (par nom), ou liste ce qu'elle contient.

    Args:
        name: Un morceau du nom du fichier à restaurer (vide = lister).
    """
    if not IS_WINDOWS:
        return "Disponible seulement sous Windows."
    if not name:
        return _ps("$sh = New-Object -ComObject Shell.Application; $sh.Namespace(10).Items() | Select-Object -First 40 Name,Size,ModifyDate | Format-Table -AutoSize | Out-String") or "Corbeille vide."
    script = ("$sh = New-Object -ComObject Shell.Application; $c = $sh.Namespace(10); $n = 0; "
              f"foreach ($i in $c.Items()) {{ if ($i.Name -like '*{name}*') {{ $v = $i.Verbs() | Where-Object {{ $_.Name -match 'estaurer|estore' }} | Select-Object -First 1; "
              "if ($v) { $v.DoIt(); $n++ } } }; \"$n\"")
    r = _ps(script)
    try:
        n = int(r.strip().splitlines()[-1])
    except Exception:  # noqa: BLE001
        return f"Réponse inattendue : {r[:200]}"
    return f"{n} élément(s) restauré(s) depuis la corbeille." if n else f"Rien dans la corbeille ne ressemble à « {name} »."


def previous_versions(path: str) -> str:
    """Versions précédentes d'un fichier (clichés instantanés / historique des fichiers) : liste les points disponibles et ouvre l'onglet Versions précédentes.

    Args:
        path: Chemin du fichier ou dossier.
    """
    if not IS_WINDOWS:
        return "Disponible seulement sous Windows."
    p = Path(path).expanduser()
    if not p.exists():
        return f"Introuvable : {p}"
    from outils_windows import run_elevated

    cliches = run_elevated("vssadmin list shadows | Select-String 'Creation|création' | Out-String")
    _ps(f"$sh = New-Object -ComObject Shell.Application; $sh.Namespace('{p.parent}').ParseName('{p.name}').InvokeVerb('properties')")
    return (f"Clichés disponibles :\n{cliches or 'aucun (la protection du système ou l historique des fichiers doit être activée)'}\n"
            "Fenêtre Propriétés ouverte : onglet « Versions précédentes » pour choisir et restaurer (je peux cliquer avec see_screen).")


def fill_pdf_form(path: str, fields: str = "", output: str = "") -> str:
    """Remplit un formulaire PDF : liste les champs (fields vide) ou les remplit depuis un JSON {"champ": "valeur"}.

    Args:
        path: PDF à remplir.
        fields: JSON des valeurs, ex. '{"Nom": "Dupont", "Date": "12/09/2026"}'. Vide = lister les champs.
        output: Chemin du PDF rempli (vide = même nom avec -rempli).
    """
    from pypdf import PdfReader, PdfWriter

    p = Path(path).expanduser()
    if not p.exists():
        return f"Introuvable : {p}"
    reader = PdfReader(str(p))
    champs = reader.get_fields() or {}
    if not fields.strip():
        if not champs:
            return "Ce PDF n'a pas de champs de formulaire (il faudrait écrire par-dessus)."
        return "Champs : " + ", ".join(f"{k} = {v.get('/V', '')!s}".strip() for k, v in list(champs.items())[:60])
    try:
        valeurs = json.loads(fields)
    except Exception as exc:  # noqa: BLE001
        return f"JSON invalide : {exc}"
    writer = PdfWriter()
    writer.append(reader)
    for page in writer.pages:
        writer.update_page_form_field_values(page, valeurs, auto_regenerate=False)
    out = Path(output) if output else p.with_name(p.stem + "-rempli.pdf")
    with out.open("wb") as f:
        writer.write(f)
    inconnus = [k for k in valeurs if k not in champs]
    return f"PDF rempli : {out}" + (f" (champs inconnus ignorés : {', '.join(inconnus)})" if inconnus else "")


def _exif_date_gps(p: Path):
    try:
        from PIL import Image

        img = Image.open(p)
        exif = img.getexif()
        date = exif.get(306)
        try:
            sub = exif.get_ifd(0x8769)
            date = sub.get(36867) or date
        except Exception:  # noqa: BLE001
            pass
        lat = lon = None
        try:
            gps = exif.get_ifd(0x8825)
            if gps and 2 in gps and 4 in gps:
                def conv(v):
                    return float(v[0]) + float(v[1]) / 60 + float(v[2]) / 3600

                lat, lon = conv(gps[2]), conv(gps[4])
                if gps.get(1) == "S":
                    lat = -lat
                if gps.get(3) == "W":
                    lon = -lon
        except Exception:  # noqa: BLE001
            pass
        if date:
            date = datetime.strptime(str(date)[:19], "%Y:%m:%d %H:%M:%S")
        return date, lat, lon
    except Exception:  # noqa: BLE001
        return None, None, None


_VILLES: dict[str, str] = {}


def _ville(lat: float, lon: float) -> str:
    cle = f"{lat:.2f},{lon:.2f}"
    if cle in _VILLES:
        return _VILLES[cle]
    try:
        import requests

        r = requests.get("https://nominatim.openstreetmap.org/reverse",
                         params={"lat": lat, "lon": lon, "format": "json", "zoom": 10},
                         headers={"User-Agent": "jarvis-local"}, timeout=10).json()
        a = r.get("address", {})
        v = a.get("city") or a.get("town") or a.get("village") or a.get("county") or ""
    except Exception:  # noqa: BLE001
        v = ""
    _VILLES[cle] = v
    time.sleep(1.0)
    return v


def photos_by_date(folder: str, by: str = "month", place: bool = True, dry_run: bool = True) -> str:
    """Classe les photos d'un dossier par date (et lieu si les photos ont un GPS) : sous-dossiers 2026-09 ou 2026-09 Mulhouse.

    Args:
        folder: Dossier des photos.
        by: "month" ou "day".
        place: Ajouter la ville (nécessite internet, une requête par lieu).
        dry_run: True = montrer le plan, False = déplacer.
    """
    p = Path(folder).expanduser()
    if not p.is_dir():
        return f"Dossier introuvable : {p}"
    exts = {".jpg", ".jpeg", ".png", ".heic", ".webp", ".tif", ".tiff", ".dng", ".cr2", ".nef"}
    plan: dict[str, list[Path]] = {}
    for f in p.iterdir():
        if not f.is_file() or f.suffix.lower() not in exts:
            continue
        date, lat, lon = _exif_date_gps(f)
        date = date or datetime.fromtimestamp(f.stat().st_mtime)
        nom = date.strftime("%Y-%m" if by == "month" else "%Y-%m-%d")
        if place and lat is not None:
            v = _ville(lat, lon)
            if v:
                nom += f" {v}"
        plan.setdefault(nom, []).append(f)
    if not plan:
        return "Aucune photo dans ce dossier."
    if dry_run:
        return "\n".join(f"- {k} : {len(v)} photo(s)" for k, v in sorted(plan.items())) + "\nRappelle avec dry_run=False pour déplacer."
    for k, fichiers in plan.items():
        d = p / k
        d.mkdir(exist_ok=True)
        for f in fichiers:
            shutil.move(str(f), str(d / f.name))
    return f"{sum(len(v) for v in plan.values())} photos classées dans {len(plan)} dossiers."


def sync_folders(source: str, destination: str, mirror: bool = False, dry_run: bool = True) -> str:
    """Synchronise deux dossiers (copie ce qui manque ou a changé ; mirror=True supprime aussi ce qui n'existe plus dans la source).

    Args:
        source: Dossier source.
        destination: Dossier destination.
        mirror: True pour un miroir exact (supprime les fichiers en trop dans la destination).
        dry_run: True = simulation, False = exécution.
    """
    s, d = Path(source).expanduser(), Path(destination).expanduser()
    if not s.is_dir():
        return f"Source introuvable : {s}"
    if IS_WINDOWS:
        args = ["robocopy", str(s), str(d), "/MIR" if mirror else "/E", "/R:1", "/W:1", "/NP", "/NDL", "/NJH"]
        if dry_run:
            args.append("/L")
        r = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace", creationflags=NO_WINDOW)
        lignes = [l for l in r.stdout.splitlines() if l.strip()]
        return ("Simulation :\n" if dry_run else "Synchronisation faite :\n") + "\n".join(lignes[-8:])
    args = ["rsync", "-a", "--itemize-changes"] + (["--delete"] if mirror else []) + (["-n"] if dry_run else []) + [str(s) + "/", str(d) + "/"]
    r = subprocess.run(args, capture_output=True, text=True)
    return (r.stdout or r.stderr)[-2000:]


_WATCH: dict = {}


def watch_folder(action: str = "start", folder: str = "", say: bool = True) -> str:
    """Surveille un dossier : prévient (voix + notification) à chaque fichier créé, modifié ou supprimé, et tient un journal.

    Args:
        action: "start", "stop", "list" ou "log" (les 20 derniers événements).
        folder: Dossier à surveiller (start/stop).
        say: Annoncer à la voix.
    """
    if action == "list":
        return "Dossiers surveillés : " + (", ".join(_WATCH) or "aucun")
    if action == "log":
        try:
            lignes = [json.loads(l) for l in SURVEILLANCE.read_text(encoding="utf-8").splitlines()[-20:]]
        except Exception:  # noqa: BLE001
            return "Aucun événement."
        return "\n".join(f"{d['t'][11:16]} {d['evenement']} {d['chemin']}" for d in lignes)
    p = Path(folder).expanduser()
    if action == "stop":
        obs = _WATCH.pop(str(p), None)
        if obs:
            obs.stop()
            return f"Surveillance de {p} arrêtée."
        return "Ce dossier n'était pas surveillé."
    if not p.is_dir():
        return f"Dossier introuvable : {p}"
    if str(p) in _WATCH:
        return "Déjà surveillé."
    try:
        from watchdog.events import FileSystemEventHandler
        from watchdog.observers import Observer
    except Exception:  # noqa: BLE001
        return "Le paquet watchdog manque."

    class H(FileSystemEventHandler):
        def on_any_event(self, event):
            if event.is_directory or event.event_type not in ("created", "modified", "deleted", "moved"):
                return
            MEM.mkdir(parents=True, exist_ok=True)
            with SURVEILLANCE.open("a", encoding="utf-8") as f:
                f.write(json.dumps({"t": datetime.now().isoformat(timespec="seconds"), "evenement": event.event_type,
                                    "chemin": str(event.src_path)}, ensure_ascii=False) + "\n")
            if say and event.event_type in ("created", "deleted"):
                mots = {"created": "nouveau fichier", "deleted": "fichier supprimé"}[event.event_type]
                _prevenir(f"{mots} dans {p.name} : {Path(str(event.src_path)).name}")

    obs = Observer()
    obs.schedule(H(), str(p), recursive=True)
    obs.daemon = True
    obs.start()
    _WATCH[str(p)] = obs
    return f"Surveillance de {p} lancée."


def _fernet(password: str, sel: bytes):
    from cryptography.fernet import Fernet
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=sel, iterations=390000)
    return Fernet(base64.urlsafe_b64encode(kdf.derive(password.encode("utf-8"))))


def encrypt_path(path: str, password: str, delete_original: bool = False) -> str:
    """Chiffre un fichier ou un dossier (AES via Fernet, mot de passe) en un fichier .jarvis.enc.

    Args:
        path: Fichier ou dossier.
        password: Mot de passe (n'est jamais enregistré).
        delete_original: Supprimer l'original après chiffrement.
    """
    p = Path(path).expanduser()
    if not p.exists():
        return f"Introuvable : {p}"
    if p.is_dir():
        zipf = shutil.make_archive(str(config.WORKSPACE / p.name), "zip", root_dir=p)
        data, nom = Path(zipf).read_bytes(), p.name + ".zip"
        Path(zipf).unlink(missing_ok=True)
    else:
        data, nom = p.read_bytes(), p.name
    sel = secrets.token_bytes(16)
    token = _fernet(password, sel).encrypt(data)
    out = p.with_name(p.name + ".jarvis.enc")
    out.write_bytes(b"JRV1" + sel + len(nom).to_bytes(2, "big") + nom.encode("utf-8") + token)
    if delete_original:
        shutil.rmtree(p) if p.is_dir() else p.unlink()
    return f"[[secret]]Chiffré : {out} ({len(token)/1024:.0f} Ko). Sans le mot de passe, impossible à rouvrir."


def decrypt_path(path: str, password: str, output_dir: str = "") -> str:
    """Déchiffre un fichier .jarvis.enc créé par encrypt_path.

    Args:
        path: Fichier .jarvis.enc.
        password: Le mot de passe.
        output_dir: Dossier de sortie (vide = à côté).
    """
    p = Path(path).expanduser()
    if not p.exists():
        return f"Introuvable : {p}"
    raw = p.read_bytes()
    if raw[:4] != b"JRV1":
        return "Ce fichier n'a pas été chiffré par encrypt_path."
    sel = raw[4:20]
    n = int.from_bytes(raw[20:22], "big")
    nom = raw[22:22 + n].decode("utf-8")
    try:
        data = _fernet(password, sel).decrypt(raw[22 + n:])
    except Exception:  # noqa: BLE001
        return "[[secret]]Mot de passe incorrect ou fichier abîmé."
    dest = Path(output_dir).expanduser() if output_dir else p.parent
    dest.mkdir(parents=True, exist_ok=True)
    out = dest / nom
    out.write_bytes(data)
    if nom.endswith(".zip") and not p.name.endswith(".zip.jarvis.enc"):
        shutil.unpack_archive(str(out), str(dest / nom[:-4]))
        out.unlink()
        return f"[[secret]]Déchiffré et décompressé dans {dest / nom[:-4]}."
    return f"[[secret]]Déchiffré : {out}"


def auto_backup(action: str = "list", name: str = "", source: str = "", destination: str = "", when: str = "DAILY", time_of_day: str = "20:00") -> str:
    """Sauvegardes automatiques : tâche planifiée qui copie (miroir) un dossier vers un disque ou un dossier cloud synchronisé.

    Args:
        action: "list", "add", "remove" ou "run".
        name: Nom de la sauvegarde.
        source: Dossier à sauvegarder.
        destination: Dossier de destination (autre disque, OneDrive, Google Drive local…).
        when: DAILY, WEEKLY ou HOURLY.
        time_of_day: HH:MM.
    """
    base = _json(BACKUPS, {})
    if action == "list":
        return "Sauvegardes : " + ("\n".join(f"- {k} : {v['src']} -> {v['dst']} ({v['quand']})" for k, v in base.items()) or "aucune")
    if action == "add":
        s, d = Path(source).expanduser(), Path(destination).expanduser()
        if not s.is_dir():
            return f"Source introuvable : {s}"
        if IS_WINDOWS:
            log = config.WORKSPACE / f"backup-{name}.log"
            cmd = f'robocopy "{s}" "{d}" /MIR /R:1 /W:1 /NP /LOG+:"{log}"'
            args = ["schtasks", "/Create", "/TN", f"Jarvis backup {name}", "/TR", cmd, "/SC", when, "/F"]
            if when != "HOURLY":
                args += ["/ST", time_of_day]
            r = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace", creationflags=NO_WINDOW)
            if r.returncode != 0:
                return f"Échec de la tâche planifiée : {(r.stderr or r.stdout)[:200]}"
        base[name] = {"src": str(s), "dst": str(d), "quand": f"{when} {time_of_day}"}
        _save(BACKUPS, base)
        return f"Sauvegarde « {name} » programmée : {s} -> {d}, {when} à {time_of_day}."
    if action == "remove":
        if IS_WINDOWS:
            subprocess.run(["schtasks", "/Delete", "/TN", f"Jarvis backup {name}", "/F"], capture_output=True, creationflags=NO_WINDOW)
        base.pop(name, None)
        _save(BACKUPS, base)
        return f"Sauvegarde « {name} » retirée."
    if action == "run":
        b = base.get(name)
        if not b:
            return f"Sauvegarde inconnue : {name}."
        return sync_folders(b["src"], b["dst"], mirror=True, dry_run=False)
    return "Action : list, add, remove ou run."


_SHARE: dict = {"serveur": None}


def share_file(path: str, minutes: int = 60) -> str:
    """Partage un fichier par lien temporaire sur le réseau local (téléphone, autre PC, même Wi-Fi) ; le lien expire.

    Args:
        path: Fichier à partager.
        minutes: Durée de validité.
    """
    import http.server
    import socket

    p = Path(path).expanduser()
    if not p.is_file():
        return f"Fichier introuvable : {p}"
    partages = _json(PARTAGES, {})
    token = secrets.token_urlsafe(12)
    partages[token] = {"chemin": str(p), "expire": time.time() + 60 * int(minutes)}
    _save(PARTAGES, partages)
    port = getattr(config, "SHARE_PORT", 8766)
    if _SHARE["serveur"] is None:
        class H(http.server.BaseHTTPRequestHandler):
            def log_message(self, *a):  # noqa: D102
                pass

            def do_GET(self):  # noqa: N802
                tok = self.path.strip("/").split("/")[0]
                info = _json(PARTAGES, {}).get(tok)
                if not info or info["expire"] < time.time():
                    self.send_response(404)
                    self.end_headers()
                    self.wfile.write(b"Lien expire ou inconnu.")
                    return
                f = Path(info["chemin"])
                data = f.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "application/octet-stream")
                self.send_header("Content-Disposition", f'attachment; filename="{f.name}"')
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        srv = http.server.ThreadingHTTPServer(("0.0.0.0", port), H)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        _SHARE["serveur"] = srv
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
    except Exception:  # noqa: BLE001
        ip = "127.0.0.1"
    return f"Lien valable {minutes} min sur le réseau local : http://{ip}:{port}/{token}/{p.name}"


def _ocr_image(p: Path) -> str:
    if not IS_WINDOWS:
        return ""
    try:
        import asyncio

        from PIL import Image, ImageOps
        from winsdk.windows.graphics.imaging import BitmapAlphaMode, BitmapPixelFormat, SoftwareBitmap
        from winsdk.windows.media.ocr import OcrEngine
        from winsdk.windows.security.cryptography import CryptographicBuffer

        img = Image.open(p).convert("RGB")
        if img.width < 1500:
            img = img.resize((img.width * 2, img.height * 2))
        img = ImageOps.autocontrast(img.convert("L"), cutoff=1).convert("RGB")
        engine = OcrEngine.try_create_from_user_profile_languages()

        async def lire():
            data = CryptographicBuffer.create_from_byte_array(img.convert("RGBA").tobytes())
            bmp = SoftwareBitmap.create_copy_from_buffer(data, BitmapPixelFormat.RGBA8, img.width, img.height, BitmapAlphaMode.STRAIGHT)
            return await engine.recognize_async(bmp)

        res = asyncio.run(lire())
        return "\n".join(l.text for l in res.lines)
    except Exception:  # noqa: BLE001
        return ""


CATEGORIES = {
    "Factures": ("facture", "invoice", "montant ttc", "total ttc", "n° de facture"),
    "Devis": ("devis", "quotation", "estimation"),
    "Contrats": ("contrat", "convention", "conditions générales", "signature", "bail"),
    "Fiches de paie": ("bulletin de paie", "fiche de paie", "salaire net", "net à payer"),
    "Impôts": ("impôt", "impots", "avis d'imposition", "dgfip", "finances publiques", "taxe"),
    "Banque": ("relevé", "iban", "bic", "solde", "virement", "carte bancaire"),
    "Assurance": ("assurance", "assuré", "sinistre", "mutuelle"),
    "Santé": ("ordonnance", "docteur", "médecin", "pharmacie", "ameli", "sécurité sociale", "cpam"),
    "École": ("bulletin", "epitech", "université", "école", "scolarité"),
    "Logement": ("loyer", "quittance", "bailleur", "locataire", "électricité", "edf", "gaz"),
    "Identité": ("carte nationale", "passeport", "permis de conduire", "acte de naissance"),
}


def scan_documents(folder: str, destination: str = "", dry_run: bool = True) -> str:
    """Lit les documents scannés (images, PDF) d'un dossier par OCR et les classe par catégorie (Factures, Impôts, Banque, Santé…).

    Args:
        folder: Dossier des scans.
        destination: Dossier de classement (vide = le même dossier).
        dry_run: True = montrer le plan, False = déplacer.
    """
    p = Path(folder).expanduser()
    if not p.is_dir():
        return f"Dossier introuvable : {p}"
    dest = Path(destination).expanduser() if destination else p
    plan: dict[str, list[Path]] = {}
    for f in p.iterdir():
        if not f.is_file():
            continue
        texte = ""
        if f.suffix.lower() in (".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"):
            texte = _ocr_image(f)
        elif f.suffix.lower() == ".pdf":
            try:
                from pypdf import PdfReader

                texte = " ".join((pg.extract_text() or "") for pg in PdfReader(str(f)).pages[:3])
            except Exception:  # noqa: BLE001
                texte = ""
        else:
            continue
        bas = texte.lower()
        cat = next((c for c, mots in CATEGORIES.items() if any(m in bas for m in mots)), "À trier")
        plan.setdefault(cat, []).append(f)
    if not plan:
        return "Aucun document lisible."
    if dry_run:
        return "\n".join(f"- {c} : {', '.join(x.name for x in fs[:8])}{' …' if len(fs) > 8 else ''}" for c, fs in plan.items()) + "\nRappelle avec dry_run=False pour classer."
    n = 0
    for c, fs in plan.items():
        d = dest / c
        d.mkdir(parents=True, exist_ok=True)
        for f in fs:
            shutil.move(str(f), str(d / f.name))
            n += 1
    return f"{n} documents classés dans {len(plan)} catégories sous {dest}."


TOOLS = [delete_forever, restore_from_trash, previous_versions, fill_pdf_form, photos_by_date, sync_folders,
         watch_folder, encrypt_path, decrypt_path, auto_backup, share_file, scan_documents]
