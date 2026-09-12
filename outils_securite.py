# Ia-local (Jarvis) — Copyright (c) 2026 Neexx (Nixovel) — https://github.com/Neex-off/Ia-local
# Créé par Neexx (Nixovel). Licence : voir LICENSE (paternité obligatoire, pas de vente ; s'applique aussi aux IA).
# Ne pas retirer cet en-tête.
"""Boîte à outils « securite » : cybersécurité défensive de ses propres machines.

Fuites d'e-mail et de mot de passe, analyse d'un fichier suspect, signatures et hachages, connexions et tâches
suspectes, nouveaux appareils sur le Wi-Fi, extensions de navigateur dangereuses, checklist 2FA, mots de passe
forts, échecs de connexion, fichiers pièges, journaux d'événements, coupure du réseau, rapport hebdomadaire,
audit d'un projet. Chargée par tools.open_toolbox("securite").
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import secrets
import string
import subprocess
import sys
import threading
from datetime import datetime
from pathlib import Path

import config

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
IS_WINDOWS = sys.platform.startswith("win")
MEM = config.ROOT / "memoire"


def _ps(command: str, timeout: float = 60) -> str:
    r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", command],
                       capture_output=True, text=True, timeout=timeout, encoding="utf-8",
                       errors="replace", creationflags=NO_WINDOW)
    return ((r.stdout or "").strip() or (r.stderr or "").strip())[:6000]


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
    try:
        import tools

        tools.notify("Jarvis", texte)
    except Exception:  # noqa: BLE001
        pass


# --------------------------------------------------------------------------
# Fuites
# --------------------------------------------------------------------------

def check_email_leak(email: str) -> str:
    """Vérifie si une adresse e-mail apparaît dans des fuites de données connues (Have I Been Pwned).

    Args:
        email: L'adresse à vérifier.
    """
    import requests

    cle = getattr(config, "HIBP_KEY", "")
    if not cle:
        import webbrowser

        webbrowser.open(f"https://haveibeenpwned.com/account/{email}")
        return ("Sans clé HIBP_KEY dans config.py, je ne peux pas interroger l'API : j'ai ouvert la page "
                "haveibeenpwned.com pour cette adresse, lis le résultat à l'écran (see_screen).")
    try:
        r = requests.get(f"https://haveibeenpwned.com/api/v3/breachedaccount/{email}",
                         params={"truncateResponse": "false"},
                         headers={"hibp-api-key": cle, "user-agent": "jarvis-local"}, timeout=20)
    except Exception as exc:  # noqa: BLE001
        return f"Erreur réseau : {exc}"
    if r.status_code == 404:
        return f"Bonne nouvelle : {email} n'apparaît dans aucune fuite connue."
    if r.status_code != 200:
        return f"HIBP a répondu {r.status_code}."
    fuites = r.json()
    lignes = [f"- {f['Name']} ({f['BreachDate']}) : {', '.join(f.get('DataClasses', [])[:5])}" for f in fuites[:15]]
    return (f"{email} apparaît dans {len(fuites)} fuite(s) :\n" + "\n".join(lignes)
            + "\nChange le mot de passe des services concernés et active la 2FA.")


def check_password_leak(password: str) -> str:
    """Vérifie si un mot de passe a déjà fuité, sans jamais l'envoyer (seuls 5 caractères de son empreinte partent). Il n'est ni affiché ni retenu.

    Args:
        password: Le mot de passe à tester.
    """
    import requests

    h = hashlib.sha1(password.encode("utf-8")).hexdigest().upper()
    try:
        r = requests.get(f"https://api.pwnedpasswords.com/range/{h[:5]}", timeout=15, headers={"Add-Padding": "true"})
    except Exception as exc:  # noqa: BLE001
        return f"Erreur réseau : {exc}"
    for ligne in r.text.splitlines():
        suffixe, _, n = ligne.partition(":")
        if suffixe == h[5:] and int(n or 0) > 0:
            return f"[[secret]]Ce mot de passe a fuité {int(n)} fois : ne l'utilise plus nulle part."
    return "[[secret]]Ce mot de passe n'apparaît dans aucune fuite connue."


# --------------------------------------------------------------------------
# Fichiers suspects
# --------------------------------------------------------------------------

def _entropie(data: bytes) -> float:
    if not data:
        return 0.0
    freq = [0] * 256
    for b in data:
        freq[b] += 1
    n = len(data)
    return -sum((c / n) * math.log2(c / n) for c in freq if c)


def file_hash(path: str, algo: str = "sha256") -> str:
    """Empreinte d'un fichier (sha256, sha1, md5), avec vérification VirusTotal si une clé est configurée.

    Args:
        path: Chemin du fichier.
        algo: sha256, sha1 ou md5.
    """
    p = Path(path).expanduser()
    if not p.exists():
        return f"Introuvable : {p}"
    h = hashlib.new(algo)
    with p.open("rb") as f:
        for bloc in iter(lambda: f.read(1 << 20), b""):
            h.update(bloc)
    d = h.hexdigest()
    out = f"{algo} {p.name} : {d}"
    if algo != "sha256":
        return out
    cle = getattr(config, "VIRUSTOTAL_KEY", "")
    if cle:
        import requests

        try:
            r = requests.get(f"https://www.virustotal.com/api/v3/files/{d}", headers={"x-apikey": cle}, timeout=20)
            if r.status_code == 200:
                st = r.json()["data"]["attributes"]["last_analysis_stats"]
                out += (f"\nVirusTotal : {st.get('malicious', 0)} moteurs le jugent malveillant, "
                        f"{st.get('suspicious', 0)} suspect, {st.get('harmless', 0) + st.get('undetected', 0)} rien.")
            elif r.status_code == 404:
                out += "\nVirusTotal : fichier jamais analysé (inconnu, pas forcément sain)."
        except Exception as exc:  # noqa: BLE001
            out += f"\nVirusTotal injoignable : {exc}"
    else:
        out += f"\nVérifier sur VirusTotal : https://www.virustotal.com/gui/file/{d}"
    return out


def verify_signature(path: str) -> str:
    """Vérifie la signature numérique d'un exécutable ou d'un installeur (éditeur, validité).

    Args:
        path: Chemin du .exe / .msi / .dll / .ps1.
    """
    if not IS_WINDOWS:
        return "Disponible seulement sous Windows."
    p = Path(path).expanduser()
    if not p.exists():
        return f"Introuvable : {p}"
    r = _ps(f"$s = Get-AuthenticodeSignature -FilePath '{p}'; \"$($s.Status)|$($s.SignerCertificate.Subject)|$($s.SignerCertificate.NotAfter)\"")
    statut, _, reste = r.partition("|")
    sujet, _, fin = reste.partition("|")
    sens = {"Valid": "signature VALIDE", "NotSigned": "NON SIGNÉ (méfiance pour un installeur)",
            "HashMismatch": "MODIFIÉ après signature : DANGER", "NotTrusted": "signé mais éditeur NON reconnu",
            "UnknownError": "erreur"}.get(statut.strip(), statut)
    editeur = re.search(r"CN=([^,]+)", sujet)
    return f"{p.name} : {sens}" + (f", éditeur « {editeur.group(1)} », certificat jusqu'au {fin[:10]}" if editeur else "")


def analyze_file(path: str) -> str:
    """Analyse un fichier suspect sans l'ouvrir : type réel, origine (téléchargé ?), signature, entropie (chiffré/compressé), scan Defender, empreinte.

    Args:
        path: Chemin du fichier.
    """
    p = Path(path).expanduser()
    if not p.exists():
        return f"Introuvable : {p}"
    data = p.read_bytes()
    out = [f"{p.name} : {len(data)/1024:.0f} Ko, extension {p.suffix or 'aucune'}."]
    magie = data[:4]
    if magie[:2] == b"MZ":
        vrai = "exécutable Windows (PE)"
    elif magie[:2] == b"PK":
        vrai = "zip/office/jar"
    elif magie == b"%PDF":
        vrai = "PDF"
    elif all(32 <= b < 127 or b in (9, 10, 13) for b in data[:200]):
        vrai = "script/texte"
    else:
        vrai = "binaire"
    out.append(f"Contenu réel : {vrai}" + (" — ATTENTION l'extension ne correspond pas"
                                          if vrai.startswith("exécutable") and p.suffix.lower() not in (".exe", ".dll", ".sys", ".scr") else ""))
    if p.suffix.lower() in (".exe", ".scr", ".bat", ".cmd", ".ps1", ".vbs", ".js", ".jar", ".msi", ".lnk", ".hta"):
        out.append("Type à risque : ne double-clique pas dessus tant que ce n'est pas clair.")
    ent = _entropie(data[:1 << 20])
    out.append(f"Entropie {ent:.2f}/8 : " + ("très élevée, contenu chiffré ou compressé (fréquent pour les malwares packés)" if ent > 7.4 else "normale"))
    if IS_WINDOWS:
        zone = _ps(f"Get-Content -Path '{p}' -Stream Zone.Identifier -ErrorAction SilentlyContinue | Out-String")
        if "ZoneId=3" in zone:
            url = re.search(r"HostUrl=(.+)", zone)
            out.append("Téléchargé d'internet" + (f" depuis {url.group(1).strip()[:80]}" if url else "") + ".")
        if vrai.startswith("exécutable") or p.suffix.lower() in (".exe", ".msi", ".dll"):
            out.append(verify_signature(str(p)))
        mp = Path(r"C:\Program Files\Windows Defender\MpCmdRun.exe")
        if mp.exists():
            r = subprocess.run([str(mp), "-Scan", "-ScanType", "3", "-File", str(p), "-DisableRemediation"],
                               capture_output=True, text=True, timeout=180, creationflags=NO_WINDOW)
            out.append("Defender : " + ("RIEN trouvé" if r.returncode == 0 else "MENACE détectée" if r.returncode == 2 else f"code {r.returncode}"))
    out.append(file_hash(str(p)).splitlines()[-1])
    return "\n".join(out)


# --------------------------------------------------------------------------
# Connexions, tâches, événements
# --------------------------------------------------------------------------

def suspicious_connections() -> str:
    """Connexions réseau en cours par programme, en signalant ceux lancés depuis des dossiers inhabituels (Temp, AppData, Téléchargements)."""
    import psutil

    doute = ("\\temp\\", "\\tmp\\", "\\appdata\\local\\temp", "\\downloads\\", "\\public\\", "\\recycle")
    alertes = []
    vus: dict[tuple[str, str], int] = {}
    for c in psutil.net_connections(kind="inet"):
        if not c.raddr or c.status not in ("ESTABLISHED", "SYN_SENT"):
            continue
        try:
            p = psutil.Process(c.pid)
            nom, exe = p.name(), (p.exe() or "").lower()
        except Exception:  # noqa: BLE001
            nom, exe = "?", ""
        cle = (nom, c.raddr.ip)
        vus[cle] = vus.get(cle, 0) + 1
        if any(d in exe for d in doute) or nom == "?":
            alertes.append(f"{nom} ({exe or 'chemin inconnu'}) -> {c.raddr.ip}:{c.raddr.port}")
    lignes = [f"{nom} -> {ip} ({n})" for (nom, ip), n in sorted(vus.items(), key=lambda x: -x[1])[:25]]
    res = "Connexions actives :\n" + "\n".join(lignes)
    if alertes:
        res += "\n\nÀ VÉRIFIER (programme lancé depuis un dossier inhabituel) :\n" + "\n".join(sorted(set(alertes)))
    else:
        res += "\n\nRien d'inhabituel dans l'origine des programmes connectés."
    return res


def suspicious_tasks() -> str:
    """Tâches planifiées suspectes : lancées depuis Temp/AppData, PowerShell encodé ou caché, scripts, téléchargeurs."""
    if not IS_WINDOWS:
        return "Disponible seulement sous Windows."
    import csv
    import io

    r = subprocess.run(["schtasks", "/Query", "/FO", "CSV", "/V"], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", creationflags=NO_WINDOW)
    lignes = list(csv.reader(io.StringIO(r.stdout)))
    if not lignes:
        return "Impossible de lire les tâches."
    entete = lignes[0]
    try:
        i_nom = next(i for i, h in enumerate(entete) if "Nom de la t" in h or h == "TaskName")
        i_cmd = next(i for i, h in enumerate(entete) if "che à exécuter" in h or "Task To Run" in h)
    except StopIteration:
        return "Format de schtasks non reconnu."
    motifs = re.compile(r"(\\temp\\|appdata\\local\\temp|-enc\w*\s|-e\s+[a-z0-9+/=]{20,}|hidden|bypass|downloadstring|"
                        r"invoke-webrequest|\.vbs|\.hta|mshta|wscript|certutil|bitsadmin|\\users\\public)", re.I)
    alertes = []
    for l in lignes[1:]:
        if len(l) <= max(i_nom, i_cmd) or l[i_nom].startswith("\\Microsoft\\"):
            continue
        if motifs.search(l[i_cmd] or ""):
            alertes.append(f"{l[i_nom]} : {l[i_cmd][:120]}")
    return ("Tâches suspectes :\n" + "\n".join(alertes[:30])) if alertes else "Aucune tâche planifiée suspecte."


def failed_logins(hours: int = 24) -> str:
    """Échecs de connexion à cette machine (événement 4625) sur les dernières heures.

    Args:
        hours: Fenêtre en heures.
    """
    if not IS_WINDOWS:
        return "Disponible seulement sous Windows."
    r = _ps(f"Get-WinEvent -FilterHashtable @{{LogName='Security'; Id=4625; StartTime=(Get-Date).AddHours(-{int(hours)})}} "
            f"-ErrorAction SilentlyContinue | Select-Object TimeCreated,@{{n='Compte';e={{$_.Properties[5].Value}}}},"
            f"@{{n='Source';e={{$_.Properties[19].Value}}}} | Format-Table -AutoSize | Out-String", timeout=90)
    if not r.strip():
        return f"Aucun échec de connexion sur {hours} h (ou le journal Sécurité exige l'administrateur)."
    n = max(r.count("\n") - 3, 1)
    return f"{n} échec(s) de connexion sur {hours} h :\n{r[:2500]}"


def event_log_analysis(hours: int = 24, log: str = "System") -> str:
    """Analyse un journal d'événements Windows (System, Application, Security) : erreurs et critiques par source, les dernières en détail.

    Args:
        hours: Fenêtre en heures.
        log: Nom du journal.
    """
    if not IS_WINDOWS:
        return "Disponible seulement sous Windows."
    filtre = f"@{{LogName='{log}'; Level=1,2; StartTime=(Get-Date).AddHours(-{int(hours)})}}"
    r = _ps(f"Get-WinEvent -FilterHashtable {filtre} -ErrorAction SilentlyContinue | Group-Object ProviderName | "
            f"Sort-Object Count -Descending | Select-Object -First 12 Count,Name | Format-Table -AutoSize | Out-String", timeout=90)
    detail = _ps(f"Get-WinEvent -FilterHashtable {filtre} -MaxEvents 6 -ErrorAction SilentlyContinue | "
                 f"Select-Object TimeCreated,Id,@{{n='Message';e={{$_.Message.Substring(0,[math]::Min(110,$_.Message.Length))}}}} | "
                 f"Format-List | Out-String", timeout=90)
    if not r.strip():
        return f"Aucune erreur ni critique dans « {log} » sur {hours} h."
    return f"Erreurs/critiques dans « {log} » sur {hours} h, par source :\n{r}\nDernières :\n{detail[:2000]}"


# --------------------------------------------------------------------------
# Réseau local, extensions, 2FA, mots de passe, pièges
# --------------------------------------------------------------------------
_WIFI = {"thread": None, "stop": threading.Event()}
CONNUS = MEM / "reseau_connus.json"


def _arp() -> dict[str, str]:
    r = subprocess.run(["arp", "-a"], capture_output=True, text=True, encoding="utf-8", errors="replace", creationflags=NO_WINDOW)
    return {m.group(2).lower(): m.group(1)
            for m in re.finditer(r"(\d+\.\d+\.\d+\.\d+)\s+([0-9a-f-]{17})\s+(?:dynamique|dynamic)", r.stdout, re.I)}


def wifi_watch(action: str = "start") -> str:
    """Alerte quand un nouvel appareil apparaît sur le réseau local (scan toutes les 5 minutes en fond).

    Args:
        action: "start", "stop", "status" ou "trust" (marque les appareils actuels comme connus).
    """
    connus = _json(CONNUS, {})
    if action in ("trust", "start"):
        for mac, ip in _arp().items():
            if action == "trust" or not connus:
                connus.setdefault(mac, {"ip": ip, "vu": datetime.now().isoformat(timespec="minutes"), "nom": ""})
        _save(CONNUS, connus)
    if action == "trust":
        return f"{len(connus)} appareils marqués comme connus."
    if action == "status":
        actif = _WIFI["thread"] is not None and _WIFI["thread"].is_alive()
        return f"{len(connus)} appareils connus ; surveillance {'active' if actif else 'arrêtée'}."
    if action == "stop":
        _WIFI["stop"].set()
        return "Surveillance du réseau arrêtée."
    if _WIFI["thread"] and _WIFI["thread"].is_alive():
        return "Déjà active."
    _WIFI["stop"].clear()

    def boucle():
        while not _WIFI["stop"].is_set():
            base = _json(CONNUS, {})
            for mac, ip in _arp().items():
                if mac not in base:
                    base[mac] = {"ip": ip, "vu": datetime.now().isoformat(timespec="minutes"), "nom": ""}
                    _save(CONNUS, base)
                    _prevenir(f"Nouvel appareil sur le réseau : {ip}, adresse {mac}.")
            _WIFI["stop"].wait(300)

    _WIFI["thread"] = threading.Thread(target=boucle, daemon=True)
    _WIFI["thread"].start()
    return f"Surveillance lancée avec {len(connus)} appareils connus : je préviens dès qu'un inconnu se connecte."


def browser_extensions(browser: str = "all") -> str:
    """Extensions installées dans Chrome, Edge, Brave, Opera GX, avec les permissions dangereuses signalées.

    Args:
        browser: "chrome", "edge", "brave", "opera" ou "all".
    """
    local = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local"))
    roaming = Path(os.environ.get("APPDATA", Path.home() / "AppData/Roaming"))
    bases = {"chrome": local / "Google/Chrome/User Data", "edge": local / "Microsoft/Edge/User Data",
             "brave": local / "BraveSoftware/Brave-Browser/User Data", "opera": roaming / "Opera Software/Opera GX Stable"}
    danger = {"<all_urls>", "webRequest", "webRequestBlocking", "cookies", "nativeMessaging", "debugger", "proxy",
              "history", "clipboardRead", "management", "privacy", "tabs", "scripting", "declarativeNetRequest"}
    out = set()
    for nav, base in bases.items():
        if browser != "all" and nav != browser:
            continue
        if not base.exists():
            continue
        for manifest in list(base.glob("*/Extensions/*/*/manifest.json"))[:200]:
            try:
                m = json.loads(manifest.read_text(encoding="utf-8", errors="replace"))
            except Exception:  # noqa: BLE001
                continue
            nom = m.get("name", "?")
            if nom.startswith("__MSG_"):
                cle = nom[6:-2]
                for loc in ("fr", "en", "en_US"):
                    f = manifest.parent / "_locales" / loc / "messages.json"
                    if f.exists():
                        try:
                            nom = json.loads(f.read_text(encoding="utf-8", errors="replace")).get(cle, {}).get("message", nom)
                            break
                        except Exception:  # noqa: BLE001
                            pass
            perms = set(map(str, list(m.get("permissions", [])) + list(m.get("host_permissions", []))))
            risq = perms & danger
            drapeau = " ⚠ " + ", ".join(sorted(risq)) if risq else ""
            out.add(f"[{nav}] {nom} {m.get('version', '')}{drapeau}")
    if not out:
        return "Aucune extension trouvée."
    n_risq = sum(1 for l in out if "⚠" in l)
    return f"{len(out)} extension(s), {n_risq} avec des permissions larges (⚠) :\n" + "\n".join(sorted(out))


TWOFA = MEM / "2fa.json"


def twofa_checklist(action: str = "list", service: str = "", done: bool = True) -> str:
    """Checklist des comptes à protéger par double authentification (2FA).

    Args:
        action: "list", "add", "done" (marque activé), "todo" (marque à faire) ou "remove".
        service: Nom du service (Google, GitHub, banque…).
        done: Pour add : déjà activé ou non.
    """
    base = _json(TWOFA, {"Google": False, "Microsoft": False, "GitHub": False, "Banque": False, "Steam": False,
                         "Discord": False, "Epic Games": False, "Amazon": False, "PayPal": False, "Apple": False})
    s = service.strip()
    if action == "add" and s:
        base[s] = bool(done)
    elif action == "done" and s:
        base[s] = True
    elif action == "todo" and s:
        base[s] = False
    elif action == "remove" and s:
        base.pop(s, None)
    _save(TWOFA, base)
    restant = [k for k, v in base.items() if not v]
    fait = [k for k, v in base.items() if v]
    return (f"2FA activée : {', '.join(fait) or 'aucun'}.\nÀ FAIRE : {', '.join(restant) or 'rien, bravo'}."
            + ("\nCommence par la banque, l'e-mail principal et les comptes qui ont une carte enregistrée." if restant else ""))


_MOTS = ("cheval", "table", "orage", "citron", "montagne", "riviere", "lampe", "foret", "nuage", "piano", "fusee",
         "cactus", "marbre", "dragon", "tulipe", "ancre", "violon", "brume", "castor", "safran", "glacier", "tortue",
         "comete", "velours", "chene", "saphir", "lanterne", "meteore", "papyrus", "zebre", "harpe", "dune", "corail")


def strong_password(length: int = 20, words: int = 0) -> str:
    """Génère un mot de passe fort : aléatoire (length caractères) ou une phrase de passe de N mots.

    Args:
        length: Longueur du mot de passe aléatoire.
        words: Si > 0, génère une phrase de N mots à la place (plus facile à retenir).
    """
    if words > 0:
        phrase = "-".join(secrets.choice(_MOTS) for _ in range(max(3, int(words)))) + str(secrets.randbelow(90) + 10)
        return f"[[secret]]{phrase}"
    alphabet = string.ascii_letters + string.digits + "!@#$%&*?-_+="
    while True:
        mdp = "".join(secrets.choice(alphabet) for _ in range(max(12, int(length))))
        if (any(c.islower() for c in mdp) and any(c.isupper() for c in mdp) and any(c.isdigit() for c in mdp)
                and any(c in "!@#$%&*?-_+=" for c in mdp)):
            return f"[[secret]]{mdp}"


CANARY = MEM / "canary.json"


def canary_files(action: str = "check", folder: str = "") -> str:
    """Fichiers pièges (canary) : pose de faux fichiers appétissants (mots de passe.txt…) et détecte s'ils ont été lus, modifiés ou supprimés.

    Args:
        action: "create" ou "check".
        folder: Dossier où poser les pièges (vide = Documents).
    """
    base = _json(CANARY, {})
    if action == "create":
        dossier = Path(folder).expanduser() if folder else Path.home() / "Documents"
        dossier.mkdir(parents=True, exist_ok=True)
        noms = ("mots de passe.txt", "codes banque.txt", "clés API.txt")
        for n in noms:
            p = dossier / n
            contenu = f"# fichier piège Jarvis, ne pas ouvrir\n{secrets.token_hex(16)}\n"
            p.write_text(contenu, encoding="utf-8")
            st = p.stat()
            base[str(p)] = {"sha": hashlib.sha256(contenu.encode()).hexdigest(), "atime": st.st_atime, "mtime": st.st_mtime}
        _save(CANARY, base)
        return f"{len(noms)} fichiers pièges posés dans {dossier}. canary_files(\"check\") dira s'ils ont été touchés."
    if not base:
        return "Aucun piège posé : canary_files(\"create\")."
    alertes = []
    for chemin, info in base.items():
        p = Path(chemin)
        if not p.exists():
            alertes.append(f"{p.name} : SUPPRIMÉ")
            continue
        st = p.stat()
        sha = hashlib.sha256(p.read_bytes()).hexdigest()
        if sha != info["sha"]:
            alertes.append(f"{p.name} : MODIFIÉ")
        elif st.st_atime > info["atime"] + 2:
            alertes.append(f"{p.name} : LU le {datetime.fromtimestamp(st.st_atime):%d/%m %H:%M}")
    return ("ALERTE, pièges touchés :\n" + "\n".join(alertes)) if alertes else "Aucun piège touché."


# --------------------------------------------------------------------------
# Réaction, rapport, audit de projet
# --------------------------------------------------------------------------

def cut_network(restore: bool = False) -> str:
    """Coupe tout le réseau de la machine en cas d'alerte (ou le rétablit avec restore=True). Administrateur requis.

    Args:
        restore: True pour réactiver les cartes réseau.
    """
    from outils_windows import run_elevated

    if restore:
        r = run_elevated("Get-NetAdapter | Where-Object Status -ne 'Up' | Enable-NetAdapter -Confirm:$false; 'ok'")
        return "Réseau rétabli." if "ok" in r else f"Échec : {r[:150]}"
    r = run_elevated("Get-NetAdapter | Where-Object Status -eq 'Up' | Disable-NetAdapter -Confirm:$false; 'ok'")
    return "Réseau coupé : plus aucune connexion. cut_network(restore=True) pour le rétablir." if "ok" in r else f"Échec : {r[:150]}"


def security_report(save: bool = True) -> str:
    """Rapport de sécurité hebdomadaire : antivirus, échecs de connexion, connexions et tâches suspectes, extensions, erreurs système, 2FA, pièges.

    Args:
        save: Enregistrer le rapport dans workspace/rapport-securite-DATE.md.
    """
    parts = [f"# Rapport de sécurité du {datetime.now():%d/%m/%Y}"]
    try:
        import tools

        parts.append("## Antivirus et pare-feu\n" + tools.security_check())
    except Exception as exc:  # noqa: BLE001
        parts.append(f"## Antivirus : {exc}")
    for titre, fn in (("Échecs de connexion (7 jours)", lambda: failed_logins(168)),
                      ("Connexions suspectes", suspicious_connections),
                      ("Tâches planifiées suspectes", suspicious_tasks),
                      ("Extensions de navigateur", browser_extensions),
                      ("Erreurs système (7 jours)", lambda: event_log_analysis(168)),
                      ("2FA", twofa_checklist), ("Fichiers pièges", canary_files)):
        try:
            parts.append(f"## {titre}\n{fn()}")
        except Exception as exc:  # noqa: BLE001
            parts.append(f"## {titre}\nErreur : {exc}")
    rapport = "\n\n".join(parts)
    if save:
        p = config.WORKSPACE / f"rapport-securite-{datetime.now():%Y%m%d}.md"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(rapport, encoding="utf-8")
        rapport += f"\n\nRapport enregistré : {p}"
    return rapport[:6000]


def audit_project_security(path: str) -> str:
    """Audit de sécurité d'un projet : secrets en clair, .env non ignoré, CORS ouvert, debug actif, SQL concaténé, tables sans RLS, dépendances vulnérables.

    Args:
        path: Dossier du projet.
    """
    p = Path(path).expanduser()
    if not p.exists():
        return f"Introuvable : {p}"
    out = []
    try:
        import tools

        out.append("## Secrets\n" + tools.scan_secrets(str(p)))
    except Exception as exc:  # noqa: BLE001
        out.append(f"## Secrets : {exc}")
    gi = p / ".gitignore"
    env = list(p.glob(".env*"))
    if env and (not gi.exists() or ".env" not in gi.read_text(encoding="utf-8", errors="replace")):
        out.append("## .env présent mais PAS dans .gitignore : risque de le pousser sur GitHub.")
    motifs = {"CORS ouvert": re.compile(r"(allow_origins\s*=\s*\[\s*['\"]\*|Access-Control-Allow-Origin['\"]?\s*[:=]\s*['\"]\*)", re.M),
              "Debug actif": re.compile(r"(DEBUG\s*=\s*True|debug\s*=\s*true|app\.run\(.*debug=True)", re.I),
              "SQL concaténé": re.compile(r"(execute\(\s*f['\"]|\+\s*['\"]\s*(WHERE|SELECT|INSERT))", re.I),
              "Clé service_role dans le code": re.compile(r"service_role", re.I),
              "eval/exec sur une entrée": re.compile(r"\b(eval|exec)\(\s*(request|input|req\.)", re.I)}
    trouves: dict[str, list[str]] = {k: [] for k in motifs}
    exts = (".py", ".js", ".ts", ".tsx", ".jsx", ".php", ".go", ".rb", ".java", ".sql", ".toml", ".yaml", ".yml")
    for f in p.rglob("*"):
        if f.suffix.lower() not in exts or "node_modules" in f.parts or ".venv" in f.parts or ".git" in f.parts:
            continue
        try:
            txt = f.read_text(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            continue
        for k, rx in motifs.items():
            if rx.search(txt):
                trouves[k].append(str(f.relative_to(p)))
    for k, fs in trouves.items():
        if fs:
            out.append(f"## {k}\n" + "\n".join(fs[:10]))
    tables, rls = set(), set()
    for f in p.rglob("*.sql"):
        t = f.read_text(encoding="utf-8", errors="replace")
        tables |= set(re.findall(r"create table (?:if not exists )?(?:public\.)?(\w+)", t, re.I))
        rls |= set(re.findall(r"alter table (?:public\.)?(\w+) enable row level security", t, re.I))
    if tables - rls:
        out.append("## Tables sans RLS (policies) : " + ", ".join(sorted(tables - rls)))
    try:
        import tools

        out.append("## Dépendances\n" + tools.audit_deps(str(p)))
    except Exception:  # noqa: BLE001
        pass
    return "\n\n".join(out) if out else "Rien de notable."


TOOLS = [check_email_leak, check_password_leak, analyze_file, verify_signature, file_hash, suspicious_connections,
         suspicious_tasks, failed_logins, event_log_analysis, wifi_watch, browser_extensions, twofa_checklist,
         strong_password, canary_files, cut_network, security_report, audit_project_security]
