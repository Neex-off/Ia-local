# Ia-local (Jarvis) — Copyright (c) 2026 Neexx (Nixovel) — https://github.com/Neex-off/Ia-local
# Créé par Neexx (Nixovel). Licence : voir LICENSE (paternité obligatoire, pas de vente ; s'applique aussi aux IA).
# Ne pas retirer cet en-tête.
"""Boîte à outils « machine » : disques, réseau, matériel, sécurité, entretien de Windows.

Chargée à la demande par tools.open_toolbox("machine").
"""
from __future__ import annotations

import shutil
import socket
import subprocess
import sys
import time

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
IS_WINDOWS = sys.platform.startswith("win")


def _ps(command: str, timeout: float = 60) -> str:
    r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", command],
                       capture_output=True, text=True, timeout=timeout, encoding="utf-8",
                       errors="replace", creationflags=NO_WINDOW)
    return ((r.stdout or "").strip() or (r.stderr or "").strip())[:3000]


def _cmd(args: list[str], timeout: float = 30) -> str:
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=timeout, encoding="utf-8",
                           errors="replace", creationflags=NO_WINDOW)
        return ((r.stdout or "").strip() or (r.stderr or "").strip())[:3000]
    except Exception as exc:  # noqa: BLE001
        return f"Erreur : {exc}"


def _win_only(nom: str) -> str:
    return f"{nom} n'est disponible que sous Windows."


# --------------------------------------------------------------------------
# Disques
# --------------------------------------------------------------------------

def disk_space() -> str:
    """Espace libre et utilisé sur chaque disque, pour savoir où il manque de la place."""
    try:
        import psutil

        lignes = []
        for part in psutil.disk_partitions(all=False):
            try:
                u = psutil.disk_usage(part.mountpoint)
            except OSError:
                continue
            lignes.append(f"{part.device:6} {u.used / 2**30:6.0f} Go utilisés sur {u.total / 2**30:.0f} Go, "
                          f"{u.percent} % plein, {u.free / 2**30:.0f} Go libres")
        return "Disques :\n" + "\n".join(lignes) if lignes else "Aucun disque lisible."
    except Exception as exc:  # noqa: BLE001
        return f"Erreur : {exc}"


def disk_health() -> str:
    """État de santé des disques (SMART) : dit si un disque commence à fatiguer."""
    if not IS_WINDOWS:
        return _win_only("La santé des disques")
    out = _ps("Get-PhysicalDisk | Select-Object FriendlyName,MediaType,HealthStatus,OperationalStatus,"
              "@{n='Go';e={[int]($_.Size/1GB)}} | Format-Table -AutoSize | Out-String -Width 200")
    return f"Santé des disques :\n{out}" if out else "Information SMART indisponible."


def clean_temp() -> str:
    """Vide les fichiers temporaires de Windows pour récupérer de l'espace disque."""
    if not IS_WINDOWS:
        return _win_only("Le nettoyage des fichiers temporaires")
    out = _ps("$a=0; foreach($d in @($env:TEMP,'C:\\Windows\\Temp')){ "
              "Get-ChildItem $d -Recurse -Force -ErrorAction SilentlyContinue | ForEach-Object { "
              "$s=$_.Length; try{ Remove-Item $_.FullName -Force -Recurse -ErrorAction Stop; $a+=$s }catch{} } }; "
              "[math]::Round($a/1MB)", timeout=240)
    return f"Fichiers temporaires nettoyés : environ {out} Mo récupérés."


# --------------------------------------------------------------------------
# Matériel
# --------------------------------------------------------------------------

def hardware_info() -> str:
    """État du matériel en direct : processeur, mémoire, carte graphique, température, batterie."""
    try:
        import psutil

        lignes = [f"Processeur : {psutil.cpu_percent(interval=0.4):.0f} % sur {psutil.cpu_count()} cœurs"]
        m = psutil.virtual_memory()
        lignes.append(f"Mémoire : {m.used / 2**30:.1f} Go sur {m.total / 2**30:.0f} Go, {m.percent} %")
        if shutil.which("nvidia-smi"):
            gpu = _cmd(["nvidia-smi", "--query-gpu=name,memory.used,memory.total,utilization.gpu,temperature.gpu",
                        "--format=csv,noheader"], 15)
            for ligne in gpu.splitlines():
                p = [x.strip() for x in ligne.split(",")]
                if len(p) >= 5:
                    lignes.append(f"Carte graphique : {p[0]}, {p[1]} sur {p[2]}, charge {p[3]}, {p[4]} °C")
        bat = getattr(psutil, "sensors_battery", lambda: None)()
        if bat:
            etat = "en charge" if bat.power_plugged else f"{max(0, bat.secsleft // 60)} min restantes"
            lignes.append(f"Batterie : {bat.percent:.0f} %, {etat}")
        return "\n".join(lignes)
    except Exception as exc:  # noqa: BLE001
        return f"Erreur : {exc}"


