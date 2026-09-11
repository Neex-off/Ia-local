# Ia-local (Jarvis) — Copyright (c) 2026 Neexx (Nixovel) — https://github.com/Neex-off/Ia-local
# Créé par Neexx (Nixovel). Licence : voir LICENSE (paternité obligatoire, pas de vente ; s'applique aussi aux IA).
# Ne pas retirer cet en-tête.
"""Boîte à outils « contenu » : vidéo, audio, sous-titres, design, calendrier éditorial, jeu et stream.

Chargée à la demande par tools.open_toolbox("contenu").
Catalogue : Création de contenu, Vidéo & audio, Design & branding, Gaming & stream.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import unicodedata
from datetime import date
from pathlib import Path

import config

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
CONTENU = config.ROOT / "memoire" / "contenu.json"
TAILLES = {
    "youtube miniature": (1280, 720), "youtube banniere": (2048, 1152), "instagram post": (1080, 1080),
    "instagram story": (1080, 1920), "tiktok": (1080, 1920), "x banniere": (1500, 500),
    "linkedin banniere": (1584, 396), "open graph": (1200, 630), "favicon": (512, 512),
}


def _p(chemin: str) -> Path:
    brut = str(chemin).strip('" ')
    p = Path(brut).expanduser()
    if p.is_absolute():
        return p
    for base in (config.WORKSPACE, config.ROOT, Path.cwd(), Path.home() / "Videos",
                 Path.home() / "Pictures", Path.home() / "Desktop", Path.home() / "Downloads"):
        if (base / p).exists():
            return base / p
    return config.WORKSPACE / p


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s).lower())
    return "".join(c for c in s if not unicodedata.combining(c)).strip()


def _charge() -> dict:
    if not CONTENU.is_file():
        return {"calendrier": []}
    try:
        return json.loads(CONTENU.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {"calendrier": []}


def _sauve(d: dict) -> None:
    CONTENU.parent.mkdir(parents=True, exist_ok=True)
    CONTENU.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")


def _ffmpeg(*args: str, timeout: float = 1800) -> str:
    if not shutil.which("ffmpeg"):
        return ("ffmpeg n'est pas installé, il est indispensable pour la vidéo et l'audio. "
                "Je peux l'installer avec install_software(\"ffmpeg\") si tu veux.")
    try:
        r = subprocess.run(["ffmpeg", "-y", *args], capture_output=True, text=True, timeout=timeout,
                           encoding="utf-8", errors="replace", creationflags=NO_WINDOW)
        return "ok" if r.returncode == 0 else (r.stderr or "")[-800:]
    except subprocess.TimeoutExpired:
        return "Le traitement a mis trop de temps."
    except Exception as exc:  # noqa: BLE001
        return f"Erreur : {exc}"


# --------------------------------------------------------------------------
# Vidéo et audio
# --------------------------------------------------------------------------

def remove_silence(video: str, threshold_db: int = -35, min_silence: float = 0.6) -> str:
    """Coupe automatiquement les silences d'une vidéo ou d'un audio, pour un montage plus rythmé.

    Args:
        video: Le fichier à traiter.
        threshold_db: Niveau en dessous duquel c'est du silence, par exemple -35.
        min_silence: Durée minimale d'un silence à couper, en secondes.
    """
    p = _p(video)
    if not p.is_file():
        return f"Introuvable : {p}"
    d = p.with_name(f"{p.stem}_sans_silence{p.suffix}")
    res = _ffmpeg("-i", str(p), "-af",
                  f"silenceremove=stop_periods=-1:stop_duration={min_silence}:stop_threshold={threshold_db}dB",
                  str(d), timeout=3600)
    if res != "ok":
        return res
    return f"Silences coupés : {d}, {p.stat().st_size / 2**20:.0f} Mo devient {d.stat().st_size / 2**20:.0f} Mo."


def normalize_audio(file: str) -> str:
    """Égalise le volume d'un fichier audio ou vidéo pour qu'il soit au bon niveau du début à la fin.

    Args:
        file: Le fichier à traiter.
    """
    p = _p(file)
    if not p.is_file():
        return f"Introuvable : {p}"
    d = p.with_name(f"{p.stem}_normalise{p.suffix}")
    res = _ffmpeg("-i", str(p), "-af", "loudnorm=I=-16:TP=-1.5:LRA=11", str(d))
    return f"Son normalisé : {d}" if res == "ok" else res


def denoise_audio(file: str, force: int = 12) -> str:
    """Réduit le bruit de fond d'un enregistrement : souffle du micro, ventilateur, bruit de pièce.

    Args:
        file: Le fichier à traiter.
        force: Force de la réduction, de 5 à 30.
    """
    p = _p(file)
    if not p.is_file():
        return f"Introuvable : {p}"
    d = p.with_name(f"{p.stem}_propre{p.suffix}")
    res = _ffmpeg("-i", str(p), "-af", f"afftdn=nr={max(5, min(30, int(force)))}:nf=-25", str(d))
    return f"Bruit de fond réduit : {d}" if res == "ok" else res


def extract_audio(video: str) -> str:
    """Extrait la piste audio d'une vidéo en mp3.

    Args:
        video: Le fichier vidéo.
    """
    p = _p(video)
    if not p.is_file():
        return f"Introuvable : {p}"
    d = p.with_suffix(".mp3")
    res = _ffmpeg("-i", str(p), "-vn", "-b:a", "192k", str(d))
    return f"Audio extrait : {d}" if res == "ok" else res


def trim_video(video: str, start: str, end: str = "") -> str:
    """Découpe un extrait d'une vidéo entre deux instants.

    Args:
        video: Le fichier vidéo.
        start: Début de l'extrait, au format "00:01:30" ou en secondes.
        end: Fin de l'extrait. Vide = jusqu'au bout.
    """
    p = _p(video)
    if not p.is_file():
        return f"Introuvable : {p}"
    d = p.with_name(f"{p.stem}_extrait{p.suffix}")
    args = ["-ss", start, "-i", str(p)]
    if end:
        args += ["-to", end]
    res = _ffmpeg(*args, "-c", "copy", str(d))
    return f"Extrait créé : {d}" if res == "ok" else res


def convert_video(video: str, to_format: str = "mp4", height: int = 0) -> str:
    """Convertit une vidéo dans un autre format ou une autre résolution.

    Args:
        video: Le fichier vidéo.
        to_format: "mp4", "webm", "mov" ou "gif".
        height: Hauteur voulue en pixels, par exemple 1080 ou 720. 0 = garder.
    """
    p = _p(video)
    if not p.is_file():
        return f"Introuvable : {p}"
    d = p.with_suffix("." + to_format.lstrip("."))
    args = ["-i", str(p)]
    if height:
        args += ["-vf", f"scale=-2:{int(height)}"]
    res = _ffmpeg(*args, str(d), timeout=3600)
    return f"Vidéo convertie : {d}, {d.stat().st_size / 2**20:.0f} Mo" if res == "ok" else res


def concat_videos(files: str, destination: str = "montage.mp4") -> str:
    """Colle plusieurs vidéos bout à bout pour faire un montage brut.

    Args:
        files: Les fichiers dans l'ordre, séparés par des points-virgules.
        destination: Le fichier à créer.
    """
    chemins = [_p(f) for f in str(files).split(";") if f.strip()]
    manquants = [str(c) for c in chemins if not c.is_file()]
    if manquants:
        return "Fichier(s) introuvable(s) : " + ", ".join(manquants)
    liste = config.WORKSPACE / "_concat.txt"
    liste.write_text("\n".join(f"file '{c.as_posix()}'" for c in chemins), encoding="utf-8")
    d = _p(destination)
    res = _ffmpeg("-f", "concat", "-safe", "0", "-i", str(liste), "-c", "copy", str(d), timeout=3600)
    liste.unlink(missing_ok=True)
    return f"{len(chemins)} vidéos assemblées dans {d}" if res == "ok" else res


def make_subtitles(video: str, language: str = "fr") -> str:
    """Génère automatiquement les sous-titres d'une vidéo au format SRT, prêts à être importés.

    Args:
        video: Le fichier vidéo ou audio.
        language: Langue parlée, par exemple "fr" ou "en".
    """
    p = _p(video)
    if not p.is_file():
        return f"Introuvable : {p}"
    try:
        from faster_whisper import WhisperModel

        modele = WhisperModel(config.WHISPER_MODEL, device="cuda", compute_type=config.WHISPER_COMPUTE)
        segments, info = modele.transcribe(str(p), language=language, beam_size=3, vad_filter=True)

        def horo(s: float) -> str:
            h, r = divmod(s, 3600)
            m, sec = divmod(r, 60)
            return f"{int(h):02d}:{int(m):02d}:{int(sec):02d},{int((sec % 1) * 1000):03d}"

        lignes, n = [], 0
        for s in segments:
            n += 1
            lignes.append(f"{n}\n{horo(s.start)} --> {horo(s.end)}\n{s.text.strip()}\n")
        d = p.with_suffix(".srt")
        d.write_text("\n".join(lignes), encoding="utf-8")
        return f"{n} sous-titres générés pour {info.duration / 60:.1f} min de vidéo : {d}"
    except Exception as exc:  # noqa: BLE001
        return f"Erreur : {exc}"


def list_audio_devices() -> str:
    """Liste les micros et les sorties audio disponibles, avec ceux utilisés par défaut."""
    try:
        import sounddevice as sd

        defaut = sd.default.device
        defauts = list(defaut) if isinstance(defaut, (list, tuple)) else [defaut]
        lignes = []
        for i, d in enumerate(sd.query_devices()):
            genre = []
            if d["max_input_channels"]:
                genre.append("micro")
            if d["max_output_channels"]:
                genre.append("sortie")
            marque = " (par défaut)" if i in defauts else ""
            lignes.append(f"{i:3d} {'/'.join(genre):14} {d['name'][:55]}{marque}")
        return "Périphériques audio :\n" + "\n".join(lignes)
    except Exception as exc:  # noqa: BLE001
        return f"Erreur : {exc}"


def test_microphone(seconds: int = 3) -> str:
    """Enregistre quelques secondes avec le micro et dit si le niveau sonore est bon.

    Args:
        seconds: Durée du test.
    """
    try:
        import numpy as np
        import sounddevice as sd

        s = max(1, min(10, int(seconds)))
        audio = sd.rec(int(s * 16000), samplerate=16000, channels=1, dtype="float32")
        sd.wait()
        rms = float(np.sqrt(np.mean(audio ** 2)))
        crete = float(np.max(np.abs(audio)))
        if rms < 0.005:
            avis = "Le micro n'entend presque rien : vérifie qu'il est branché et non coupé."
        elif crete > 0.98:
            avis = "Le son sature : baisse le gain du micro."
        elif rms < 0.02:
            avis = "Niveau faible : monte un peu le gain ou rapproche-toi."
        else:
            avis = "Niveau correct."
        return f"Test de {s} s : niveau moyen {rms:.3f}, crête {crete:.2f}. {avis}"
    except Exception as exc:  # noqa: BLE001
        return f"Erreur : {exc}"


# --------------------------------------------------------------------------
# Design et image de marque
# --------------------------------------------------------------------------

def palette_from_image(path: str, count: int = 6) -> str:
    """Extrait les couleurs principales d'une image pour en faire une palette.

    Args:
        path: L'image de référence.
        count: Nombre de couleurs à extraire.
    """
    try:
        from PIL import Image

        p = _p(path)
        if not p.is_file():
            return f"Introuvable : {p}"
        img = Image.open(p).convert("RGB").resize((160, 160))
        n = max(2, min(12, int(count)))
        reduit = img.quantize(colors=n, method=Image.MEDIANCUT).convert("RGB")
        couleurs = sorted(reduit.getcolors(160 * 160) or [], key=lambda x: -x[0])
        lignes = []
        for nb, (r, g, b) in couleurs[:n]:
            lum = (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255
            ton = "clair" if lum > 0.6 else "sombre" if lum < 0.25 else "moyen"
            lignes.append(f"#{r:02X}{g:02X}{b:02X}  rgb({r}, {g}, {b})  {nb * 100 // (160 * 160)} %  {ton}")
        return f"Palette de {p.name} :\n" + "\n".join(lignes)
    except Exception as exc:  # noqa: BLE001
        return f"Erreur : {exc}"


def check_contrast(color1: str, color2: str) -> str:
    """Vérifie si deux couleurs sont assez contrastées pour que le texte reste lisible.

    Args:
        color1: Couleur du texte, par exemple "#333333".
        color2: Couleur du fond, par exemple "#FFFFFF".
    """
    def lum(c: str) -> float:
        h = c.strip().lstrip("#")
        if len(h) != 6:
            raise ValueError(f"couleur invalide : {c}")
        vals = []
        for i in (0, 2, 4):
            v = int(h[i:i + 2], 16) / 255
            vals.append(v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4)
        return 0.2126 * vals[0] + 0.7152 * vals[1] + 0.0722 * vals[2]

    try:
        l1, l2 = lum(color1), lum(color2)
        ratio = (max(l1, l2) + 0.05) / (min(l1, l2) + 0.05)
        if ratio >= 7:
            avis = "excellent, lisible partout"
        elif ratio >= 4.5:
            avis = "correct pour du texte normal"
        elif ratio >= 3:
            avis = "juste bon pour du gros texte, insuffisant pour du texte normal"
        else:
            avis = "INSUFFISANT, le texte sera difficile à lire"
        return f"Contraste entre {color1} et {color2} : {ratio:.1f} pour 1. C'est {avis}."
    except Exception as exc:  # noqa: BLE001
        return f"Erreur : {exc}"


def resize_for_social(path: str, format_name: str = "youtube miniature") -> str:
    """Redimensionne une image au format exact d'un réseau social ou d'un site.

    Args:
        path: L'image de départ.
        format_name: "youtube miniature", "youtube banniere", "instagram post", "instagram story", "tiktok", "x banniere", "linkedin banniere", "open graph" ou "favicon".
    """
    try:
        from PIL import Image

        p = _p(path)
        if not p.is_file():
            return f"Introuvable : {p}"
        cle = next((k for k in TAILLES if _norm(format_name) in _norm(k) or _norm(k) in _norm(format_name)), None)
        if not cle:
            return "Format inconnu. Choisis parmi : " + ", ".join(TAILLES)
        w, h = TAILLES[cle]
        img = Image.open(p).convert("RGB")
        ratio = max(w / img.width, h / img.height)
        img = img.resize((round(img.width * ratio), round(img.height * ratio)), Image.LANCZOS)
        gauche, haut = (img.width - w) // 2, (img.height - h) // 2
        img = img.crop((gauche, haut, gauche + w, haut + h))
        d = p.with_name(f"{p.stem}_{re.sub(r'[^a-z]+', '-', _norm(cle))}.png")
        img.save(d)
        return f"Image au format {cle}, {w} sur {h} pixels : {d}"
    except Exception as exc:  # noqa: BLE001
        return f"Erreur : {exc}"


def make_favicon(path: str) -> str:
    """Crée le favicon et les icônes d'un site à partir d'un logo.

    Args:
        path: Le logo de départ.
    """
    try:
        from PIL import Image

        p = _p(path)
        if not p.is_file():
            return f"Introuvable : {p}"
        img = Image.open(p).convert("RGBA")
        dossier = p.parent
        faits = []
        for taille in (16, 32, 180, 192, 512):
            d = dossier / f"icone-{taille}.png"
            img.resize((taille, taille), Image.LANCZOS).save(d)
            faits.append(d.name)
        img.save(dossier / "favicon.ico", sizes=[(16, 16), (32, 32), (48, 48)])
        return f"Icônes créées dans {dossier} : favicon.ico et {', '.join(faits)}"
    except Exception as exc:  # noqa: BLE001
        return f"Erreur : {exc}"


def email_signature(name: str, role: str = "", phone: str = "", website: str = "") -> str:
    """Crée une signature de mail en HTML, prête à coller dans les réglages de la messagerie.

    Args:
        name: Nom et prénom.
        role: Fonction ou métier.
        phone: Numéro de téléphone.
        website: Adresse du site.
    """
    couleur = getattr(config, "COULEUR_MARQUE", "#2563eb")
    lignes = ['<div style="font-family:Arial,sans-serif;font-size:14px;color:#333">',
              f'<div style="font-weight:bold;font-size:16px;color:{couleur}">{name}</div>']
    if role:
        lignes.append(f'<div style="color:#666">{role}</div>')
    lignes.append(f'<div style="border-top:2px solid {couleur};margin:8px 0;width:60px"></div>')
    if phone:
        lignes.append(f"<div>{phone}</div>")
    if website:
        lien = website if website.startswith("http") else "https://" + website
        lignes.append(f'<div><a href="{lien}" style="color:{couleur};text-decoration:none">{website}</a></div>')
    lignes.append("</div>")
    d = config.WORKSPACE / "signature_mail.html"
    d.write_text("\n".join(lignes), encoding="utf-8")
    return (f"Signature créée : {d}\nOuvre ce fichier dans le navigateur, copie ce que tu vois, "
            "et colle-le dans les réglages de ta messagerie.")


# --------------------------------------------------------------------------
# Calendrier éditorial
# --------------------------------------------------------------------------

def plan_content(title: str, platform: str = "YouTube", when: str = "", status: str = "idee") -> str:
    """Ajoute une idée ou une publication au calendrier éditorial.

    Args:
        title: Le sujet ou le titre.
        platform: "YouTube", "TikTok", "Instagram", "LinkedIn" ou "blog".
        when: Date prévue au format AAAA-MM-JJ. Vide = sans date.
        status: "idee", "ecrit", "tourne", "monte" ou "publie".
    """
    d = _charge()
    d["calendrier"].append({"date": when or "", "plateforme": platform, "titre": title,
                            "statut": status, "cree": date.today().isoformat()})
    _sauve(d)
    return f"Ajouté au calendrier : « {title} » sur {platform}, statut {status}."


def content_calendar(platform: str = "") -> str:
    """Montre le calendrier éditorial : les idées, ce qui est en cours et ce qui est publié.

    Args:
        platform: Filtrer sur une plateforme. Vide = tout.
    """
    d = _charge()
    items = [x for x in d["calendrier"] if not platform or _norm(platform) in _norm(x["plateforme"])]
    if not items:
        return "Le calendrier éditorial est vide. Ajoute des idées avec plan_content."
    par_statut: dict[str, list] = {}
    for x in items:
        par_statut.setdefault(x["statut"], []).append(x)
    out = [f"{len(items)} contenu(s) :"]
    for statut in ("idee", "ecrit", "tourne", "monte", "publie"):
        lot = par_statut.get(statut, [])
        if lot:
            out.append(f"\n{statut.upper()}, {len(lot)} :")
            out += [f"  {x.get('date') or '  sans date'}  {x['plateforme'][:10]:10} {x['titre'][:60]}" for x in lot]
    return "\n".join(out)


def update_content(title: str, status: str) -> str:
    """Change l'état d'un contenu du calendrier éditorial.

    Args:
        title: Un morceau du titre.
        status: "idee", "ecrit", "tourne", "monte" ou "publie".
    """
    d = _charge()
    for x in d["calendrier"]:
        if _norm(title)[:25] in _norm(x["titre"]):
            ancien = x["statut"]
            x["statut"] = status
            _sauve(d)
            return f"« {x['titre']} » passe de {ancien} à {status}."
    return f"Aucun contenu ne correspond à « {title} »."


def teleprompter(text: str, words_per_minute: int = 130) -> str:
    """Affiche un texte en grand qui défile tout seul, pour lire face caméra.

    Args:
        text: Le texte à lire.
        words_per_minute: Vitesse de défilement, en mots par minute.
    """
    import webbrowser

    mots = len(text.split())
    duree = max(10, round(mots / max(60, int(words_per_minute)) * 60))
    html = f"""<!doctype html><meta charset="utf-8"><title>Téléprompteur</title>
