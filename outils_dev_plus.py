# Ia-local (Jarvis) — Copyright (c) 2026 Neexx (Nixovel) — https://github.com/Neex-off/Ia-local
# Créé par Neexx (Nixovel). Licence : voir LICENSE (paternité obligatoire, pas de vente ; s'applique aussi aux IA).
# Ne pas retirer cet en-tête.
"""Compléments de la boîte « dev » : versions de Node/Python, WSL, extensions VS Code, ouvrir un projet, variables
d'environnement, clés SSH, serveurs MCP, et Git avancé (init, branches mergées, conflits, pull requests, issues,
changelog, tags/releases, stash, bisect, .gitignore), lecture d'erreurs, revue avant commit, message de commit,
README, suivi de la CI GitHub.

Importé par outils_dev.py. GitHub passe par l'API REST avec config.GITHUB_TOKEN (pas besoin de gh).
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import config

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
IS_WINDOWS = sys.platform.startswith("win")


def _run(args: list[str], cwd=None, timeout: float = 120) -> str:
    try:
        r = subprocess.run(args, cwd=str(cwd) if cwd else None, capture_output=True, text=True, timeout=timeout,
                           encoding="utf-8", errors="replace", creationflags=NO_WINDOW)
        return ((r.stdout or "") + (("\n" + r.stderr) if r.stderr else "")).strip()[:6000]
    except FileNotFoundError:
        return f"Programme introuvable : {args[0]}"
    except subprocess.TimeoutExpired:
        return "Délai dépassé."


def _git(repo: str, *args: str) -> str:
    return _run(["git", *args], cwd=Path(repo).expanduser())


def _remote(repo: str):
    url = _git(repo, "remote", "get-url", "origin")
    m = re.search(r"github\.com[:/]([^/]+)/([^/.\s]+)", url)
    return (m.group(1), m.group(2)) if m else None


def _depot(repo: str):
    if "/" in repo and not Path(repo).expanduser().exists():
        parts = repo.split("/")
        return (parts[0], parts[1]) if len(parts) == 2 else None
    return _remote(repo)


def _gh(method: str, path: str, **payload):
    import requests

    token = getattr(config, "GITHUB_TOKEN", "")
    if not token:
        return None, "Il manque GITHUB_TOKEN dans config.py (github.com > Settings > Developer settings > Personal access tokens)."
    h = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}
    r = requests.request(method, f"https://api.github.com{path}", headers=h, json=payload or None, timeout=30)
    if r.status_code >= 300:
        return None, f"GitHub {r.status_code} : {r.text[:200]}"
    return (r.json() if r.text else {}), ""


# --------------------------------------------------------------------------
# Environnement de dev
# --------------------------------------------------------------------------

def runtime_versions(action: str = "list", tool: str = "python", version: str = "") -> str:
    """Versions de Node et Python : voir ce qui est installé, installer une version (uv / winget / nvm / pyenv).

    Args:
        action: "list" ou "install".
        tool: "python" ou "node".
        version: Version voulue pour install (ex. "3.12", "20").
    """
    if action == "list":
        out = [f"python : {_run(['python', '--version'])}", f"node : {_run(['node', '--version'])}",
               f"npm : {_run(['npm.cmd' if IS_WINDOWS else 'npm', '--version'])}"]
        if shutil.which("py"):
            out.append("versions Python (py -0) :\n" + _run(["py", "-0"]))
        if shutil.which("nvm"):
            out.append("nvm :\n" + _run(["nvm", "list"]))
        if shutil.which("uv"):
            out.append("uv :\n" + _run(["uv", "python", "list", "--only-installed"]))
        return "\n".join(out)
    if tool == "python":
        if shutil.which("uv"):
            return _run(["uv", "python", "install", version], timeout=600)
        if IS_WINDOWS:
            return _run(["winget", "install", "-e", "--id", f"Python.Python.{version}", "--accept-source-agreements", "--accept-package-agreements"], timeout=600)
        return _run(["pyenv", "install", version], timeout=1200)
    if shutil.which("nvm"):
        return _run(["nvm", "install", version], timeout=600) + "\n" + _run(["nvm", "use", version])
    if IS_WINDOWS:
        return (_run(["winget", "install", "-e", "--id", "CoreyButler.NVMforWindows", "--accept-source-agreements", "--accept-package-agreements"], timeout=600)
                + "\nnvm installé : relance un terminal puis runtime_versions(\"install\", \"node\", \"20\").")
    return "Installe nvm (github.com/nvm-sh/nvm) puis réessaie."


def install_wsl(distro: str = "Ubuntu") -> str:
    """Installe une distribution Linux via WSL (Windows Subsystem for Linux), ou liste celles présentes (distro vide).

    Args:
        distro: "Ubuntu", "Debian", "kali-linux"… (vide = lister).
    """
    if not IS_WINDOWS:
        return "WSL n'existe que sous Windows."
    if not distro:
        return _run(["wsl", "--list", "--verbose"]) or "Aucune distribution."
    from outils_windows import run_elevated

    return run_elevated(f"wsl --install -d {distro}") + "\nUn redémarrage peut être demandé ; ensuite la distribution demande un nom d'utilisateur."


def vscode_extensions(action: str = "list", extension: str = "") -> str:
    """Extensions VS Code : lister, installer, désinstaller.

    Args:
        action: "list", "install" ou "uninstall".
        extension: Identifiant (ex. "ms-python.python").
    """
    code = shutil.which("code") or shutil.which("code.cmd")
    if not code:
        return "VS Code (commande « code ») introuvable."
    if action == "list":
        return _run([code, "--list-extensions", "--show-versions"])
    if action == "install":
        return _run([code, "--install-extension", extension, "--force"], timeout=300)
    return _run([code, "--uninstall-extension", extension], timeout=120)


def open_in_editor(path: str, editor: str = "code") -> str:
    """Ouvre un projet ou un fichier dans l'éditeur (VS Code par défaut, ou "cursor", "idea", "pycharm", "notepad++").

    Args:
        path: Dossier ou fichier.
        editor: Nom de l'éditeur.
    """
    p = Path(path).expanduser()
    if not p.exists():
        return f"Introuvable : {p}"
    exe = shutil.which(editor) or shutil.which(editor + ".cmd")
    if not exe:
        if IS_WINDOWS:
            os.startfile(str(p))
        else:
            subprocess.Popen(["xdg-open", str(p)])
        return f"Éditeur « {editor} » introuvable : ouvert avec le programme par défaut."
    subprocess.Popen([exe, str(p)], creationflags=NO_WINDOW)
    return f"{p.name} ouvert dans {editor}."


def env_vars(action: str = "get", name: str = "", value: str = "", scope: str = "user") -> str:
    """Variables d'environnement et PATH : lire, définir, supprimer, ajouter un dossier au PATH (persistant).

    Args:
        action: "get", "set", "remove" ou "path_add".
        name: Nom de la variable (ou dossier pour path_add).
        value: Valeur (pour set).
        scope: "user" ou "machine" (machine = administrateur).
    """
    if action == "get":
        if name:
            v = os.environ.get(name)
            return f"{name} = {v}" if v is not None else f"{name} n'est pas définie."
        return "\n".join(f"{k} = {v[:100]}" for k, v in sorted(os.environ.items()) if "TOKEN" not in k and "KEY" not in k)[:4000]
    if not IS_WINDOWS:
        return "Sous Linux/Mac, ajoute la ligne export dans ~/.bashrc ou ~/.zshrc : je peux le faire avec write_file."
    cible = "User" if scope == "user" else "Machine"
    if action == "set":
        cmd = f"[Environment]::SetEnvironmentVariable('{name}', '{value}', '{cible}'); 'ok'"
    elif action == "remove":
        cmd = f"[Environment]::SetEnvironmentVariable('{name}', $null, '{cible}'); 'ok'"
    elif action == "path_add":
        d = str(Path(name).expanduser())
        cmd = (f"$p = [Environment]::GetEnvironmentVariable('Path', '{cible}'); if ($p -notlike '*{d}*') "
               f"{{ [Environment]::SetEnvironmentVariable('Path', ($p.TrimEnd(';') + ';{d}'), '{cible}') }}; 'ok'")
    else:
        return "Action : get, set, remove ou path_add."
    if cible == "Machine":
        from outils_windows import run_elevated

        r = run_elevated(cmd)
    else:
        r = _run(["powershell", "-NoProfile", "-Command", cmd])
    return f"Fait ({scope}) : relance les terminaux pour le voir." if "ok" in r else f"Échec : {r[:200]}"


def ssh_keygen(name: str = "id_ed25519", comment: str = "", copy_public: bool = True) -> str:
    """Génère une paire de clés SSH (ed25519) et copie la clé publique dans le presse-papiers pour GitHub ou un serveur.

    Args:
        name: Nom du fichier de clé dans ~/.ssh.
        comment: Commentaire (e-mail) dans la clé.
        copy_public: Copier la clé publique dans le presse-papiers.
    """
    d = Path.home() / ".ssh"
    d.mkdir(exist_ok=True)
    k = d / name
    if not k.exists():
        r = _run(["ssh-keygen", "-t", "ed25519", "-f", str(k), "-N", "", "-C", comment or "jarvis"])
        if not k.exists():
            return f"Échec : {r[:300]}"
        prefixe = f"Clé créée : {k}. "
    else:
        prefixe = f"La clé {k} existe déjà. "
    pub = (d / (name + ".pub")).read_text(encoding="utf-8").strip()
    if copy_public:
        import pyperclip

        pyperclip.copy(pub)
    return prefixe + f"Clé publique{' copiée dans le presse-papiers' if copy_public else ''} : {pub[:70]}… À coller dans GitHub > Settings > SSH keys, ou ~/.ssh/authorized_keys du serveur."


def mcp_servers(action: str = "list", name: str = "", command: str = "", args: str = "", target: str = "claude") -> str:
    """Serveurs MCP : lister, ajouter ou retirer un serveur dans la configuration de Claude Desktop ou Claude Code.

    Args:
        action: "list", "add" ou "remove".
        name: Nom du serveur.
        command: Commande (ex. "npx").
        args: Arguments séparés par des espaces (ex. "-y @modelcontextprotocol/server-filesystem C:\\dossier").
        target: "claude" (Claude Desktop) ou "code" (Claude Code, ~/.claude.json).
    """
    if target == "code":
        f = Path.home() / ".claude.json"
    else:
        f = Path(os.environ.get("APPDATA", Path.home() / "AppData/Roaming")) / "Claude" / "claude_desktop_config.json"
    data = {}
    if f.exists():
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            return f"Configuration illisible : {f}"
    servers = data.setdefault("mcpServers", {})
    if action == "list":
        return f"{f} :\n" + ("\n".join(f"- {k} : {v.get('command')} {' '.join(v.get('args', []))}" for k, v in servers.items()) or "aucun serveur")
    if action == "add":
        servers[name] = {"command": command, "args": args.split()}
    elif action == "remove":
        servers.pop(name, None)
    else:
        return "Action : list, add ou remove."
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return f"Serveur « {name} » {'ajouté' if action == 'add' else 'retiré'} dans {f.name}. Redémarre {'Claude Desktop' if target == 'claude' else 'Claude Code'}."


# --------------------------------------------------------------------------
# Git avancé
# --------------------------------------------------------------------------

def git_init(path: str, remote: str = "", first_commit: bool = True) -> str:
    """Crée un dépôt Git dans un dossier (avec .gitignore adapté et premier commit), et le relie à un dépôt distant si donné.

    Args:
        path: Dossier du projet.
        remote: URL du dépôt distant (vide = aucun).
        first_commit: Faire un premier commit.
    """
    p = Path(path).expanduser()
    p.mkdir(parents=True, exist_ok=True)
    out = [_git(p, "init", "-b", "main")]
    if not (p / ".gitignore").exists():
        out.append(gitignore(str(p)))
    if first_commit:
        _git(p, "add", "-A")
        out.append(_git(p, "commit", "-m", "Premier commit"))
    if remote:
        out.append(_git(p, "remote", "add", "origin", remote))
    return "\n".join(o for o in out if o)


def git_prune_branches(repo: str, dry_run: bool = True) -> str:
    """Supprime les branches locales déjà fusionnées dans main/master (et nettoie les branches distantes disparues).

    Args:
        repo: Dossier du dépôt.
        dry_run: True = lister seulement.
    """
    base = "main" if "main" in _git(repo, "branch", "--list", "main") else "master"
    merged = [b.strip().lstrip("* ") for b in _git(repo, "branch", "--merged", base).splitlines()]
    merged = [b for b in merged if b and b not in (base, "main", "master", "develop")]
    if dry_run:
        return f"Branches fusionnées dans {base} : {', '.join(merged) or 'aucune'}. Rappelle avec dry_run=False pour les supprimer."
    out = [_git(repo, "branch", "-d", b) for b in merged]
    out.append(_git(repo, "remote", "prune", "origin"))
    return f"{len(merged)} branche(s) supprimée(s).\n" + "\n".join(out)[-1500:]


def git_conflicts(repo: str, file: str = "", keep: str = "") -> str:
    """Conflits Git : liste les fichiers en conflit et montre les zones ; peut résoudre un fichier en gardant "ours" ou "theirs".

    Args:
        repo: Dossier du dépôt.
        file: Fichier à examiner ou résoudre (vide = liste).
        keep: "ours", "theirs" pour résoudre automatiquement, vide pour montrer les zones à l'utilisateur.
    """
    fichiers = [l for l in _git(repo, "diff", "--name-only", "--diff-filter=U").splitlines() if l.strip()]
    if not file:
        return ("Fichiers en conflit : " + ", ".join(fichiers)) if fichiers else "Aucun conflit."
    p = Path(repo).expanduser() / file
    if keep in ("ours", "theirs"):
        r = _git(repo, "checkout", f"--{keep}", "--", file)
        _git(repo, "add", file)
        return f"{file} résolu en gardant « {keep} ». {r}"
    txt = p.read_text(encoding="utf-8", errors="replace")
    zones = re.findall(r"<<<<<<< .*?\n(.*?)=======\n(.*?)>>>>>>> .*?\n", txt, re.S)
    if not zones:
        return f"{file} ne contient plus de marqueurs de conflit."
    out = [f"Zone {i} :\n--- notre version ---\n{a[:600]}\n--- leur version ---\n{b[:600]}" for i, (a, b) in enumerate(zones, start=1)]
    return (f"{len(zones)} zone(s) dans {file}. Lis-les à l'utilisateur et propose : garder la nôtre (keep=\"ours\"), "
            "la leur (keep=\"theirs\"), ou éditer avec write_file.\n\n" + "\n\n".join(out))


def create_pull_request(repo: str, title: str, body: str = "", base: str = "main", draft: bool = False) -> str:
    """Crée une Pull Request GitHub depuis la branche courante (pousse d'abord si besoin).

    Args:
        repo: Dossier du dépôt.
        title: Titre de la PR.
        body: Description.
        base: Branche cible.
        draft: True pour un brouillon.
    """
    rem = _remote(repo)
    if not rem:
        return "Pas de dépôt GitHub distant (origin)."
    branche = _git(repo, "rev-parse", "--abbrev-ref", "HEAD").strip()
    _git(repo, "push", "-u", "origin", branche)
    data, err = _gh("POST", f"/repos/{rem[0]}/{rem[1]}/pulls", title=title, head=branche, base=base, body=body, draft=draft)
    if err:
        return err
    return f"PR créée : {data.get('html_url')}"


def summarize_pr(repo: str, number: int, kind: str = "pr") -> str:
    """Résume une Pull Request ou une issue GitHub : titre, auteur, état, description, fichiers changés, derniers commentaires.

    Args:
        repo: Dossier du dépôt (ou "owner/nom").
        number: Numéro.
        kind: "pr" ou "issue".
    """
    rem = _depot(repo)
    if not rem:
        return "Dépôt GitHub introuvable."
    o, n = rem
    chemin = f"/repos/{o}/{n}/{'pulls' if kind == 'pr' else 'issues'}/{int(number)}"
    data, err = _gh("GET", chemin)
    if err:
        return err
    out = [f"#{number} « {data.get('title')} » par {data.get('user', {}).get('login')} — {data.get('state')}",
           (data.get("body") or "")[:1200]]
    if kind == "pr":
        fichiers, _ = _gh("GET", chemin + "/files")
        if fichiers:
            out.append("Fichiers : " + ", ".join(f"{f['filename']} (+{f['additions']}/-{f['deletions']})" for f in fichiers[:20]))
    comms, _ = _gh("GET", f"/repos/{o}/{n}/issues/{int(number)}/comments")
    for c in (comms or [])[-5:]:
        out.append(f"- {c['user']['login']} : {c['body'][:200]}")
    return "\n".join(out)


def create_issues(repo: str, todo: str, labels: str = "") -> str:
    """Crée des issues GitHub depuis une liste dictée (une par ligne ou séparée par des points-virgules).

    Args:
        repo: Dossier du dépôt (ou "owner/nom").
        todo: Les tâches, ex. "corriger le bouton login ; ajouter la page profil".
        labels: Labels séparés par des virgules.
    """
    rem = _depot(repo)
    if not rem:
        return "Dépôt GitHub introuvable."
    o, n = rem
    items = [t.strip(" -•") for t in re.split(r"[;\n]", todo) if t.strip(" -•")]
    lab = [l.strip() for l in labels.split(",") if l.strip()]
    urls = []
    for it in items:
        data, err = _gh("POST", f"/repos/{o}/{n}/issues", title=it[:120], body="Créée à la voix via Jarvis.", labels=lab)
        urls.append(data.get("html_url") if data else f"échec ({err})")
    return f"{len(items)} issue(s) :\n" + "\n".join(urls)


def changelog(repo: str, since: str = "", output: str = "") -> str:
    """Génère un changelog depuis les commits (groupés : nouveautés, corrections, autres) depuis un tag ou une date.

    Args:
        repo: Dossier du dépôt.
        since: Tag (ex. "v1.2.0") ou date (ex. "2026-08-01") ; vide = depuis le dernier tag.
        output: Fichier à écrire (vide = CHANGELOG.md dans le dépôt, ajouté en tête).
    """
    if not since:
        since = _git(repo, "describe", "--tags", "--abbrev=0").strip()
        if since.lower().startswith("fatal"):
            since = ""
    est_date = bool(re.match(r"\d{4}-\d{2}-\d{2}", since))
    plage = f"{since}..HEAD" if since and not est_date else "HEAD"
    args = ["log", plage, "--pretty=format:%s (%h)", "--no-merges"] + ([f"--since={since}"] if est_date else [])
    lignes = [l for l in _git(repo, *args).splitlines() if l.strip()]
    if not lignes:
        return "Aucun commit sur la période."
    groupes: dict[str, list[str]] = {"Nouveautés": [], "Corrections": [], "Autres": []}
    for l in lignes:
        bas = l.lower()
        if bas.startswith(("feat", "add", "ajout", "nouveau")) or "ajoute" in bas:
            groupes["Nouveautés"].append(l)
        elif bas.startswith(("fix", "corr", "bug")) or "corrige" in bas:
            groupes["Corrections"].append(l)
        else:
            groupes["Autres"].append(l)
    md = [f"## {datetime.now():%Y-%m-%d}" + (f" (depuis {since})" if since else "")]
    for g, ls in groupes.items():
        if ls:
            md.append(f"### {g}\n" + "\n".join(f"- {l}" for l in ls))
    texte = "\n\n".join(md) + "\n\n"
    out = Path(output) if output else Path(repo).expanduser() / "CHANGELOG.md"
    ancien = out.read_text(encoding="utf-8") if out.exists() else "# Changelog\n\n"
    if ancien.startswith("# Changelog"):
        nouveau = ancien.replace("# Changelog\n\n", "# Changelog\n\n" + texte, 1)
    else:
        nouveau = texte + ancien
    out.write_text(nouveau, encoding="utf-8")
    return f"Changelog écrit dans {out} ({len(lignes)} commits).\n\n{texte[:1500]}"


def git_release(repo: str, tag: str, title: str = "", notes: str = "", push: bool = True) -> str:
    """Crée un tag Git et, si le dépôt est sur GitHub, une release avec des notes (générées des commits si vides).

    Args:
        repo: Dossier du dépôt.
        tag: Nom du tag (ex. "v1.3.0").
        title: Titre de la release (vide = le tag).
        notes: Notes (vide = commits depuis le tag précédent).
        push: Pousser le tag.
    """
    if not notes:
        prec = _git(repo, "describe", "--tags", "--abbrev=0").strip()
        plage = f"{prec}..HEAD" if prec and not prec.lower().startswith("fatal") else "HEAD"
        notes = "\n".join(f"- {l}" for l in _git(repo, "log", plage, "--pretty=format:%s", "--no-merges").splitlines()[:40])
    r = _git(repo, "tag", "-a", tag, "-m", title or tag)
    if push:
        r += "\n" + _git(repo, "push", "origin", tag)
    rem = _remote(repo)
    if rem:
        data, err = _gh("POST", f"/repos/{rem[0]}/{rem[1]}/releases", tag_name=tag, name=title or tag, body=notes)
        if not err:
            return f"Tag {tag} créé et release publiée : {data.get('html_url')}"
        return f"Tag {tag} créé. Release GitHub non créée : {err}"
    return f"Tag {tag} créé (pas de GitHub distant). {r[-300:]}"


def git_stash(repo: str, action: str = "push", message: str = "") -> str:
    """Git stash : mettre de côté les modifications en cours (push), les reprendre (pop), lister (list), jeter (drop).

    Args:
        repo: Dossier du dépôt.
        action: "push", "pop", "list", "drop" ou "apply".
        message: Message pour push.
    """
    if action == "push":
        return _git(repo, "stash", "push", "-u", "-m", message or f"jarvis {datetime.now():%d/%m %H:%M}") or "Rien à mettre de côté."
    if action in ("pop", "list", "drop", "apply"):
        return _git(repo, "stash", action) or "Rien."
    return "Action : push, pop, list, drop ou apply."


def git_bisect(repo: str, good: str, bad: str = "HEAD", test_command: str = "") -> str:
    """Retrouve le commit qui a introduit un bug (git bisect) : automatiquement avec une commande de test, sinon guide pas à pas.

    Args:
        repo: Dossier du dépôt.
        good: Un commit ou tag où ça marchait.
        bad: Un commit où ça casse (HEAD par défaut).
        test_command: Commande qui renvoie 0 si OK (ex. "pytest -x tests/test_login.py"). Vide = mode manuel.
    """
    _git(repo, "bisect", "reset")
    r = _git(repo, "bisect", "start", bad, good)
    if not test_command:
        return (f"Bisect démarré : {r}\nGit a fait un checkout au milieu. Teste, puis dis-moi « ça marche » ou « ça casse » : "
                "je lancerai run_command(\"git bisect good\") ou (\"git bisect bad\") dans le dépôt jusqu'au coupable, puis git bisect reset.")
    cmd = ["cmd", "/c", test_command] if IS_WINDOWS else ["sh", "-c", test_command]
    r = _run(["git", "bisect", "run", *cmd], cwd=Path(repo).expanduser(), timeout=1800)
    m = re.search(r"([0-9a-f]{7,40}) is the first bad commit", r)
    _git(repo, "bisect", "reset")
    if m:
        detail = _git(repo, "show", "--stat", "--pretty=format:%h %an %ad%n%s", m.group(1))
        return f"Commit coupable : {m.group(1)}\n{detail[:1200]}"
    return f"Bisect terminé sans coupable clair :\n{r[-1500:]}"


_GITIGNORE = {
    "python": "__pycache__/\n*.py[cod]\n.venv/\nvenv/\n.env\n*.egg-info/\ndist/\nbuild/\n.pytest_cache/\n.mypy_cache/\n.ruff_cache/\n",
    "node": "node_modules/\ndist/\nbuild/\n.next/\n.nuxt/\n.env\n.env.*\n!.env.example\nnpm-debug.log*\n.turbo/\ncoverage/\n",
    "unity": "[Ll]ibrary/\n[Tt]emp/\n[Oo]bj/\n[Bb]uild/\n[Ll]ogs/\n[Uu]serSettings/\n*.csproj\n*.sln\n",
    "rust": "target/\n", "go": "bin/\n*.exe\nvendor/\n", "java": "target/\n*.class\n.gradle/\nbuild/\n",
    "flutter": ".dart_tool/\nbuild/\n.flutter-plugins*\n*.iml\n", "csharp": "bin/\nobj/\n*.user\n.vs/\n",
}
_COMMUN = "# Système\n.DS_Store\nThumbs.db\ndesktop.ini\n# Éditeurs\n.idea/\n.vscode/\n*.swp\n# Secrets\n.env\n*.pem\n*.key\n"


def gitignore(repo: str, stacks: str = "") -> str:
    """Génère un .gitignore adapté au projet (détection automatique : python, node, rust, go, java, flutter, unity, csharp).

    Args:
        repo: Dossier du projet.
        stacks: Forcer des technologies séparées par des virgules (vide = détection).
    """
    p = Path(repo).expanduser()
    if stacks:
        choix = [s.strip().lower() for s in stacks.split(",")]
    else:
        choix = []
        if any((p / f).exists() for f in ("requirements.txt", "pyproject.toml", "setup.py")) or list(p.glob("*.py")):
            choix.append("python")
        if (p / "package.json").exists():
            choix.append("node")
        if (p / "Cargo.toml").exists():
            choix.append("rust")
        if (p / "go.mod").exists():
            choix.append("go")
        if (p / "pom.xml").exists() or (p / "build.gradle").exists():
            choix.append("java")
        if (p / "pubspec.yaml").exists():
            choix.append("flutter")
        if (p / "Assets").is_dir() and (p / "ProjectSettings").is_dir():
            choix.append("unity")
        if list(p.glob("*.csproj")) or list(p.glob("*.sln")):
            choix.append("csharp")
    contenu = _COMMUN + "".join(f"# {s}\n{_GITIGNORE.get(s, '')}" for s in choix)
    f = p / ".gitignore"
    if f.exists():
        ancien = f.read_text(encoding="utf-8")
        nouveau = ancien.rstrip() + "\n" + "\n".join(l for l in contenu.splitlines() if l and l not in ancien) + "\n"
    else:
        nouveau = contenu
    f.write_text(nouveau, encoding="utf-8")
    return f".gitignore écrit pour : {', '.join(choix) or 'générique'}."


# --------------------------------------------------------------------------
# Lecture d'erreurs, revue, messages, README, CI
# --------------------------------------------------------------------------
_PISTES = {"ModuleNotFoundError": "un paquet manque : pip install <nom> dans le bon venv",
           "ImportError": "import circulaire ou version de paquet incompatible",
           "KeyError": "clé absente : vérifie le nom exact ou utilise .get()",
           "TypeError": "mauvais type ou mauvais nombre d'arguments",
           "AttributeError": "l'objet est None ou n'a pas cet attribut : vérifie ce qui le crée",
           "FileNotFoundError": "chemin faux ou relatif au mauvais dossier",
           "PermissionError": "fichier ouvert ailleurs ou droits insuffisants",
           "ConnectionRefused": "le service n'écoute pas sur ce port",
           "ECONNREFUSED": "le serveur n'est pas lancé ou mauvais port",
           "Cannot read properties of undefined": "variable undefined : ordre de chargement ou réponse API vide",
           "CORS": "le serveur doit autoriser l'origine du front",
           "401": "authentification manquante ou expirée", "403": "droits insuffisants", "404": "route ou fichier absent",
           "500": "erreur côté serveur : lire ses journaux", "OutOfMemory": "mémoire insuffisante",
           "CUDA out of memory": "VRAM pleine : modèle plus petit ou batch réduit"}


def explain_error(text: str = "", log_path: str = "") -> str:
    """Prépare l'explication d'une erreur ou d'une stack trace : isole la vraie cause, le fichier et la ligne, et les pistes classiques.

    Args:
        text: La stack trace collée (vide = lire log_path).
        log_path: Fichier journal à lire (les 200 dernières lignes).
    """
    if not text and log_path:
        p = Path(log_path).expanduser()
        if not p.exists():
            return f"Introuvable : {p}"
        text = "\n".join(p.read_text(encoding="utf-8", errors="replace").splitlines()[-200:])
    if not text:
        return "Donne la trace ou un fichier."
    lignes = text.strip().splitlines()
    derniere = next((l for l in reversed(lignes) if l.strip() and not l.startswith(" ")), lignes[-1])
    fichiers = (re.findall(r'File "([^"]+)", line (\d+)', text) or re.findall(r"at .*?\(([^:)]+):(\d+)", text)
                or re.findall(r"([\w./\\-]+\.\w+):(\d+)", text))
    pistes = [f"- {k} : {v}" for k, v in _PISTES.items() if k.lower() in text.lower()]
    return (f"Erreur finale : {derniere.strip()[:300]}\n"
            + (f"Endroit : {fichiers[-1][0]} ligne {fichiers[-1][1]}\n" if fichiers else "")
            + (f"Chaîne : {' -> '.join(f'{Path(f).name}:{l}' for f, l in fichiers[-4:])}\n" if len(fichiers) > 1 else "")
            + ("Pistes :\n" + "\n".join(pistes) if pistes else "Pas de piste automatique : lis le message final et le fichier indiqué.")
            + "\nExplique ça à l'utilisateur en une phrase, puis propose la correction.")


def review_before_commit(repo: str, max_chars: int = 6000) -> str:
    """Revue de code avant commit : diff des modifications, fichiers touchés, lint rapide, secrets, TODO oubliés, gros fichiers.

    Args:
        repo: Dossier du dépôt.
        max_chars: Taille max du diff renvoyé.
    """
    p = Path(repo).expanduser()
    stat = _git(repo, "diff", "--stat", "HEAD") or _git(repo, "status", "--short")
    diff = _git(repo, "diff", "HEAD")[:max_chars]
    alertes = []
    for l in diff.splitlines():
        if l.startswith("+") and not l.startswith("+++"):
            if re.search(r"(api[_-]?key|secret|password|token)\s*[=:]\s*['\"][^'\"]{8,}", l, re.I):
                alertes.append("SECRET possible : " + l[:100])
            if re.search(r"\b(TODO|FIXME|XXX|HACK)\b", l):
                alertes.append("TODO : " + l[:100])
            if re.search(r"\b(console\.log|debugger|pdb\.set_trace|breakpoint\()", l):
                alertes.append("Debug oublié : " + l[:100])
    gros = [l for l in _git(repo, "diff", "--cached", "--name-only").splitlines() if (p / l).exists() and (p / l).stat().st_size > 5_000_000]
    lint = _run(["ruff", "check", ".", "--quiet"], cwd=p)[:800] if shutil.which("ruff") and list(p.glob("*.py")) else ""
    return (f"Fichiers :\n{stat}\n\n" + ("ALERTES :\n" + "\n".join(alertes[:15]) + "\n\n" if alertes else "")
            + (f"Fichiers > 5 Mo : {', '.join(gros)}\n\n" if gros else "") + (f"Lint :\n{lint}\n\n" if lint else "")
            + f"Diff :\n{diff}\n\nRelis ce diff : logique, cas limites, nommage, tests. Donne un avis en cinq points max, puis propose le message de commit.")


def commit_message(repo: str) -> str:
    """Prépare un message de commit : résumé des changements (fichiers, symboles ajoutés, extrait) pour que tu rédiges un titre net et un corps court.

    Args:
        repo: Dossier du dépôt.
    """
    stat = _git(repo, "diff", "--stat", "HEAD") or _git(repo, "status", "--short")
    diff = _git(repo, "diff", "HEAD", "--unified=0")[:4000]
    fonctions = sorted(set(re.findall(r"^\+\s*(?:def|function|const|class|export (?:default )?function)\s+(\w+)", diff, re.M)))[:12]
    return (f"Changements :\n{stat}\n\nNouveaux symboles : {', '.join(fonctions) or 'aucun'}\n\nExtrait :\n{diff[:2500]}\n\n"
            "Rédige : une ligne de titre à l'impératif (< 70 caractères, sans point), une ligne vide, puis 1 à 4 puces sur le pourquoi. "
            "Ensuite git_commit(repo, message).")


def scaffold_readme(repo: str, write: bool = False) -> str:
    """Rassemble ce qu'il faut pour un README (technos, scripts, structure, commandes de lancement) et peut écrire un premier jet.

    Args:
        repo: Dossier du projet.
        write: True pour écrire README.md (s'il n'existe pas).
    """
    p = Path(repo).expanduser()
    technos, commandes, structure = [], [], []
    if (p / "package.json").exists():
        try:
            pk = json.loads((p / "package.json").read_text(encoding="utf-8"))
            technos.append("Node.js : " + ", ".join(list(pk.get("dependencies", {}))[:8]))
            commandes += [f"npm run {k}" for k in pk.get("scripts", {})][:8]
        except Exception:  # noqa: BLE001
            pass
    if (p / "requirements.txt").exists():
        deps = [l.split("==")[0].split(">=")[0] for l in (p / "requirements.txt").read_text(encoding="utf-8").splitlines() if l.strip() and not l.startswith("#")]
        technos.append("Python : " + ", ".join(deps[:10]))
        commandes += ["python -m venv .venv", "pip install -r requirements.txt"]
    if (p / "Dockerfile").exists():
        commandes.append("docker build -t app . && docker run app")
    for f in sorted(p.iterdir())[:25]:
        if f.name.startswith(".") or f.name in ("node_modules", "__pycache__", ".venv"):
            continue
        structure.append(f"{f.name}{'/' if f.is_dir() else ''}")
    md = (f"# {p.name}\n\n_Une phrase sur ce que fait le projet._\n\n## Technologies\n"
          + "\n".join(f"- {t}" for t in technos or ["à compléter"])
          + "\n\n## Installation\n```bash\n" + "\n".join(commandes or ["à compléter"]) + "\n```\n\n## Structure\n"
          + "\n".join(f"- `{s}`" for s in structure) + "\n\n## Licence\n\nMIT\n")
    if write and not (p / "README.md").exists():
        (p / "README.md").write_text(md, encoding="utf-8")
        return f"README.md écrit (premier jet à compléter) :\n\n{md[:1500]}"
    return "Éléments pour le README (rédige-le et écris-le avec write_file, ou scaffold_readme(write=True)) :\n\n" + md[:2500]


def ci_status(repo: str, watch_minutes: int = 0) -> str:
    """Suivi de la CI GitHub Actions : derniers runs, état, et alerte à la voix à la fin si watch_minutes > 0.

    Args:
        repo: Dossier du dépôt (ou "owner/nom").
        watch_minutes: Surveiller en fond jusqu'à N minutes et prévenir quand c'est fini (0 = juste l'état).
    """
    rem = _depot(repo)
    if not rem:
        return "Dépôt GitHub introuvable."
    o, n = rem
    data, err = _gh("GET", f"/repos/{o}/{n}/actions/runs?per_page=6")
    if err:
        return err
    runs = data.get("workflow_runs", [])
    if not runs:
        return "Aucun run GitHub Actions."
    lignes = [f"- {r['name']} #{r['run_number']} ({r['head_branch']}) : {r['status']} {r.get('conclusion') or ''} — {r['html_url']}" for r in runs]
    if watch_minutes > 0 and runs[0]["status"] != "completed":
        import threading
        import time as _t

        run_id = runs[0]["id"]

        def boucle():
            fin = _t.time() + 60 * watch_minutes
            while _t.time() < fin:
                _t.sleep(30)
                d, _ = _gh("GET", f"/repos/{o}/{n}/actions/runs/{run_id}")
                if d and d.get("status") == "completed":
                    try:
                        import noyau

                        noyau.hooks["dire"](f"La CI de {n} est terminée : {'succès' if d.get('conclusion') == 'success' else 'échec'}.")
                    except Exception:  # noqa: BLE001
                        pass
                    return

        threading.Thread(target=boucle, daemon=True).start()
        lignes.append(f"Je surveille le run #{runs[0]['run_number']} et je te préviens à la fin.")
    return "\n".join(lignes)


TOOLS = [runtime_versions, install_wsl, vscode_extensions, open_in_editor, env_vars, ssh_keygen, mcp_servers,
         git_init, git_prune_branches, git_conflicts, create_pull_request, summarize_pr, create_issues, changelog,
         git_release, git_stash, git_bisect, gitignore, explain_error, review_before_commit, commit_message,
         scaffold_readme, ci_status]
