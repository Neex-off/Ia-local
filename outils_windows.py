# Ia-local (Jarvis) — Copyright (c) 2026 Neexx (Nixovel) — https://github.com/Neex-off/Ia-local
# Créé par Neexx (Nixovel). Licence : voir LICENSE (paternité obligatoire, pas de vente ; s'applique aussi aux IA).
# Ne pas retirer cet en-tête.
"""Boîte à outils « windows » : registre, fonctionnalités, tâches planifiées, alimentation, affichage, pilotes,
Windows Update, restauration, réparation, disques, réseau avancé (Wi-Fi, VPN, DNS, proxy, hosts, pare-feu,
Wake-on-LAN), matériel (écrans externes, RGB, ventilateurs, consommation, surchauffe).

Chargée à la demande par tools.open_toolbox("windows"). Les actions qui exigent l'administrateur passent par
run_elevated, qui ouvre la demande UAC habituelle de Windows.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import socket
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


def _ps(command: str, timeout: float = 60) -> str:
    r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", command],
                       capture_output=True, text=True, timeout=timeout, encoding="utf-8",
                       errors="replace", creationflags=NO_WINDOW)
    return ((r.stdout or "").strip() or (r.stderr or "").strip())[:6000]


def _win() -> str | None:
    return None if IS_WINDOWS else "Disponible seulement sous Windows."


def _json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return default


def _save(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def run_elevated(command: str, wait: bool = True) -> str:
    """Exécute une commande PowerShell en administrateur (Windows affiche sa demande UAC ; l'utilisateur doit accepter).

    Args:
        command: La commande PowerShell.
        wait: Attendre la fin (jusqu'à 10 minutes) et renvoyer la sortie.
    """
    if (e := _win()):
        return e
    sortie = config.WORKSPACE / "eleve.log"
    script_ps = config.WORKSPACE / "eleve.ps1"
    sortie.parent.mkdir(parents=True, exist_ok=True)
    sortie.unlink(missing_ok=True)
    script_ps.write_text(f"try {{ {command} }} catch {{ $_ | Out-String }} *> \"{sortie}\"\n", encoding="utf-8-sig")
    lanceur = (f"Start-Process powershell -Verb RunAs {'-Wait' if wait else ''} -WindowStyle Hidden -ArgumentList "
               f"'-NoProfile -ExecutionPolicy Bypass -File \"{script_ps}\"'")
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-Command", lanceur], capture_output=True, text=True,
                           timeout=600 if wait else 20, encoding="utf-8", errors="replace", creationflags=NO_WINDOW)
    except subprocess.TimeoutExpired:
        return "La commande administrateur n'a pas fini en 10 minutes."
    err = (r.stderr or "").lower()
    if "annul" in err or "cancel" in err:
        return "L'utilisateur a refusé la demande d'administrateur (UAC)."
    if not wait:
        return "Lancée en administrateur (résultat plus tard dans workspace/eleve.log)."
    time.sleep(0.5)
    try:
        return sortie.read_text(encoding="utf-8", errors="replace")[-4000:].strip() or "Terminé (aucune sortie)."
    except Exception:  # noqa: BLE001
        return "Terminé, mais aucune sortie n'a été écrite (UAC refusé ?)."


# --------------------------------------------------------------------------
# Registre, fonctionnalités, tâches, alimentation, applications par défaut, affichage
# --------------------------------------------------------------------------

def registry_read(key: str, name: str = "") -> str:
    """Lit une clé du registre Windows (toutes ses valeurs, ou une seule).

    Args:
        key: Chemin complet, ex. "HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\Advanced".
        name: Nom d'une valeur précise (vide = toutes).
    """
    if (e := _win()):
        return e
    k = (key.replace("HKEY_CURRENT_USER", "HKCU").replace("HKEY_LOCAL_MACHINE", "HKLM")
         .replace("HKLM\\", "HKLM:\\").replace("HKCU\\", "HKCU:\\"))
    if name:
        return _ps(f"(Get-ItemProperty -Path '{k}' -ErrorAction Stop).'{name}'")
    return _ps(f"Get-ItemProperty -Path '{k}' -ErrorAction Stop | Format-List | Out-String -Width 200")


def registry_write(key: str, name: str, value: str, type: str = "String") -> str:
    """Modifie une valeur du registre, avec sauvegarde automatique (.reg) de la clé avant.

    Args:
        key: Chemin complet de la clé (HKCU\\... ou HKLM\\...).
        name: Nom de la valeur.
        value: Nouvelle valeur.
        type: String, DWord, QWord, ExpandString, MultiString ou Binary.
    """
    if (e := _win()):
        return e
    if "HKLM\\SYSTEM" in key.upper() or "\\SAM" in key.upper() or "\\SECURITY" in key.upper():
        return "Interdit : cette partie du registre est système."
    sauvegarde = config.WORKSPACE / "registre-backups" / f"{datetime.now():%Y%m%d-%H%M%S}.reg"
    sauvegarde.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["reg", "export", key, str(sauvegarde), "/y"], capture_output=True, creationflags=NO_WINDOW)
    k = key.replace("HKLM\\", "HKLM:\\").replace("HKCU\\", "HKCU:\\")
    cmd = f"New-Item -Path '{k}' -Force | Out-Null; Set-ItemProperty -Path '{k}' -Name '{name}' -Value '{value}' -Type {type}; 'ok'"
    r = _ps(cmd)
    if "ok" not in r and key.upper().startswith("HKLM"):
        r = run_elevated(cmd)
    import noyau

    noyau.register_undo(f"registre {key}\\{name}", lambda: _ps(f"reg import '{sauvegarde}'") or "restauré")
    return f"{'Modifié' if 'ok' in r else 'Échec : ' + r[:200]} (sauvegarde {sauvegarde.name})."


def windows_features(action: str = "list", name: str = "") -> str:
    """Fonctionnalités Windows optionnelles (WSL, Hyper-V, Sandbox, .NET 3.5…) : lister, activer, désactiver.

    Args:
        action: "list", "enable" ou "disable".
        name: Nom de la fonctionnalité (ex. "Microsoft-Windows-Subsystem-Linux", "Containers-DisposableClientVM" pour le bac à sable).
    """
    if (e := _win()):
        return e
    if action == "list":
        return run_elevated("Get-WindowsOptionalFeature -Online | Where-Object State -eq Enabled | Select-Object -ExpandProperty FeatureName | Sort-Object")
    verbe = "Enable" if action == "enable" else "Disable"
    return run_elevated(f"{verbe}-WindowsOptionalFeature -Online -FeatureName '{name}' -NoRestart {'-All' if verbe == 'Enable' else ''} | Select-Object RestartNeeded | Format-List")


def scheduled_tasks(action: str = "list", name: str = "", command: str = "", when: str = "DAILY", time_of_day: str = "09:00") -> str:
    """Tâches planifiées Windows : lister, créer, supprimer, lancer.

    Args:
        action: "list", "create", "delete" ou "run".
        name: Nom de la tâche.
        command: Programme ou commande à lancer (pour create).
        when: MINUTE, HOURLY, DAILY, WEEKLY, ONLOGON, ONSTART (pour create).
        time_of_day: Heure HH:MM (pour DAILY/WEEKLY).
    """
    if (e := _win()):
        return e
    if action == "list":
        out = _ps("Get-ScheduledTask | Where-Object {$_.TaskPath -notlike '\\Microsoft\\*'} | Select-Object TaskName,State,TaskPath | Format-Table -AutoSize | Out-String -Width 160")
        return out or "Aucune tâche hors Microsoft."
    if action == "create":
        args = ["schtasks", "/Create", "/TN", name, "/TR", command, "/SC", when, "/F"]
        if when in ("DAILY", "WEEKLY"):
            args += ["/ST", time_of_day]
    elif action == "delete":
        args = ["schtasks", "/Delete", "/TN", name, "/F"]
    elif action == "run":
        args = ["schtasks", "/Run", "/TN", name]
    else:
        return "Action : list, create, delete ou run."
    r = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace", creationflags=NO_WINDOW)
    return (r.stdout or r.stderr).strip()


def power_plan(name: str = "") -> str:
    """Plans d'alimentation : liste (vide) ou active un plan (équilibré, performances, économie, ultime).

    Args:
        name: Vide pour lister, sinon un morceau du nom du plan à activer.
    """
    if (e := _win()):
        return e
    liste = _ps("powercfg /list")
    if not name:
        return liste
    for ligne in liste.splitlines():
        m = re.search(r"([0-9a-f-]{36})\s+\((.+?)\)", ligne, re.I)
        if m and name.lower() in m.group(2).lower():
            _ps(f"powercfg /setactive {m.group(1)}")
            return f"Plan « {m.group(2)} » activé."
    return f"Aucun plan ne contient « {name} »."


def default_apps(kind: str = "") -> str:
    """Ouvre les réglages des applications par défaut (Windows ne permet plus de les changer autrement), puis clique à l'écran.

    Args:
        kind: Vide = page générale ; sinon une extension (".pdf") ou un protocole ("mailto") pour ouvrir la bonne page.
    """
    if (e := _win()):
        return e
    os.startfile("ms-settings:defaultapps")
    return (f"Page des applications par défaut ouverte{' (cherche « ' + kind + ' » dans sa barre de recherche)' if kind else ''} : "
            "regarde l'écran et clique sur le choix voulu.")


def _device(i: int):
    try:
        import win32api

        return win32api.EnumDisplayDevices(None, i).DeviceName
    except Exception:  # noqa: BLE001
        return None


def display_settings(resolution: str = "", refresh_hz: int = 0, monitor: int = 1, hdr: str = "", primary: int = 0) -> str:
    """Affichage : résolution et fréquence d'un écran, HDR, écran principal.

    Args:
        resolution: "1920x1080" par exemple (vide = ne change pas).
        refresh_hz: Fréquence en Hz (0 = ne change pas).
        monitor: Numéro de l'écran (1 = principal).
        hdr: "on" ou "off" (ouvre la page HDR ; Win+Alt+B bascule).
        primary: Numéro de l'écran à rendre principal (0 = ne change pas).
    """
    if (e := _win()):
        return e
    out = []
    if resolution or refresh_hz:
        try:
            import win32api
            import win32con

            devs = [d for i in range(8) if (d := _device(i)) is not None]
            dev = devs[max(0, min(int(monitor) - 1, len(devs) - 1))]
            dm = win32api.EnumDisplaySettings(dev, win32con.ENUM_CURRENT_SETTINGS)
            if resolution:
                w, h = (int(x) for x in resolution.lower().split("x"))
                dm.PelsWidth, dm.PelsHeight = w, h
            if refresh_hz:
                dm.DisplayFrequency = int(refresh_hz)
            dm.Fields = win32con.DM_PELSWIDTH | win32con.DM_PELSHEIGHT | win32con.DM_DISPLAYFREQUENCY
            code = win32api.ChangeDisplaySettingsEx(dev, dm)
            out.append("Résolution/fréquence appliquées." if code == 0 else f"Refusé par Windows (code {code}) : ce mode n'existe peut-être pas.")
        except Exception as exc:  # noqa: BLE001
            out.append(f"Erreur : {exc}")
    if hdr:
        os.startfile("ms-settings:display-hdr")
        out.append(f"Page HDR ouverte ; le raccourci Win+Alt+B bascule le HDR ({hdr}).")
    if primary:
        os.startfile("ms-settings:display")
        out.append("Page Affichage ouverte : sélectionne l'écran et coche « Faire de cet écran l'écran principal ».")
    return " ".join(out) or "Rien demandé."


# --------------------------------------------------------------------------
# Pilotes, Windows Update, restauration, réparation
# --------------------------------------------------------------------------

def update_drivers() -> str:
    """Met à jour les pilotes : rescan du matériel, page des mises à jour facultatives de Windows Update, et l'application NVIDIA/AMD si présente."""
    if (e := _win()):
        return e
    _ps("pnputil /scan-devices")
    os.startfile("ms-settings:windowsupdate-optionalupdates")
    out = ["Rescan du matériel fait et page « Mises à jour facultatives » ouverte : regarde l'écran, coche les pilotes et clique Télécharger et installer."]
    for exe in (r"C:\Program Files\NVIDIA Corporation\NVIDIA app\CEF\NVIDIA app.exe",
                r"C:\Program Files\NVIDIA Corporation\NVIDIA App\NVIDIA App.exe",
                r"C:\Program Files\AMD\CNext\CNext\RadeonSoftware.exe"):
        if Path(exe).exists():
            subprocess.Popen([exe], creationflags=NO_WINDOW)
            out.append(f"Application du fabricant lancée ({Path(exe).stem}) : vérifie son onglet Pilotes à l'écran.")
            break
    return " ".join(out)


def install_windows_updates(scan_only: bool = False) -> str:
    """Windows Update : recherche, télécharge et installe les mises à jour disponibles.

    Args:
        scan_only: True pour seulement chercher.
    """
    if (e := _win()):
        return e
    if scan_only:
        _ps("UsoClient StartScan")
        os.startfile("ms-settings:windowsupdate")
        return "Recherche lancée, page Windows Update ouverte : lis ce qu'elle affiche."
    script = ("if (Get-Module -ListAvailable PSWindowsUpdate) { Import-Module PSWindowsUpdate; "
              "Get-WindowsUpdate -AcceptAll -Install -IgnoreReboot | Out-String } else { "
              "UsoClient StartScan; Start-Sleep 5; UsoClient StartDownload; Start-Sleep 5; UsoClient StartInstall; 'Installation demandée via UsoClient' }")
    r = run_elevated(script)
    os.startfile("ms-settings:windowsupdate")
    return r + "\nPage Windows Update ouverte pour suivre l'avancement à l'écran."


def restore_point_restore(sequence: int = 0) -> str:
    """Points de restauration : liste (0) ou restaure le système à un point (numéro de séquence). Redémarre le PC.

    Args:
        sequence: 0 pour lister, sinon le numéro SequenceNumber du point à restaurer.
    """
    if (e := _win()):
        return e
    if not sequence:
        return run_elevated("Get-ComputerRestorePoint | Select-Object SequenceNumber,CreationTime,Description | Format-Table -AutoSize | Out-String -Width 120")
    return run_elevated(f"Restore-Computer -RestorePoint {int(sequence)} -Confirm:$false", wait=False)


def repair_system(mode: str = "both") -> str:
    """Réparation des fichiers système : sfc /scannow, DISM RestoreHealth, ou les deux. Long (10 à 30 min), en administrateur.

    Args:
        mode: "sfc", "dism" ou "both".
    """
    if (e := _win()):
        return e
    parts = []
    if mode in ("dism", "both"):
        parts.append("DISM /Online /Cleanup-Image /RestoreHealth")
    if mode in ("sfc", "both"):
        parts.append("sfc /scannow")
    return run_elevated("; ".join(parts))


# --------------------------------------------------------------------------
# Disques
# --------------------------------------------------------------------------

def trim_disks(drive: str = "") -> str:
    """TRIM / optimisation des disques (SSD : ReTrim, HDD : défragmentation).

    Args:
        drive: Lettre ("C") ou vide pour tous.
    """
    if (e := _win()):
        return e
    if drive:
        return run_elevated(f"Optimize-Volume -DriveLetter {drive.strip(':')} -ReTrim -Verbose | Out-String")
    return run_elevated("Get-Volume | Where-Object DriveLetter | ForEach-Object { Optimize-Volume -DriveLetter $_.DriveLetter -ReTrim -Verbose } | Out-String")


def eject_usb(drive: str) -> str:
    """Éjecte proprement une clé ou un disque USB.

    Args:
        drive: Lettre du lecteur, ex. "E".
    """
    if (e := _win()):
        return e
    d = drive.strip(":\\ ").upper() + ":"
    r = _ps(f"$sh = New-Object -ComObject Shell.Application; $sh.Namespace(17).ParseName('{d}\\').InvokeVerb('Eject'); 'ok'")
    return f"{d} éjecté : tu peux le retirer." if "ok" in r else f"Échec : {r[:200]}"


def partitions() -> str:
    """Partitions, volumes et état du chiffrement BitLocker."""
    if (e := _win()):
        return e
    vol = _ps("Get-Volume | Where-Object DriveLetter | Select-Object DriveLetter,FileSystemLabel,FileSystem,@{n='Taille(Go)';e={[math]::Round($_.Size/1GB)}},@{n='Libre(Go)';e={[math]::Round($_.SizeRemaining/1GB)}},HealthStatus | Format-Table -AutoSize | Out-String -Width 140")
    parts = _ps("Get-Partition | Select-Object DiskNumber,PartitionNumber,DriveLetter,Type,@{n='Taille(Go)';e={[math]::Round($_.Size/1GB,1)}} | Format-Table -AutoSize | Out-String -Width 140")
    bl = _ps("manage-bde -status 2>&1 | Select-String 'Volume|Protection|Chiffrement|Encryption|Conversion' | Out-String")
    return f"{vol}\n{parts}\nBitLocker :\n{bl or 'état non lisible sans administrateur'}"


# --------------------------------------------------------------------------
# Réseau avancé
# --------------------------------------------------------------------------

def wifi_passwords(profile: str = "") -> str:
    """Mots de passe Wi-Fi enregistrés sur ce PC (tous, ou un réseau précis).

    Args:
        profile: Nom du réseau (vide = tous).
    """
    if (e := _win()):
        return e
    if profile:
        noms = [profile]
    else:
        r = _ps("netsh wlan show profiles")
        noms = [n.strip() for n in re.findall(r":\s+(.+)$", r, re.M) if n.strip()]
    out = []
    for n in noms[:40]:
        r = _ps(f'netsh wlan show profile name="{n}" key=clear')
        m = re.search(r"(?:Contenu de la clé|Key Content)\s*:\s*(.+)", r)
        out.append(f"{n} : {m.group(1).strip() if m else '(pas de clé lisible)'}")
    return "\n".join(out) or "Aucun profil Wi-Fi."


def vpn(action: str = "status", name: str = "") -> str:
    """VPN : état, connecter, déconnecter (connexions VPN de Windows, ou Tailscale s'il est installé).

    Args:
        action: "status", "on" ou "off".
        name: Nom de la connexion VPN (vide = la première).
    """
    if (e := _win()):
        return e
    if action == "status":
        r = _ps("Get-VpnConnection | Select-Object Name,ConnectionStatus,ServerAddress | Format-Table -AutoSize | Out-String")
        ts = _ps("tailscale status | Select-Object -First 3 | Out-String") if shutil.which("tailscale") else ""
        return (r or "Aucune connexion VPN Windows.") + (f"\nTailscale : {ts}" if ts else "")
    if not name:
        name = _ps("(Get-VpnConnection | Select-Object -First 1).Name").strip()
        if not name and shutil.which("tailscale"):
            return _ps(f"tailscale {'up' if action == 'on' else 'down'}") or f"Tailscale {action}."
        if not name:
            return "Aucune connexion VPN configurée dans Windows."
    if action == "on":
        return _ps(f'rasdial "{name}"')
    return _ps(f'rasdial "{name}" /disconnect')


def set_dns(servers: str = "auto", adapter: str = "") -> str:
    """Change les serveurs DNS d'une carte réseau (ex. "1.1.1.1,1.0.0.1" ou "auto").

    Args:
        servers: "auto" ou une liste d'adresses séparées par des virgules.
        adapter: Nom de la carte (vide = celle qui a une connexion).
    """
    if (e := _win()):
        return e
    if not adapter:
        adapter = _ps("(Get-NetAdapter | Where-Object Status -eq Up | Select-Object -First 1).Name").strip()
    if servers.strip().lower() == "auto":
        cmd = f"Set-DnsClientServerAddress -InterfaceAlias '{adapter}' -ResetServerAddresses; 'ok'"
    else:
        lst = ",".join(f"'{s.strip()}'" for s in servers.split(",") if s.strip())
        cmd = f"Set-DnsClientServerAddress -InterfaceAlias '{adapter}' -ServerAddresses @({lst}); 'ok'"
    r = run_elevated(cmd)
    return f"DNS de « {adapter} » : {servers}." if "ok" in r else f"Échec : {r[:200]}"


def set_proxy(action: str = "status", server: str = "") -> str:
    """Proxy système : état, activer avec une adresse (hôte:port), désactiver.

    Args:
        action: "status", "on" ou "off".
        server: "hote:port" pour on.
    """
    if (e := _win()):
        return e
    k = "HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Internet Settings"
    if action == "status":
        return _ps(f"Get-ItemProperty '{k}' | Select-Object ProxyEnable,ProxyServer | Format-List | Out-String")
    if action == "on":
        _ps(f"Set-ItemProperty '{k}' ProxyEnable 1; Set-ItemProperty '{k}' ProxyServer '{server}'")
        return f"Proxy activé : {server}."
    _ps(f"Set-ItemProperty '{k}' ProxyEnable 0")
    return "Proxy désactivé."


HOSTS = Path(r"C:\Windows\System32\drivers\etc\hosts")
_MARQUE = "# jarvis-focus"


def block_sites(action: str = "list", sites: str = "") -> str:
    """Mode focus : bloque des sites via le fichier hosts (ou les débloque).

    Args:
        action: "add", "remove", "clear" ou "list".
        sites: Domaines séparés par des virgules, ex. "youtube.com,twitter.com".
    """
    if (e := _win()):
        return e
    try:
        contenu = HOSTS.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:  # noqa: BLE001
        return f"Impossible de lire hosts : {exc}"
    actuels = re.findall(rf"^0\.0\.0\.0\s+(\S+)\s+{re.escape(_MARQUE)}", contenu, re.M)
    if action == "list":
        return "Sites bloqués : " + (", ".join(sorted({a.removeprefix('www.') for a in actuels})) or "aucun")
    doms = {d.strip().lower().removeprefix("www.") for d in sites.split(",") if d.strip()}
    if action == "add":
        nouveaux = set(actuels)
        for d in doms:
            nouveaux |= {d, "www." + d}
    elif action == "remove":
        nouveaux = {a for a in actuels if a.removeprefix("www.") not in doms}
    else:
        nouveaux = set()
    propre = "\n".join(l for l in contenu.splitlines() if _MARQUE not in l).rstrip()
    bloc = "\n".join(f"0.0.0.0 {d} {_MARQUE}" for d in sorted(nouveaux))
    tmp = config.WORKSPACE / "hosts.tmp"
    tmp.parent.mkdir(parents=True, exist_ok=True)
    tmp.write_text(propre + ("\n" + bloc if bloc else "") + "\n", encoding="utf-8")
    r = run_elevated(f"Copy-Item '{tmp}' '{HOSTS}' -Force; ipconfig /flushdns | Out-Null; 'ok'")
    if "ok" not in r:
        return f"Échec (administrateur refusé ?) : {r[:150]}"
    return f"Sites bloqués maintenant : {', '.join(sorted(d for d in nouveaux if not d.startswith('www.'))) or 'aucun'}. Ferme et rouvre le navigateur."


def firewall_rule(action: str = "list", name: str = "", port: int = 0, direction: str = "in", protocol: str = "TCP", allow: bool = False) -> str:
    """Règles du pare-feu Windows : lister les règles créées ici, ajouter (bloquer ou autoriser un port), supprimer.

    Args:
        action: "list", "add" ou "remove".
        name: Nom de la règle.
        port: Port concerné.
        direction: "in" ou "out".
        protocol: TCP ou UDP.
        allow: True pour autoriser, False pour bloquer.
    """
    if (e := _win()):
        return e
    if action == "list":
        return _ps("Get-NetFirewallRule -DisplayName 'jarvis:*' -ErrorAction SilentlyContinue | Select-Object DisplayName,Direction,Action,Enabled | Format-Table -AutoSize | Out-String") or "Aucune règle créée par Jarvis."
    nom = f"jarvis:{name or (('port ' + str(port)) if port else 'regle')}"
    if action == "add":
        d = "Inbound" if direction == "in" else "Outbound"
        a = "Allow" if allow else "Block"
        r = run_elevated(f"New-NetFirewallRule -DisplayName '{nom}' -Direction {d} -Action {a} -Protocol {protocol} -LocalPort {int(port)} | Out-Null; 'ok'")
        return f"Règle « {nom} » créée : {a} {protocol} {port} {d}." if "ok" in r else f"Échec : {r[:150]}"
    r = run_elevated(f"Remove-NetFirewallRule -DisplayName '{nom}'; 'ok'")
    return f"Règle « {nom} » supprimée." if "ok" in r else f"Échec : {r[:150]}"


def wake_on_lan(mac: str, broadcast: str = "255.255.255.255") -> str:
    """Réveille un PC du réseau par Wake-on-LAN (paquet magique).

    Args:
        mac: Adresse MAC, ex. "AA:BB:CC:DD:EE:FF".
        broadcast: Adresse de diffusion (par défaut tout le réseau).
    """
    m = re.sub(r"[^0-9a-fA-F]", "", mac)
    if len(m) != 12:
        return "Adresse MAC invalide."
    data = bytes.fromhex("FF" * 6 + m * 16)
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    s.sendto(data, (broadcast, 9))
    s.close()
    return f"Paquet magique envoyé à {mac}."


# --------------------------------------------------------------------------
# Matériel
# --------------------------------------------------------------------------

def external_brightness(level: int, monitor: int = 0) -> str:
    """Luminosité des écrans externes via DDC/CI (0 à 100).

    Args:
        level: Luminosité voulue.
        monitor: Numéro de l'écran (0 = tous).
    """
    try:
        from monitorcontrol import get_monitors
    except Exception:  # noqa: BLE001
        return "Le paquet monitorcontrol manque (pip install monitorcontrol)."
    faits = []
    try:
        for i, m in enumerate(get_monitors(), start=1):
            if monitor and i != monitor:
                continue
            with m:
                m.set_luminance(max(0, min(100, int(level))))
            faits.append(str(i))
    except Exception as exc:  # noqa: BLE001
        return f"Erreur DDC/CI : {exc} (l'écran doit accepter DDC/CI, souvent à activer dans son menu)."
    return f"Luminosité {level} % sur les écrans {', '.join(faits) or 'aucun'}."


def rgb_control(color: str = "", mode: str = "") -> str:
    """Éclairage RGB via OpenRGB (couleur hex "ff0000", ou mode "static", "off", "rainbow"…).

    Args:
        color: Couleur hex sans #, ex. "00ff88".
        mode: Mode OpenRGB, ex. "static", "off", "breathing".
    """
    exe = shutil.which("OpenRGB") or next((p for p in (r"C:\Program Files\OpenRGB\OpenRGB.exe",
                                                       str(Path.home() / "AppData/Local/Programs/OpenRGB/OpenRGB.exe"))
                                           if Path(p).exists()), None)
    if not exe:
        return "OpenRGB n'est pas installé (openrgb.org). Sans lui, je ne peux pas piloter les LED."
    args = [exe, "--noautoconnect"]
    if color:
        args += ["-c", color.lstrip("#")]
    if mode:
        args += ["-m", mode]
    r = subprocess.run(args, capture_output=True, text=True, timeout=30, creationflags=NO_WINDOW)
    return "RGB appliqué." if r.returncode == 0 else f"OpenRGB : {(r.stderr or r.stdout)[:200]}"


def fan_curve(profile: int = 0) -> str:
    """Courbes de ventilateurs / undervolt GPU : applique un profil MSI Afterburner (1 à 5) s'il est installé.

    Args:
        profile: Numéro du profil Afterburner (0 = dire ce qui est possible).
    """
    exe = next((p for p in (r"C:\Program Files (x86)\MSI Afterburner\MSIAfterburner.exe",) if Path(p).exists()), None)
    if not exe:
        return ("MSI Afterburner n'est pas installé : c'est lui (ou FanControl) qui gère courbes et undervolt. "
                "Installe-le, crée tes profils, puis fan_curve(1..5) les applique.")
    if not profile:
        return "Afterburner présent : fan_curve(1) à fan_curve(5) appliquent tes profils enregistrés."
    subprocess.Popen([exe, f"-Profile{int(profile)}"], creationflags=NO_WINDOW)
    return f"Profil Afterburner {profile} appliqué (ventilateurs et undervolt de ce profil)."


def power_consumption() -> str:
    """Estimation de la consommation électrique de la machine (GPU mesuré, CPU estimé selon la charge) et son coût."""
    gpu_w = 0.0
    try:
        r = subprocess.run(["nvidia-smi", "--query-gpu=power.draw", "--format=csv,noheader,nounits"],
                           capture_output=True, text=True, timeout=10, creationflags=NO_WINDOW)
        gpu_w = float(r.stdout.strip().split("\n")[0])
    except Exception:  # noqa: BLE001
        pass
    import psutil

    charge = psutil.cpu_percent(interval=1.0) / 100
    tdp = getattr(config, "CPU_TDP_W", 120)
    cpu_w = 15 + charge * (tdp - 15)
    reste = 40  # carte mère, RAM, disques, ventilateurs
    total = gpu_w + cpu_w + reste
    prix = getattr(config, "PRIX_KWH", 0.25)
    return (f"Environ {total:.0f} W en ce moment : GPU {gpu_w:.0f} W (mesuré), CPU {cpu_w:.0f} W (estimé, charge {charge*100:.0f} %), "
            f"reste {reste} W. Soit {total/1000*prix:.3f} € par heure, {total*24/1000*prix:.2f} € par jour s'il reste comme ça.")


_ALERTE = {"thread": None, "stop": threading.Event()}


def _temps() -> tuple[float | None, float | None]:
    g = c = None
    try:
        r = subprocess.run(["nvidia-smi", "--query-gpu=temperature.gpu", "--format=csv,noheader"],
                           capture_output=True, text=True, timeout=10, creationflags=NO_WINDOW)
        g = float(r.stdout.strip().split("\n")[0])
    except Exception:  # noqa: BLE001
        pass
    try:
        r = _ps("(Get-CimInstance -Namespace root/wmi -ClassName MSAcpi_ThermalZoneTemperature -ErrorAction Stop | Select-Object -First 1).CurrentTemperature", timeout=15)
        c = (float(r) / 10) - 273.15
    except Exception:  # noqa: BLE001
        pass
    return g, c


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


def overheat_alert(enable: bool = True, gpu_max: int = 85, cpu_max: int = 90) -> str:
    """Alerte de surchauffe : surveille les températures en fond et prévient (notification + voix) au-delà des seuils.

    Args:
        enable: True pour lancer, False pour arrêter.
        gpu_max: Seuil GPU en °C.
        cpu_max: Seuil CPU en °C.
    """
    if not enable:
        _ALERTE["stop"].set()
        return "Surveillance des températures arrêtée."
    if _ALERTE["thread"] and _ALERTE["thread"].is_alive():
        return "Déjà en cours."
    _ALERTE["stop"].clear()

    def boucle():
        dernier = 0.0
        while not _ALERTE["stop"].is_set():
            g, c = _temps()
            if (g and g >= gpu_max) or (c and c >= cpu_max):
                if time.time() - dernier > 300:
                    dernier = time.time()
                    _prevenir(f"Attention, surchauffe : GPU {g or '?'} degrés, CPU {c or '?'} degrés.")
            _ALERTE["stop"].wait(30)

    _ALERTE["thread"] = threading.Thread(target=boucle, daemon=True)
    _ALERTE["thread"].start()
    return f"Surveillance lancée : alerte au-delà de {gpu_max} °C GPU ou {cpu_max} °C CPU."


TOOLS = [run_elevated, registry_read, registry_write, windows_features, scheduled_tasks, power_plan, default_apps,
         display_settings, update_drivers, install_windows_updates, restore_point_restore, repair_system,
         trim_disks, eject_usb, partitions, wifi_passwords, vpn, set_dns, set_proxy, block_sites, firewall_rule,
         wake_on_lan, external_brightness, rgb_control, fan_curve, power_consumption, overheat_alert]