<style>body{{background:#000;color:#fff;font:600 44px/1.6 Arial,sans-serif;margin:0;overflow:hidden}}
#t{{padding:60vh 8vw;white-space:pre-wrap;animation:d {duree}s linear forwards}}
@keyframes d{{from{{transform:translateY(0)}}to{{transform:translateY(-100%)}}}}
#p{{position:fixed;top:0;left:0;right:0;height:4px;background:#4fd8ff;z-index:2}}
body:hover #t{{animation-play-state:paused}}</style>
<div id="p"></div><div id="t">{text}</div>"""
    d = config.WORKSPACE / "teleprompteur.html"
    d.write_text(html, encoding="utf-8")
    webbrowser.open(d.as_uri())
    return (f"Téléprompteur ouvert : {mots} mots, environ {duree // 60} min {duree % 60} s de lecture. "
            "Passe la souris dessus pour mettre en pause.")


# --------------------------------------------------------------------------
# Jeu et stream
# --------------------------------------------------------------------------

def game_mode(on: bool = True) -> str:
    """Prépare l'ordinateur pour jouer : coupe les notifications et repère les applications gourmandes.

    Args:
        on: True pour activer le mode jeu, False pour tout remettre comme avant.
    """
    try:
        import outils_systeme as S

        if not on:
            S.do_not_disturb(False)
            return "Mode jeu désactivé, les notifications reviennent."
        gourmands = ["chrome", "msedge", "opera", "LM Studio", "Discord", "Spotify", "obs64"]
        trouves = []
        try:
            import psutil

            for p in psutil.process_iter(["name", "memory_info"]):
                nom = p.info.get("name") or ""
                mo = (p.info["memory_info"].rss / 2**20) if p.info.get("memory_info") else 0
                if any(_norm(g) in _norm(nom) for g in gourmands) and mo > 300:
                    trouves.append(f"{nom} ({mo:.0f} Mo)")
        except Exception:  # noqa: BLE001
            pass
        S.do_not_disturb(True)
        libre = ", ".join(sorted(set(trouves))[:8]) or "rien de gourmand"
        return (f"Mode jeu : notifications coupées. Applications gourmandes ouvertes : {libre}. "
                "Dis-moi lesquelles fermer et je le fais avec close_app.")
    except Exception as exc:  # noqa: BLE001
        return f"Erreur : {exc}"


def ping_servers(hosts: str = "8.8.8.8;1.1.1.1") -> str:
    """Mesure la latence vers des serveurs, pour savoir si la connexion est bonne pour jouer.

    Args:
        hosts: Les adresses à tester, séparées par des points-virgules.
    """
    out = []
    for h in [x.strip() for x in hosts.split(";") if x.strip()]:
        try:
            cmd = ["ping", "-n", "4", h] if sys.platform.startswith("win") else ["ping", "-c", "4", h]
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=30, encoding="utf-8",
                               errors="replace", creationflags=NO_WINDOW)
            txt = r.stdout or ""
            moy = re.search(r"Moyenne = (\d+)\s*ms", txt) or re.search(r"= [\d.]+/([\d.]+)/", txt)
            perte = re.search(r"(\d+)%\s*(?:de perte|packet loss)", txt)
            if moy:
                v = float(moy.group(1))
                avis = "excellent" if v < 30 else "correct" if v < 70 else "élevé, ça va laguer"
                out.append(f"{h} : {v:.0f} ms, {avis}" + (f", {perte.group(1)} % de perte" if perte else ""))
            else:
                out.append(f"{h} : pas de réponse")
        except Exception as exc:  # noqa: BLE001
            out.append(f"{h} : {exc}")
    return "\n".join(out)


def clear_shader_cache() -> str:
    """Vide le cache des shaders de la carte graphique, utile quand un jeu saccade ou plante."""
    if not sys.platform.startswith("win"):
        return "Cette opération n'est disponible que sous Windows."
    import os

    total, dossiers = 0, []
    for sous in ("NVIDIA/DXCache", "NVIDIA/GLCache", "D3DSCache", "AMD/DxCache"):
        base = os.environ.get("LOCALAPPDATA")
        if not base:
            continue
        d = Path(base) / sous
        if not d.is_dir():
            continue
        for f in d.rglob("*"):
            if f.is_file():
                try:
                    t = f.stat().st_size
                    f.unlink()
                    total += t
                except Exception:  # noqa: BLE001
                    continue
        dossiers.append(sous)
    if not dossiers:
        return "Aucun cache de shaders trouvé."
    return (f"Cache des shaders vidé, {total / 2**20:.0f} Mo récupérés dans : {', '.join(dossiers)}. "
            "Le premier lancement des jeux sera un peu plus lent, c'est normal.")


def obs_control(action: str = "statut", scene: str = "") -> str:
    """Pilote OBS Studio : enregistrement, changement de scène, direct, clip.

    Args:
        action: "enregistrer", "arreter", "scene", "direct", "clip" ou "statut".
        scene: Nom de la scène, pour l'action "scene".
    """
    hote = getattr(config, "OBS_WEBSOCKET", "")
    if not hote:
        return ("Le pilotage d'OBS n'est pas configuré. Dans OBS, ouvre Outils puis Paramètres du serveur "
                "WebSocket, active-le, puis ajoute OBS_WEBSOCKET = \"ws://127.0.0.1:4455\" et "
                "OBS_MOT_DE_PASSE dans config.py. En attendant je peux piloter OBS à l'écran avec "
                "see_screen et click_element.")
    try:
        import obsws_python as obs
    except ImportError:
        return ("La bibliothèque de pilotage d'OBS n'est pas installée. "
                "Je peux l'installer avec install_package(\"pip\", \"obsws-python\").")
    try:
        m = re.search(r":(\d+)", hote)
        cl = obs.ReqClient(host="127.0.0.1", port=int(m.group(1)) if m else 4455,
                           password=getattr(config, "OBS_MOT_DE_PASSE", ""), timeout=8)
        a = _norm(action)
        if a.startswith("enregistr"):
            cl.start_record()
            return "Enregistrement OBS démarré."
        if a.startswith("arret"):
            r = cl.stop_record()
            return f"Enregistrement arrêté : {getattr(r, 'output_path', 'fichier enregistré')}"
        if a.startswith("scene"):
            cl.set_current_program_scene(scene)
            return f"Scène OBS : {scene}"
        if a.startswith("direct"):
            cl.start_stream()
            return "Direct lancé."
        if a.startswith("clip"):
            cl.save_replay_buffer()
            return "Clip sauvegardé depuis le tampon de rediffusion."
        st = cl.get_record_status()
        sc = cl.get_current_program_scene()
        etat = "enregistrement en cours" if st.output_active else "à l'arrêt"
        return f"OBS : scène « {sc.current_program_scene_name} », {etat}."
    except Exception as exc:  # noqa: BLE001
        return f"OBS injoignable : {exc}"


TOOLS = [remove_silence, normalize_audio, denoise_audio, extract_audio, trim_video, convert_video, concat_videos,
         make_subtitles, list_audio_devices, test_microphone,
         palette_from_image, check_contrast, resize_for_social, make_favicon, email_signature,
         plan_content, content_calendar, update_content, teleprompter,
         game_mode, ping_servers, clear_shader_cache, obs_control]