def list_drivers(filter: str = "") -> str:
    """Liste les pilotes installés et leur version, pour repérer celui qui est ancien.

    Args:
        filter: Mot-clé, par exemple "nvidia", "audio" ou "réseau". Vide = les principaux.
    """
    if not IS_WINDOWS:
        return _win_only("La liste des pilotes")
    f = f"| Where-Object {{ $_.DeviceName -like '*{filter}*' }}" if filter else ""
    out = _ps("Get-CimInstance Win32_PnPSignedDriver | Select-Object DeviceName,DriverVersion,DriverDate "
              f"{f} | Sort-Object DeviceName | Select-Object -First 40 | Format-Table -AutoSize | Out-String -Width 200")
    return f"Pilotes :\n{out}" if out else "Aucun pilote trouvé."


# --------------------------------------------------------------------------
# Réseau
# --------------------------------------------------------------------------

def network_info() -> str:
    """Adresse IP, état de la connexion, latence vers internet et qualité du Wi-Fi."""
    try:
        lignes = []
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("1.1.1.1", 53))
            lignes.append(f"IP locale : {s.getsockname()[0]}")
            s.close()
        except OSError:
            lignes.append("IP locale : indisponible")
        t0 = time.time()
        try:
            socket.create_connection(("1.1.1.1", 53), timeout=3).close()
            lignes.append(f"Internet : connecté, latence {1000 * (time.time() - t0):.0f} ms")
        except OSError:
            lignes.append("Internet : PAS de connexion")
        if IS_WINDOWS:
            wifi = _ps("netsh wlan show interfaces", 20)
            for mot in ("SSID", "Signal", "Réception", "Transmission"):
                for ligne in wifi.splitlines():
                    if ligne.strip().startswith(mot) and ":" in ligne:
                        lignes.append(ligne.strip())
                        break
        return "\n".join(lignes)
    except Exception as exc:  # noqa: BLE001
        return f"Erreur : {exc}"


def speed_test() -> str:
    """Mesure la vitesse de téléchargement de la connexion internet."""
    try:
        import requests

        url = "https://speed.cloudflare.com/__down?bytes=25000000"
        t0, total = time.time(), 0
        with requests.get(url, stream=True, timeout=30) as r:
            r.raise_for_status()
            for morceau in r.iter_content(chunk_size=262144):
                total += len(morceau)
                if time.time() - t0 > 12:
                    break
        dt = max(0.1, time.time() - t0)
        return f"Débit descendant : {(total * 8 / dt) / 1_000_000:.0f} Mb/s, {total / 2**20:.0f} Mo en {dt:.1f} s"
    except Exception as exc:  # noqa: BLE001
        return f"Erreur de mesure : {exc}"


def open_ports() -> str:
    """Liste les ports réseau ouverts sur l'ordinateur et le programme qui écoute derrière."""
    try:
        import psutil

        lignes = []
        for c in psutil.net_connections(kind="inet"):
            if c.status != "LISTEN":
                continue
            try:
                nom = psutil.Process(c.pid).name() if c.pid else "?"
            except Exception:  # noqa: BLE001
                nom = "?"
            lignes.append(f"port {c.laddr.port:<6} {c.laddr.ip:<16} {nom}")
        lignes = sorted(set(lignes))
        return f"{len(lignes)} port(s) en écoute :\n" + "\n".join(lignes[:40]) if lignes else "Aucun port en écoute."
    except Exception as exc:  # noqa: BLE001
        return f"Erreur : {exc}"


def wifi_list() -> str:
    """Liste les réseaux Wi-Fi à portée avec leur puissance de signal."""
    if not IS_WINDOWS:
        return _win_only("La liste des réseaux Wi-Fi")
    out = _ps("netsh wlan show networks mode=bssid | Select-String 'SSID|Signal'", 30)
    return f"Réseaux Wi-Fi :\n{out}" if out else "Aucun réseau détecté."


def wifi_connect(name: str) -> str:
    """Se connecte à un réseau Wi-Fi déjà enregistré sur l'ordinateur.

    Args:
        name: Nom du réseau (SSID).
    """
    if not IS_WINDOWS:
        return _win_only("La connexion Wi-Fi")
    return _ps(f'netsh wlan connect name="{name}"', 30) or f"Connexion demandée au réseau {name}."


def lan_devices() -> str:
    """Liste les appareils connectés au réseau local : téléphones, consoles, imprimantes."""
    out = _cmd(["arp", "-a"], 25)
    lignes = [l.strip() for l in out.splitlines() if l.strip() and l.strip()[0].isdigit()]
    return f"{len(lignes)} appareil(s) vus sur le réseau :\n" + "\n".join(lignes[:40]) if lignes else out


# --------------------------------------------------------------------------
# Sécurité et entretien
# --------------------------------------------------------------------------

