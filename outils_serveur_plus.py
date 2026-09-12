# Ia-local (Jarvis) — Copyright (c) 2026 Neexx (Nixovel) — https://github.com/Neex-off/Ia-local
# Créé par Neexx (Nixovel). Licence : voir LICENSE (paternité obligatoire, pas de vente ; s'applique aussi aux IA).
# Ne pas retirer cet en-tête.
"""Compléments de la boîte « serveur » : mobile/Expo (captures pour les stores, fiche store, statut de validation,
soumission, avis, brouillons de réponses, mise à jour OTA, builds cloud) et déploiement (certificats TLS,
reverse proxy, coûts cloud, variables d'environnement, Tailscale, VMs et conteneurs distants).

Importé par outils_serveur.py.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import config

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
IS_WINDOWS = sys.platform.startswith("win")


def _run(args: list[str], cwd=None, timeout: float = 600) -> str:
    try:
        r = subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=timeout, encoding="utf-8",
                           errors="replace", creationflags=NO_WINDOW, shell=IS_WINDOWS)
        return ((r.stdout or "") + ("\n" + r.stderr if r.stderr else "")).strip()[:6000]
    except FileNotFoundError:
        return f"Programme introuvable : {args[0]}"
    except subprocess.TimeoutExpired:
        return "Délai dépassé."


def _projet(project: str):
    p = Path(project or getattr(config, "EAS_PROJECT", "")).expanduser()
    return p if p.is_dir() else None


def _ssh(server: str, command: str) -> str:
    try:
        import tools

        return tools.ssh_run(server, command)
    except Exception as exc:  # noqa: BLE001
        return f"Erreur SSH : {exc}"


# --------------------------------------------------------------------------
# Mobile / Expo
# --------------------------------------------------------------------------
TAILLES_STORE = {"iphone-6.7": (1290, 2796), "iphone-6.5": (1284, 2778), "ipad-12.9": (2048, 2732),
                 "android-phone": (1080, 1920), "android-tablet": (1600, 2560)}


def store_screenshots(source_folder: str, output_folder: str = "", sizes: str = "iphone-6.7,android-phone") -> str:
    """Prépare les captures d'écran pour les stores aux bonnes tailles (redimensionne et complète le fond) depuis des captures d'émulateur ou de téléphone.

    Args:
        source_folder: Dossier des captures brutes.
        output_folder: Dossier de sortie (vide = workspace/store).
        sizes: Tailles voulues parmi iphone-6.7, iphone-6.5, ipad-12.9, android-phone, android-tablet.
    """
    from PIL import Image

    out = Path(output_folder) if output_folder else config.WORKSPACE / "store"
    out.mkdir(parents=True, exist_ok=True)
    src = Path(source_folder).expanduser()
    if not src.is_dir():
        return "Donne un dossier de captures (phone_screenshot de la boîte vie en produit depuis le téléphone branché)."
    n = 0
    for img_path in sorted(src.iterdir()):
        if img_path.suffix.lower() not in (".png", ".jpg", ".jpeg"):
            continue
        img = Image.open(img_path).convert("RGB")
        for t in sizes.split(","):
            w, h = TAILLES_STORE.get(t.strip(), (0, 0))
            if not w:
                continue
            ratio = min(w / img.width, h / img.height)
            petit = img.resize((int(img.width * ratio), int(img.height * ratio)), Image.LANCZOS)
            fond = Image.new("RGB", (w, h), img.getpixel((2, 2)))
            fond.paste(petit, ((w - petit.width) // 2, (h - petit.height) // 2))
            fond.save(out / f"{img_path.stem}-{t.strip()}.png")
            n += 1
    return f"{n} captures store écrites dans {out}."


def store_listing(app_name: str, description: str, output: str = "") -> str:
    """Prépare la fiche store (titre, sous-titre, descriptions, mots-clés, notes de version) en Markdown, que tu complètes ensuite.

    Args:
        app_name: Nom de l'application.
        description: Ce que fait l'app, pour qui, ses 3 à 5 points forts (en quelques phrases).
        output: Fichier de sortie (vide = workspace/fiche-store-<nom>.md).
    """
    slug = re.sub(r"\W+", "-", app_name).lower()
    out = Path(output) if output else config.WORKSPACE / f"fiche-store-{slug}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    gabarit = (f"# Fiche store — {app_name}\n\n## Titre (30 car. max)\n{app_name}\n\n## Sous-titre (30 car. max)\n_à rédiger_\n\n"
               f"## Description courte (80 car., Play Store)\n_à rédiger_\n\n## Description longue (4000 car. max)\n{description}\n\n"
               "## Mots-clés (100 car., App Store, séparés par des virgules)\n_à rédiger_\n\n## Notes de version\n- Première version\n\n"
               "## Catégorie\n_à choisir_\n\n## Classification d'âge\n_à choisir_\n")
    out.write_text(gabarit, encoding="utf-8")
    return (f"Gabarit écrit dans {out}. Rédige maintenant chaque section à partir de : « {description[:200]} » "
            "(titre accrocheur, sous-titre bénéfice, description longue en paragraphes courts, mots-clés sans répéter le nom), puis écris-la avec write_file.")


def store_status(project: str = "") -> str:
    """Statut des builds et soumissions App Store / Play Console via EAS (Expo) : dernières builds, soumissions et leur état.

    Args:
        project: Dossier du projet Expo (vide = config.EAS_PROJECT).
    """
    p = _projet(project)
    if not p:
        return "Donne le dossier du projet Expo (ou EAS_PROJECT dans config.py)."
    if not (shutil.which("eas") or shutil.which("eas.cmd")):
        return "eas-cli manque : npm install -g eas-cli, puis eas login."
    builds = _run(["eas", "build:list", "--limit", "5", "--non-interactive", "--json"], cwd=p)
    lignes = []
    try:
        b = json.loads(builds[builds.index("["):])
        lignes += [f"- build {x.get('platform')} {x.get('appVersion')} ({x.get('buildProfile')}) : {x.get('status')} — {x.get('createdAt', '')[:16]}" for x in b]
    except Exception:  # noqa: BLE001
        lignes.append(builds[:1500])
    subs = _run(["eas", "submit:list", "--limit", "5", "--non-interactive", "--json"], cwd=p)
    try:
        s = json.loads(subs[subs.index("["):])
        lignes += [f"- soumission {x.get('platform')} : {x.get('status')} — {x.get('createdAt', '')[:16]}" for x in s]
    except Exception:  # noqa: BLE001
        pass
    return "\n".join(lignes) + "\nPour l'état de validation détaillé (En révision, Approuvé, Refusé) : open_url sur App Store Connect ou la Play Console, puis see_screen."


def submit_build(project: str = "", platform: str = "android", profile: str = "production") -> str:
    """Soumet la dernière build EAS au store (Play Console ou App Store Connect).

    Args:
        project: Dossier du projet Expo.
        platform: "android" ou "ios".
        profile: Profil de soumission eas.json.
    """
    p = _projet(project)
    if not p:
        return "Donne le dossier du projet Expo."
    return _run(["eas", "submit", "--platform", platform, "--profile", profile, "--latest", "--non-interactive"], cwd=p, timeout=1800)[-2500:]


def store_reviews(app_id: str, platform: str = "android", count: int = 20) -> str:
    """Lit les avis publics d'une app sur le Play Store (page publique) ou l'App Store (flux RSS), avec la note et le texte.

    Args:
        app_id: Identifiant (Android : com.exemple.app ; iOS : id123456789).
        platform: "android" ou "ios".
        count: Nombre d'avis.
    """
    import requests

    if platform == "ios":
        num = re.sub(r"\D", "", app_id)
        try:
            r = requests.get(f"https://itunes.apple.com/fr/rss/customerreviews/id={num}/sortBy=mostRecent/json", timeout=20).json()
            entries = r.get("feed", {}).get("entry", [])
            avis = [f"- {e['im:rating']['label']}/5 « {e['title']['label']} » : {e['content']['label'][:200]}" for e in entries[:count] if "im:rating" in e]
            return "\n".join(avis) or "Aucun avis."
        except Exception as exc:  # noqa: BLE001
            return f"Erreur : {exc}"
    try:
        html = requests.get(f"https://play.google.com/store/apps/details?id={app_id}&hl=fr&gl=FR", timeout=20,
                            headers={"User-Agent": "Mozilla/5.0"}).text
        note = re.search(r'"ratingValue":\s*"?([\d.]+)', html) or re.search(r'aria-label="Note\s*:?\s*([\d,.]+)', html)
        textes = re.findall(r'"([^"]{40,300})",\s*(?:null|\d),\s*\[\s*"[^"]*",\s*\d+', html)
        out = [f"Note globale : {note.group(1)}" if note else "Note non lue"]
        out += [f"- {t}" for t in textes[:count]]
        out.append("Avis complets et crashs : Play Console > Qualité (open_url puis see_screen).")
        return "\n".join(out)
    except Exception as exc:  # noqa: BLE001
        return f"Erreur : {exc}"


def review_reply_drafts(reviews: str, tone: str = "chaleureux et concis") -> str:
    """Prépare des brouillons de réponses aux avis utilisateurs (un par avis) ; tu les rédiges ensuite.

    Args:
        reviews: Les avis, un par ligne (avec la note si possible).
        tone: Ton voulu.
    """
    lignes = [l.strip("- ") for l in reviews.splitlines() if l.strip()]
    if not lignes:
        return "Donne les avis."
    return (f"{len(lignes)} avis. Pour chacun, rédige une réponse {tone} de 2 à 4 phrases : remercier, reprendre le point précis, "
            "dire ce qui est fait ou prévu (sans promettre de date), inviter à écrire au support si problème. Signe « L'équipe ». Avis :\n"
            + "\n".join(f"{i}. {l}" for i, l in enumerate(lignes, start=1)))


def ota_update(project: str = "", message: str = "", branch: str = "production") -> str:
    """Publie une mise à jour OTA (EAS Update) : le JavaScript est mis à jour chez les utilisateurs sans passer par les stores.

    Args:
        project: Dossier du projet Expo.
        message: Message de la mise à jour.
        branch: Branche EAS Update.
    """
    p = _projet(project)
    if not p:
        return "Donne le dossier du projet Expo."
    return _run(["eas", "update", "--branch", branch, "--message", message or f"maj {datetime.now():%d/%m %H:%M}", "--non-interactive"], cwd=p, timeout=1800)[-2000:]


def cloud_builds(project: str = "", action: str = "status", platform: str = "all", profile: str = "production") -> str:
    """Builds cloud EAS : statut des dernières, ou lancer une build.

    Args:
        project: Dossier du projet Expo.
        action: "status" ou "start".
        platform: "android", "ios" ou "all".
        profile: Profil eas.json.
    """
    p = _projet(project)
    if not p:
        return "Donne le dossier du projet Expo."
    if action == "start":
        return _run(["eas", "build", "--platform", platform, "--profile", profile, "--non-interactive", "--no-wait"], cwd=p, timeout=600)[-2000:]
    return store_status(str(p))


# --------------------------------------------------------------------------
# Serveurs
# --------------------------------------------------------------------------

def renew_tls(server: str, domain: str = "", dry_run: bool = True) -> str:
    """Renouvelle les certificats TLS (certbot) sur un serveur par SSH, ou affiche leur état.

    Args:
        server: Nom du serveur (list_servers) ou user@hote.
        domain: Domaine précis (vide = tous).
        dry_run: True = simulation certbot, False = renouvellement réel.
    """
    etat = _ssh(server, "sudo certbot certificates 2>/dev/null | grep -E 'Certificate Name|Expiry' || echo 'certbot absent'")
    cmd = ("sudo certbot renew" + ("" if dry_run else " --force-renewal") + (f" --cert-name {domain}" if domain else "")
           + (" --dry-run" if dry_run else "") + " 2>&1 | tail -15")
    return f"État :\n{etat}\n\n{'Simulation' if dry_run else 'Renouvellement'} :\n{_ssh(server, cmd)}"


def reverse_proxy(server: str, domain: str, target_port: int, kind: str = "nginx", apply: bool = False) -> str:
    """Configure un reverse proxy (nginx ou Caddy) : génère la configuration pour un domaine vers un port local, et l'installe si apply=True.

    Args:
        server: Serveur SSH.
        domain: Domaine (ex. app.exemple.fr).
        target_port: Port de l'application (ex. 3000).
        kind: "nginx" ou "caddy".
        apply: Écrire la config sur le serveur et recharger.
    """
    if kind == "caddy":
        conf = f"{domain} {{\n    reverse_proxy 127.0.0.1:{target_port}\n}}\n"
        cmd = f"printf '%s' '{conf}' | sudo tee -a /etc/caddy/Caddyfile > /dev/null && sudo systemctl reload caddy && echo ok"
    else:
        conf = (f"server {{\n    listen 80;\n    server_name {domain};\n    location / {{\n        proxy_pass http://127.0.0.1:{target_port};\n"
                "        proxy_http_version 1.1;\n        proxy_set_header Upgrade $http_upgrade;\n        proxy_set_header Connection 'upgrade';\n"
                "        proxy_set_header Host $host;\n        proxy_set_header X-Real-IP $remote_addr;\n"
                "        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;\n        proxy_set_header X-Forwarded-Proto $scheme;\n    }\n}\n")
        chemin = f"/etc/nginx/sites-available/{domain}"
        cmd = (f"printf '%s' '{conf}' | sudo tee {chemin} > /dev/null && sudo ln -sf {chemin} /etc/nginx/sites-enabled/{domain} && "
               "sudo nginx -t && sudo systemctl reload nginx && echo ok")
    if not apply:
        return (f"Configuration {kind} pour {domain} -> :{target_port} :\n\n{conf}\nRappelle avec apply=True pour l'installer sur {server}, "
                f"puis certbot --nginx -d {domain} pour le HTTPS (Caddy le fait tout seul).")
    r = _ssh(server, cmd)
    return "Reverse proxy installé et rechargé." if "ok" in r else f"Échec : {r[-500:]}"


def cloud_costs(provider: str = "auto") -> str:
    """Suivi des coûts cloud : AWS (Cost Explorer via aws cli), GCP (gcloud), Azure (az) ; Vercel/Hetzner/OVH par leur page facturation.

    Args:
        provider: "aws", "gcp", "azure", "vercel", "hetzner", "ovh" ou "auto".
    """
    out = []
    debut = datetime.now().replace(day=1).strftime("%Y-%m-%d")
    fin = datetime.now().strftime("%Y-%m-%d")
    if provider in ("aws", "auto") and shutil.which("aws"):
        r = _run(["aws", "ce", "get-cost-and-usage", "--time-period", f"Start={debut},End={fin}", "--granularity", "MONTHLY",
                  "--metrics", "UnblendedCost", "--group-by", "Type=DIMENSION,Key=SERVICE", "--output", "json"], timeout=60)
        try:
            groupes = json.loads(r)["ResultsByTime"][0]["Groups"]
            total = sum(float(g["Metrics"]["UnblendedCost"]["Amount"]) for g in groupes)
            top = sorted(groupes, key=lambda g: -float(g["Metrics"]["UnblendedCost"]["Amount"]))[:6]
            out.append(f"AWS depuis le {debut} : {total:.2f} USD. " + ", ".join(f"{g['Keys'][0]} {float(g['Metrics']['UnblendedCost']['Amount']):.2f}" for g in top))
        except Exception:  # noqa: BLE001
            out.append("AWS : " + r[:300])
    if provider in ("gcp", "auto") and shutil.which("gcloud"):
        out.append("GCP : " + _run(["gcloud", "billing", "accounts", "list", "--format=value(displayName,open)"], timeout=60)[:300] + " (détail : console.cloud.google.com/billing)")
    if provider in ("azure", "auto") and shutil.which("az"):
        out.append("Azure : " + _run(["az", "consumption", "usage", "list", "--start-date", debut, "--end-date", fin, "--query", "[].{c:cost}", "-o", "tsv"], timeout=90)[:300])
    pages = {"vercel": "https://vercel.com/account/billing", "hetzner": "https://console.hetzner.cloud/", "ovh": "https://www.ovh.com/manager/#/dedicated/billing"}
    if provider in pages:
        import webbrowser

        webbrowser.open(pages[provider])
        out.append(f"Page facturation {provider} ouverte : lis le montant à l'écran (see_screen).")
    return "\n".join(out) or "Aucun outil cloud (aws, gcloud, az) trouvé : dis-moi le fournisseur, j'ouvre sa page de facturation."


def deploy_env(target: str, action: str = "list", name: str = "", value: str = "", env_file: str = ".env") -> str:
    """Variables d'environnement de déploiement : Vercel (vercel env), ou fichier .env d'un serveur SSH (lire, ajouter, modifier, supprimer).

    Args:
        target: "vercel", ou le nom d'un serveur SSH (avec env_file = chemin du .env sur le serveur).
        action: "list", "set" ou "remove".
        name: Nom de la variable.
        value: Valeur (pour set).
        env_file: Chemin du .env sur le serveur.
    """
    if target == "vercel":
        if action == "list":
            return _run(["vercel", "env", "ls"], timeout=60)
        if action == "set":
            r = subprocess.run(["vercel", "env", "add", name, "production"], input=value + "\n", capture_output=True, text=True, timeout=60, shell=IS_WINDOWS)
            return (r.stdout + r.stderr)[-500:]
        return _run(["vercel", "env", "rm", name, "production", "-y"], timeout=60)
    if action == "list":
        return _ssh(target, f"sed 's/=.*/=•••/' {env_file} 2>/dev/null || echo 'fichier absent'")
    if action == "set":
        cmd = (f"if grep -q '^{name}=' {env_file} 2>/dev/null; then sed -i 's|^{name}=.*|{name}={value}|' {env_file}; "
               f"else echo '{name}={value}' >> {env_file}; fi && echo ok")
        return "Variable enregistrée (redémarre le service pour l'appliquer)." if "ok" in _ssh(target, cmd) else "Échec."
    return "Supprimée." if "ok" in _ssh(target, f"sed -i '/^{name}=/d' {env_file} && echo ok") else "Échec."


def tailscale(action: str = "status") -> str:
    """Accès distant sécurisé avec Tailscale : état, connecter, déconnecter, liste des machines, installer.

    Args:
        action: "status", "up", "down", "peers" ou "install".
    """
    exe = shutil.which("tailscale") or (r"C:\Program Files\Tailscale\tailscale.exe" if Path(r"C:\Program Files\Tailscale\tailscale.exe").exists() else None)
    if action == "install":
        if exe:
            return "Tailscale est déjà installé."
        if IS_WINDOWS:
            return _run(["winget", "install", "-e", "--id", "tailscale.tailscale", "--accept-source-agreements", "--accept-package-agreements"], timeout=600)
        return "Installe Tailscale : curl -fsSL https://tailscale.com/install.sh | sh"
    if not exe:
        return "Tailscale n'est pas installé : tailscale(\"install\")."
    if action == "peers":
        return _run([exe, "status"], timeout=30)
    if action in ("up", "down"):
        return _run([exe, action], timeout=60) or f"Tailscale {action}."
    return _run([exe, "status", "--self"], timeout=30) + "\n" + _run([exe, "ip", "-4"], timeout=30)


def remote_containers(server: str, action: str = "list", name: str = "", command: str = "") -> str:
    """VMs et conteneurs distants : conteneurs Docker d'un serveur SSH (list, logs, restart, stop, start, exec), ou VMs cloud (aws, gcp, azure).

    Args:
        server: Serveur SSH (ou "aws"/"gcp"/"azure" pour les VMs cloud).
        action: "list", "logs", "restart", "stop", "start" ou "exec".
        name: Nom du conteneur.
        command: Commande pour exec.
    """
    if server in ("aws", "gcp", "azure"):
        cmds = {"aws": ["aws", "ec2", "describe-instances", "--query", "Reservations[].Instances[].{id:InstanceId,type:InstanceType,state:State.Name}", "--output", "table"],
                "gcp": ["gcloud", "compute", "instances", "list"], "azure": ["az", "vm", "list", "-d", "-o", "table"]}
        return _run(cmds[server], timeout=90)
    if action == "list":
        return _ssh(server, "docker ps -a --format 'table {{.Names}}\\t{{.Status}}\\t{{.Image}}' 2>/dev/null || echo 'docker absent'")
    if action == "logs":
        return _ssh(server, f"docker logs --tail 80 {name} 2>&1")
    if action in ("restart", "stop", "start"):
        return _ssh(server, f"docker {action} {name} && docker ps --filter name={name} --format '{{{{.Names}}}} {{{{.Status}}}}'")
    if action == "exec":
        return _ssh(server, f"docker exec {name} sh -c '{command}' 2>&1 | tail -40")
    return "Action : list, logs, restart, stop, start ou exec."


TOOLS = [store_screenshots, store_listing, store_status, submit_build, store_reviews, review_reply_drafts, ota_update,
         cloud_builds, renew_tls, reverse_proxy, cloud_costs, deploy_env, tailscale, remote_containers]