def security_check() -> str:
    """Bilan de sécurité de l'ordinateur : antivirus, protection en temps réel, signatures, pare-feu."""
    if not IS_WINDOWS:
        return _win_only("Le bilan de sécurité")
    av = _ps("$s=Get-MpComputerStatus; \"Antivirus actif : $($s.AntivirusEnabled) | Temps reel : "
             "$($s.RealTimeProtectionEnabled) | Signatures du : $($s.AntivirusSignatureLastUpdated)\"", 60)
    fw = _ps("Get-NetFirewallProfile | Select-Object Name,Enabled | Format-Table -AutoSize | Out-String", 40)
    return f"{av}\n\nPare-feu :\n{fw}"


def antivirus_scan(quick: bool = True) -> str:
    """Lance une analyse antivirus avec Windows Defender.

    Args:
        quick: True pour une analyse rapide de quelques minutes, False pour une analyse complète et longue.
    """
    if not IS_WINDOWS:
        return _win_only("L'analyse antivirus")
    t = "QuickScan" if quick else "FullScan"
    subprocess.Popen(["powershell", "-NoProfile", "-Command", f"Start-MpScan -ScanType {t}"], creationflags=NO_WINDOW)
    return f"Analyse {'rapide' if quick else 'complète'} lancée en arrière-plan."


def startup_programs() -> str:
    """Liste les programmes qui se lancent automatiquement au démarrage de Windows."""
    if not IS_WINDOWS:
        return _win_only("Les programmes au démarrage")
    out = _ps("Get-CimInstance Win32_StartupCommand | Select-Object Name,Command,Location | "
              "Format-Table -AutoSize | Out-String -Width 200", 60)
    return f"Programmes au démarrage :\n{out}"


def list_services(filter: str = "") -> str:
    """Liste les services Windows et leur état.

    Args:
        filter: Mot-clé pour filtrer, par exemple "audio". Vide = les services en cours d'exécution.
    """
    if not IS_WINDOWS:
        return _win_only("Les services Windows")
    cond = f"-Name '*{filter}*'" if filter else "| Where-Object Status -eq 'Running'"
    out = _ps(f"Get-Service {cond} | Select-Object Status,Name,DisplayName | Select-Object -First 40 | "
              "Format-Table -AutoSize | Out-String -Width 200", 60)
    return out or "Aucun service."


def control_service(name: str, action: str = "redemarrer") -> str:
    """Démarre, arrête ou redémarre un service Windows.

    Args:
        name: Nom du service.
        action: "demarrer", "arreter" ou "redemarrer".
    """
    if not IS_WINDOWS:
        return _win_only("Le contrôle des services")
    a = (action or "").lower()
    cmd = {"demarrer": "Start-Service", "démarrer": "Start-Service", "arreter": "Stop-Service",
           "arrêter": "Stop-Service", "redemarrer": "Restart-Service", "redémarrer": "Restart-Service"}.get(a)
    if not cmd:
        return "Action inconnue : utilise demarrer, arreter ou redemarrer."
    out = _ps(f"{cmd} -Name '{name}' -Force -ErrorAction Stop; 'ok'", 60)
    return (f"Service {name} : {action} effectué." if "ok" in out
            else f"Échec : {out[:200]}. Droits administrateur nécessaires ?")


def check_windows_update() -> str:
    """Vérifie les mises à jour de Windows et ouvre la page correspondante à l'écran."""
    if not IS_WINDOWS:
        return _win_only("Windows Update")
    hist = _ps("Get-HotFix | Sort-Object InstalledOn -Descending | Select-Object -First 5 HotFixID,InstalledOn | "
               "Format-Table -AutoSize | Out-String", 60)
    subprocess.Popen(["cmd", "/c", "start", "", "ms-settings:windowsupdate"], creationflags=NO_WINDOW)
    return ("Page Windows Update ouverte : regarde-la avec see_screen pour lire l'état exact avant de conclure.\n"
            f"Dernières mises à jour installées :\n{hist}")


def create_restore_point(name: str = "Avant modification Jarvis") -> str:
    """Crée un point de restauration Windows avant une modification importante du système.

    Args:
        name: Nom du point de restauration.
    """
    if not IS_WINDOWS:
        return _win_only("Les points de restauration")
    out = _ps(f"Checkpoint-Computer -Description '{name}' -RestorePointType MODIFY_SETTINGS -ErrorAction Stop; 'ok'", 240)
    return (f"Point de restauration « {name} » créé." if "ok" in out
            else f"Échec : {out[:200]}. Protection du système désactivée, ou droits administrateur nécessaires.")


TOOLS = [disk_space, disk_health, clean_temp, hardware_info, list_drivers,
         network_info, speed_test, open_ports, wifi_list, wifi_connect, lan_devices,
         security_check, antivirus_scan, startup_programs, list_services, control_service,
         check_windows_update, create_restore_point]
